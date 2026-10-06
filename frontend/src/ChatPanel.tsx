import { useEffect, useRef, useState } from 'react'
import { ApiError, errorMessage, listAll, request } from './api'
import type { CourseRun } from './api'
import type { ChatSession, ChatTurn, Citation } from './ragTypes'

export default function ChatPanel({ run, csrfToken, onExpired, onRead }: {
  run: CourseRun; csrfToken: string; onExpired: () => void; onRead: (citation: Citation) => void
}) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionId, setSessionId] = useState('')
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [question, setQuestion] = useState('')
  const [error, setError] = useState('')
  const [loadingSessions, setLoadingSessions] = useState(true)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const loading = loadingSessions || loadingHistory
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const alive = useRef(true)
  const retry = useRef<{ message: string; key: string } | null>(null)
  const canWrite = run.status === 'active' && run.data_origin === 'real'
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  function fail(value: unknown) {
    if (!alive.current) return
    setError(errorMessage(value))
    if (value instanceof ApiError && value.status === 401) onExpired()
  }
  useEffect(() => {
    let stopped = false
    setLoadingSessions(true); setError('')
    listAll<ChatSession>(`/course-runs/${run.id}/chat-sessions`).then(value => {
      if (!stopped) { setSessions(value); setSessionId(id => id || value[0]?.id || '') }
    }).catch(value => { if (!stopped) fail(value) })
      .finally(() => { if (!stopped) setLoadingSessions(false) })
    return () => { stopped = true }
  }, [run.id, refresh])
  useEffect(() => {
    let stopped = false
    setTurns([])
    if (!sessionId) { setLoadingHistory(false); return }
    setLoadingHistory(true)
    listAll<ChatTurn>(`/chat-sessions/${sessionId}/messages`).then(value => { if (!stopped) setTurns(value) })
      .catch(value => { if (!stopped) fail(value) }).finally(() => { if (!stopped) setLoadingHistory(false) })
    return () => { stopped = true }
  }, [sessionId, refresh])
  async function newSession() {
    const session = await request<ChatSession>(`/course-runs/${run.id}/chat-sessions`, { method: 'POST', csrfToken })
    if (alive.current) { setSessions(v => [session, ...v]); setSessionId(session.id); setQuestion(''); retry.current = null }
    return session.id
  }
  async function send(message = question.trim(), key?: string) {
    if (!message || busy || !canWrite) return
    setBusy(true); setError('')
    const requestKey = key || (retry.current?.message === message ? retry.current.key : crypto.randomUUID())
    try {
      const id = sessionId || await newSession()
      retry.current = { message, key: requestKey }
      await request<ChatTurn>(`/chat-sessions/${id}/messages`, { method: 'POST', csrfToken, body: { message, request_key: requestKey } })
      if (alive.current) { setQuestion(''); retry.current = null; setRefresh(v => v + 1) }
    } catch (value) { if (alive.current) { setQuestion(message); fail(value) } }
    finally { if (alive.current) setBusy(false) }
  }
  return <section className="chat-panel" aria-labelledby="chat-title">
    <span className="eyebrow">HỎI TỪ TÀI LIỆU</span><h3 id="chat-title">Trợ giảng AI</h3>
    <p className="muted">Chatbot chỉ dùng đoạn PDF được giảng viên duyệt. Mỗi câu hỏi được xử lý độc lập; nêu rõ thuật ngữ để tìm đúng nguồn. Mở trang trích dẫn để kiểm tra câu trả lời.</p>
    <p className="muted">Gemini nhận câu hỏi và tối đa 4 đoạn nguồn để trả lời; embedding được tạo trên máy. Đừng nhập mật khẩu hoặc thông tin cá nhân vào câu hỏi.</p>
    {!canWrite && <p className="notice">Lượt học {run.data_origin === 'synthetic' ? 'mô phỏng' : 'đã đóng/chưa mở'}: chỉ xem lịch sử, không gửi câu hỏi mới.</p>}
    <div className="rag-actions">
      <label>Phiên trò chuyện
        <select value={sessionId} disabled={busy || loading} onChange={e => { setSessionId(e.target.value); setQuestion(''); setError(''); retry.current = null }}>
          {!sessions.length && <option value="">Chưa có phiên</option>}
          {sessions.map(s => <option key={s.id} value={s.id}>{new Date(s.created_at).toLocaleString('vi-VN')}</option>)}
        </select>
      </label>
      <button className="button button-secondary" disabled={busy || !canWrite || loading} onClick={async () => {
        setBusy(true); setError('')
        try { await newSession() } catch (value) { fail(value) } finally { if (alive.current) setBusy(false) }
      }}>Phiên mới</button>
      <button className="text-button" disabled={busy || loading} onClick={() => setRefresh(v => v + 1)}>Tải lại chat</button>
    </div>
    {loading && <p role="status">Đang tải lịch sử chat…</p>}
    {error && <p className="notice notice-error" role="alert">{error}</p>}
    {!loading && !turns.length && <p className="muted">Chưa có câu hỏi. Ví dụ: Row và Column khác nhau thế nào?</p>}
    <div className="chat-history" aria-live="polite">
      {turns.map(turn => <article className="chat-turn" key={turn.id}>
        <p><strong>Bạn:</strong> {turn.question}</p>
        <p className="chat-answer"><strong>Trợ giảng:</strong> {turn.status === 'pending' ? 'Đang xử lý. Hãy tải lại lịch sử sau ít giây.'
          : turn.status === 'provider_error' ? 'Mô hình chưa trả lời được. Có thể thử lại câu hỏi này.' : turn.answer}</p>
        {turn.status === 'insufficient_sources' && <span className="rag-badge">Chưa đủ nguồn</span>}
        {turn.status === 'source_unavailable' && <span className="rag-badge">Nguồn đã thu hồi</span>}
        <div className="chat-citations">{turn.citations.map((citation, index) => <div key={`${citation.chunk_id}:${index}`}>
          <button className="text-button" onClick={() => onRead(citation)}>{citation.document_code} · bản {citation.version} · trang {citation.pdf_page}</button>
          <blockquote>{citation.excerpt}</blockquote>
        </div>)}</div>
        {(turn.status === 'provider_error' || turn.status === 'pending') && canWrite && <button className="text-button" disabled={busy}
          onClick={() => void send(turn.question, turn.request_key)}>Thử lại câu hỏi này</button>}
      </article>)}
    </div>
    <form onSubmit={e => { e.preventDefault(); void send() }}>
      <fieldset disabled={busy || !canWrite || loading}>
        <label>Câu hỏi từ PDF · tối đa 2000 ký tự
          <textarea rows={3} required maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} />
        </label>
        <button className="button button-primary" disabled={!question.trim()}>{busy ? 'Đang tìm nguồn và trả lời…' : retry.current?.message === question.trim() ? 'Thử gửi lại câu hỏi' : 'Gửi câu hỏi'}</button>
      </fieldset>
    </form>
  </section>
}

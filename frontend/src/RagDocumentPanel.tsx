import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { ApiError, errorMessage, listAll, request } from './api'
import type { RagPage, RagStatus } from './ragTypes'
const PdfViewer = lazy(() => import('./PdfViewer'))

const stateLabels: Record<RagStatus['status'], string> = {
  unprepared: 'Chưa bật', processing: 'Đang chuẩn bị nguồn', ready: 'Sẵn sàng',
  needs_review: 'Có trang cần kiểm tra', failed: 'Chuẩn bị chưa thành công', disabled: 'Đã tắt',
}
const pageLabels: Record<RagPage['state'], string> = {
  automatic: 'Hệ thống xử lý tự động', checked: 'Giảng viên đã kiểm tra', needs_review: 'Cần kiểm tra', excluded: 'Đã loại',
}
const issueLabels: Record<string, string> = {
  contains_images: 'Có ảnh cần đối chiếu', short_or_empty: 'Ít hoặc không có chữ',
  extraction_failed: 'Không trích được chữ', possible_toc: 'Có thể là mục lục',
  possible_cover: 'Có thể là trang bìa', excluded_kind: 'Loại nội dung không dùng tự động',
  manual_transcription: 'Bản phiên chép cần kiểm tra',
}

export default function RagDocumentPanel({ versionId, documentStatus, csrfToken, onPublished, onExpired }: {
  versionId: string; documentStatus: string; csrfToken: string; onPublished: () => void
  onExpired: () => void
}) {
  const [state, setState] = useState<RagStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState(true)
  const [pages, setPages] = useState<RagPage[]>([])
  const [selected, setSelected] = useState(0)
  const [pagesLoading, setPagesLoading] = useState(false)
  const [transcription, setTranscription] = useState('')
  const [preview, setPreview] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const page = pages.find(p => p.pdf_page === selected)
  const processing = state?.status === 'processing'
  const canReview = !!state?.enabled && !state.legacy && !processing && !busy
  const fail = useCallback((value: unknown) => {
    setError(errorMessage(value))
    if (value instanceof ApiError && value.status === 401) onExpired()
  }, [onExpired])
  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load() {
      try {
        const value = await request<RagStatus>(`/document-versions/${versionId}/rag`)
        if (!stopped) {
          setState(value); setLoading(false)
          if (value.status === 'processing') timer = setTimeout(load, 2000)
        }
      } catch (value) { if (!stopped) { fail(value); setLoading(false) } }
    }
    void load()
    return () => { stopped = true; clearTimeout(timer) }
  }, [versionId, documentStatus, refresh, fail])
  useEffect(() => {
    let stopped = false
    if (!open || processing) return
    setPagesLoading(true)
    listAll<RagPage>(`/document-versions/${versionId}/rag/pages?needs_review_only=${filter}`).then(value => {
      if (!stopped) {
        setPages(value); setSelected(old => value.some(p => p.pdf_page === old) ? old : value[0]?.pdf_page || 0)
      }
    }).catch(value => { if (!stopped) fail(value) }).finally(() => { if (!stopped) setPagesLoading(false) })
    return () => { stopped = true }
  }, [open, filter, versionId, refresh, processing, fail])
  async function toggle(enable: boolean) {
    setBusy(true); setError('')
    try {
      const value = await request<RagStatus>(`/document-versions/${versionId}/rag/${enable ? 'enable' : 'disable'}`, { method: 'POST', csrfToken })
      setState(value); setRefresh(v => v + 1)
      if (enable) onPublished()
    } catch (value) { fail(value) }
    finally { setBusy(false) }
  }
  async function review(action: 'allow' | 'exclude', text?: string) {
    if (!page) return
    setBusy(true); setError('')
    try {
      const value = await request<RagStatus>(`/document-versions/${versionId}/rag/pages/${page.pdf_page}`, {
        method: 'PATCH', csrfToken, body: { revision: page.revision, action, ...(text ? { transcription: text } : {}) },
      })
      setState(value); setRefresh(v => v + 1); setTranscription('')
    } catch (value) { fail(value) }
    finally { setBusy(false) }
  }
  return <section className="rag-document" aria-label="Trợ giảng cho phiên bản PDF">
    <p><strong>Trợ giảng:</strong> {loading ? 'Đang tải trạng thái…' : state?.legacy ? 'Đang dùng nguồn đã duyệt trước đây' : state ? stateLabels[state.status] : 'Không tải được trạng thái'}</p>
    {state && !processing && <p className="muted">{state.usable_pages} trang đủ điều kiện làm nguồn · {state.counts.needs_review} trang cần kiểm tra.</p>}
    {documentStatus !== 'published' && state?.enabled && <p className="muted">PDF chưa công bố; chatbot hiện không sử dụng tài liệu này.</p>}
    <div className="rag-actions">
      {(!state?.enabled || state?.legacy || state?.status === 'failed' || documentStatus !== 'published') && <button className="button button-primary" disabled={busy || loading || processing}
        onClick={() => void toggle(true)}>{state?.status === 'failed' ? 'Thử chuẩn bị lại' : 'Công bố và dùng cho trợ giảng'}</button>}
      {state?.enabled && <button className="text-button" disabled={busy || loading} onClick={() => void toggle(false)}>Tắt trợ giảng cho bản này</button>}
      <button className="text-button" disabled={busy || loading || processing} onClick={() => setOpen(v => !v)}>{open ? 'Đóng kiểm tra nguồn' : 'Kiểm tra nguồn'}</button>
      {(error || state?.status === 'failed') && <button className="text-button" disabled={busy} onClick={() => { setError(''); setRefresh(v => v + 1) }}>Tải lại trạng thái</button>}
    </div>
    {processing && <p role="status">Hệ thống đang trích văn bản và chuẩn bị tìm kiếm. Bạn có thể tiếp tục quản lý học phần.</p>}
    {state?.status === 'failed' && <p role="alert" className="notice notice-error">{state.error_code === 'EMBEDDING_UNAVAILABLE' ? 'Model tìm kiếm trên máy chưa sẵn sàng. Cần kiểm tra cấu hình rồi thử chuẩn bị lại.' : 'Nguồn chưa chuẩn bị xong. Hãy thử chuẩn bị lại; PDF vẫn xem được.'}</p>}
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    {open && <div className="rag-page-review">
      {(!state?.enabled || state.legacy) && <p className="notice">Bấm công bố và dùng cho trợ giảng trước khi lưu quyết định theo trang.</p>}
      <p className="muted">Trang tự động không có nghĩa là đã được giảng viên kiểm tra. Trang có cảnh báo đang tạm loại khỏi nguồn trả lời; trang đã kiểm tra có thể sử dụng sau khi xử lý xong.</p>
      <label><input type="checkbox" checked={filter} disabled={busy || processing} onChange={e => { setFilter(e.target.checked); setTranscription('') }} /> Chỉ hiện trang cần kiểm tra</label>
      {(pagesLoading || processing) ? <p role="status">Đang cập nhật nguồn…</p> : !pages.length ? <p>{filter ? 'Không có trang cần kiểm tra.' : 'Chưa có nguồn. Bấm công bố và dùng cho trợ giảng để chuẩn bị.'}</p> : <>
        <label htmlFor={`rag-page-${versionId}`}>Trang cần đối chiếu</label>
          <select id={`rag-page-${versionId}`} value={selected} disabled={busy} onChange={e => { setSelected(Number(e.target.value)); setTranscription('') }}>
            {pages.map(p => <option key={p.pdf_page} value={p.pdf_page}>Trang {p.pdf_page} · {pageLabels[p.state]}</option>)}
          </select>
        {page && <>
          <p><strong>{pageLabels[page.state]}</strong></p>
          {!!page.issues.length && <p className="notice">{page.issues.map(i => issueLabels[i] || i).join(' · ')}</p>}
          {page.text_only && <p className="notice">Trang có ảnh: trợ giảng chỉ dùng phần chữ trích được. Nội dung hoặc mã nguồn chỉ nằm trong ảnh cần bản phiên chép đã kiểm tra.</p>}
          <button className="text-button" onClick={() => setPreview(true)}>Đối chiếu PDF trang {page.pdf_page}</button>
          <div className={preview ? 'rag-source-comparison' : ''}>
            <pre>{page.text || '[Không trích được văn bản; cần phiên chép trang gốc.]'}</pre>
            {preview && <Suspense fallback={<p role="status">Đang mở PDF để đối chiếu…</p>}>
              <PdfViewer key={`${versionId}:${page.pdf_page}`} versionId={versionId} title={`PDF trang ${page.pdf_page}`}
                teacherPreview initialPage={page.pdf_page} onClose={() => setPreview(false)} />
            </Suspense>}
          </div>
          <div className="rag-actions">
            <button className="button button-primary" disabled={!canReview || page.text.trim().length < 20} onClick={() => void review('allow')}>Đã đối chiếu, cho phép trang</button>
            <button className="button button-secondary" disabled={!canReview} onClick={() => void review('exclude')}>Loại trang khỏi trợ giảng</button>
          </div>
          <details><summary>Thêm bản phiên chép cho trang {page.pdf_page}</summary>
            <form onSubmit={e => { e.preventDefault(); void review('allow', transcription.trim()) }}>
              <fieldset disabled={!canReview}>
                <label>Văn bản đã đối chiếu (20–3500 ký tự)
                  <textarea required minLength={20} maxLength={3500} rows={5} value={transcription} onChange={e => setTranscription(e.target.value)} />
                </label>
                <button className="button button-secondary">Lưu phiên chép và cho phép trang</button>
              </fieldset>
            </form>
          </details>
        </>}
      </>}
    </div>}
  </section>
}

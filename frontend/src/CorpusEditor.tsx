import { useEffect, useState } from 'react'
import { ApiError, errorMessage, request } from './api'
import type { LearningDocument } from './learningTypes'
import type { Chunk } from './ragTypes'

const flags: Record<string, string> = {
  contains_images: 'Có ảnh: kiểm tra phần chữ/mã nguồn trong ảnh',
  short_or_empty: 'Ít hoặc không có chữ trích được',
  extraction_failed: 'Không trích được chữ',
  possible_toc: 'Có thể là mục lục',
  manual_transcription: 'Bản phiên chép thủ công cần đối chiếu PDF',
}
type ChunkPage = { items: Chunk[]; total: number; counts: Record<string, number> }

export default function CorpusEditor({ documents, csrfToken, onExpired, onRead }: {
  documents: LearningDocument[]; csrfToken: string; onExpired: () => void
  onRead?: (versionId: string, title: string, page: number) => void
}) {
  const versions = documents.flatMap(d => d.versions.map(v => ({ ...v, document: d })))
  const [versionId, setVersionId] = useState('')
  const version = versions.find(v => v.id === versionId)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<ChunkPage | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [manual, setManual] = useState('')
  const [kinds, setKinds] = useState<Record<string, Chunk['kind']>>({})
  const [offset, setOffset] = useState(0)
  function fail(value: unknown) {
    setError(errorMessage(value))
    if (value instanceof ApiError && value.status === 401) onExpired()
  }
  useEffect(() => {
    let stopped = false
    setData(null); setError(''); setKinds({})
    if (!versionId) return
    setLoading(true)
    request<ChunkPage>(`/document-versions/${versionId}/chunks?pdf_page=${page}&limit=10&offset=${offset}`)
      .then(value => { if (!stopped) setData(value) })
      .catch(value => { if (!stopped) fail(value) })
      .finally(() => { if (!stopped) setLoading(false) })
    return () => { stopped = true }
  }, [versionId, page, refresh, offset])
  async function mutate(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(''); setNotice('')
    try { await action(); setNotice(success); setRefresh(v => v + 1); return true }
    catch (value) { fail(value); return false }
    finally { setBusy(false) }
  }
  function review(chunk: Chunk, status: Chunk['review_status']) {
    void mutate(() => request(`/chunks/${chunk.id}`, { method: 'PATCH', csrfToken,
      body: { revision: chunk.revision, kind: kinds[chunk.id] || chunk.kind, review_status: status } }),
    status === 'reviewed' ? 'Đã duyệt đoạn. Chatbot chỉ dùng đoạn khi PDF đã công bố.' : 'Đã cập nhật trạng thái đoạn.')
  }
  return <section className="corpus-editor" aria-labelledby="corpus-title">
    <h3 id="corpus-title">Rà soát nguồn cho chatbot</h3>
    <p className="muted">Đối chiếu từng đoạn với trang PDF trước khi duyệt. Loại trang bìa, mục lục và chữ trích sai. Mã nguồn trong ảnh cần phiên chép và duyệt riêng.</p>
    <fieldset disabled={busy}>
      <label>Phiên bản PDF để rà soát
        <select value={versionId} onChange={e => { setVersionId(e.target.value); setPage(1); setOffset(0); setNotice(''); setManual('') }}>
          <option value="">Chọn phiên bản</option>
          {versions.map(v => <option key={v.id} value={v.id}>{v.document.code} · bản {v.version} · {v.page_count} trang</option>)}
        </select>
      </label>
      {version && <>
        <div className="rag-actions">
          <button className="button button-secondary" onClick={() => void mutate(
            () => request(`/document-versions/${versionId}/corpus`, { method: 'POST', csrfToken }),
            'Corpus đã sẵn sàng để rà soát. Đoạn cũ giữ nguyên; đoạn mới chờ duyệt.')}>Trích văn bản PDF</button>
          <button className="text-button" onClick={() => setRefresh(v => v + 1)} disabled={loading}>Tải lại nguồn</button>
          <button className="button button-secondary" onClick={() => void mutate(
            () => request(`/document-versions/${versionId}/embedding-index`, { method: 'POST', csrfToken }),
            'Đã lập chỉ mục embedding local cho các đoạn đã duyệt.')}>Lập chỉ mục embedding</button>
        </div>
        <label>Trang PDF cần rà soát
          <input type="number" min={1} max={version.page_count} value={page} onChange={e => {
            const next = e.target.valueAsNumber
            if (Number.isInteger(next) && next >= 1 && next <= version.page_count) { setPage(next); setOffset(0); setManual('') }
          }} />
        </label>
        {onRead ? <button className="text-button" onClick={() => onRead(versionId, version.document.title, page)}>Đối chiếu PDF trang {page}</button>
          : <a href={`/api/v1/document-versions/${versionId}/content#page=${page}`} target="_blank" rel="noopener noreferrer">Đối chiếu PDF trang {page}</a>}
      </>}
    </fieldset>
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    {notice && <p role="status" className="notice notice-success">{notice}</p>}
    {loading && <p role="status">Đang tải đoạn nguồn…</p>}
    {data && <>
      <p>Toàn phiên bản: {data.counts.reviewed || 0} đã duyệt · {data.counts.pending || 0} chờ duyệt · {data.counts.rejected || 0} đã loại.</p>
      {!(Object.values(data.counts).reduce((a, b) => a + b, 0)) && <p>Chưa có corpus. Bấm trích văn bản PDF trước.</p>}
      {!!Object.keys(data.counts).length && !data.total && <p>Trang này chưa có đoạn nguồn.</p>}
      {data.items.map(chunk => <article className="corpus-chunk" key={chunk.id}>
        <strong>Trang {chunk.pdf_page} · đoạn {chunk.chunk_index + 1} · {chunk.review_status === 'reviewed' ? 'Đã duyệt' : chunk.review_status === 'rejected' ? 'Đã loại' : 'Chờ duyệt'}</strong>
        <p className="muted">{chunk.embedding_code ? 'Đã có vector embedding local.' : 'Chưa có vector; duyệt rồi lập chỉ mục embedding.'}</p>
        {chunk.flags.length > 0 && <p className="notice">{chunk.flags.map(f => flags[f] || f).join(' · ')}</p>}
        <pre>{chunk.text || '[Không trích được văn bản. Cần kiểm tra trang gốc.]'}</pre>
        <fieldset disabled={busy}>
          <label>Loại đoạn {chunk.chunk_index + 1}
            <select value={kinds[chunk.id] || chunk.kind} onChange={e => setKinds({ ...kinds, [chunk.id]: e.target.value as Chunk['kind'] })}>
              <option value="content">Nội dung có chứng cứ</option><option value="cover">Trang bìa</option>
              <option value="toc">Mục lục</option><option value="image">Ảnh chưa phiên chép</option>
            </select>
          </label>
          <div className="rag-actions">
            <button className="button button-primary" disabled={(kinds[chunk.id] || chunk.kind) !== 'content' || chunk.text.trim().length < 20}
              onClick={() => review(chunk, 'reviewed')}>Đã đối chiếu, duyệt đoạn</button>
            <button className="button button-secondary" onClick={() => review(chunk, 'rejected')}>Loại đoạn</button>
            <button className="text-button" onClick={() => review(chunk, 'pending')}>Đưa về chờ duyệt</button>
          </div>
        </fieldset>
      </article>)}
      {data.total > 10 && <div className="rag-actions">
        <button className="text-button" disabled={offset === 0 || loading} onClick={() => setOffset(v => Math.max(0, v - 10))}>Đoạn trước</button>
        <button className="text-button" disabled={offset + 10 >= data.total || loading} onClick={() => setOffset(v => v + 10)}>Đoạn tiếp</button>
      </div>}
      {version && !!Object.keys(data.counts).length && <details>
        <summary>Thêm bản phiên chép cho trang {page}</summary>
        <form onSubmit={e => { e.preventDefault(); void mutate(
          () => request(`/document-versions/${versionId}/chunks`, { method: 'POST', csrfToken, body: { pdf_page: page, text: manual } }),
          'Đã thêm bản phiên chép chờ duyệt. Loại đoạn trích sai trước khi duyệt bản thay thế.').then(ok => { if (ok) setManual('') }) }}>
          <fieldset disabled={busy}>
            <label>Văn bản đã đối chiếu với PDF (20–3500 ký tự)
              <textarea required minLength={20} maxLength={3500} rows={6} value={manual} onChange={e => setManual(e.target.value)} />
            </label>
            <button className="button button-secondary">Thêm đoạn chờ duyệt</button>
          </fieldset>
        </form>
      </details>}
    </>}
  </section>
}

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { Topic } from './api'
import { request, errorMessage } from './api'
import type { RagRange, RagStatus } from './ragTypes'
import { useFormGuard } from './website/ui'

export default function RagScopeEditor({
  versionId,
  pageCount,
  topics,
  state,
  csrfToken,
  onSaved,
}: {
  versionId: string
  pageCount: number
  topics: Topic[]
  state: RagStatus
  csrfToken: string
  onSaved: (state: RagStatus) => void
}) {
  const [all, setAll] = useState(true),
    [ranges, setRanges] = useState<RagRange[]>([]),
    [saved, setSaved] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('')
  const [generation, setGeneration] = useState(state.generation_id)
  function reset() {
    const rows = state.scope_ranges || []
    setAll(!rows.length)
    setRanges(
      rows.length ? rows : [{ page_start: 1, page_end: pageCount, topic_id: null, label: '' }],
    )
    setSaved(JSON.stringify(rows))
    setGeneration(state.generation_id)
    setError('')
  }
  useEffect(reset, [versionId, pageCount])
  const dirty = !!saved && JSON.stringify(all ? [] : ranges) !== saved
  useEffect(()=>{if(JSON.stringify(state.scope_ranges||[])===saved)setGeneration(state.generation_id)},[state.generation_id,JSON.stringify(state.scope_ranges),saved])
  const guard = useFormGuard(dirty, busy)
  function update(index: number, change: Partial<RagRange>) {
    setRanges((rows) => rows.map((row, i) => (i === index ? { ...row, ...change } : row)))
    setMessage('')
  }
  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const result = await request<RagStatus>(`/document-versions/${versionId}/rag/scope`, {
        method: 'PUT',
        csrfToken,
        body: {
          expected_generation: generation,
          ranges: all
            ? []
            : ranges.map((row) => ({
                ...row,
                label: row.label?.trim() || '',
                topic_id: row.topic_id || null,
              })),
        },
      })
      setSaved(JSON.stringify(result.scope_ranges))
      setAll(!result.scope_ranges.length)
      setRanges(
        result.scope_ranges.length
          ? result.scope_ranges
          : [{ page_start: 1, page_end: pageCount, topic_id: null, label: '' }],
      )
      setGeneration(result.generation_id)
      onSaved(result)
      setMessage('Đã lưu phạm vi. Nếu nguồn đang bật, hệ thống sẽ chuẩn bị lại trong nền.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <details className="rag-scope">
      <summary>Phạm vi nguồn và chương/chủ đề (tùy chọn)</summary>
      <p className="muted">
        Mặc định dùng toàn bộ PDF. Chương/chủ đề chỉ là thông tin giảng viên xác nhận để ưu tiên tìm
        kiếm; không tự gắn tài liệu vào bài giảng. Dùng “Gắn tài liệu” trong chủ đề để hiển thị cho
        việc học.
      </p>
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      {guard && <p role="status">{guard}</p>}
      {message && <p role="status">{message}</p>}
      <form onSubmit={save} className="learning-form">
        <fieldset disabled={busy}>
          <label className="review-confirm">
            <input
              type="checkbox"
              checked={all}
              onChange={(e) => {
                setAll(e.target.checked)
                setMessage('')
              }}
            />
            Dùng toàn bộ tài liệu làm nguồn
          </label>
          {!all &&
            ranges.map((row, index) => (
              <div className="rag-range" key={index}>
                <div className="learning-form-grid">
                  <label>
                    Từ trang PDF
                    <input
                      aria-label={`Từ trang PDF ${index + 1}`}
                      type="number"
                      min={1}
                      max={pageCount}
                      required
                      value={row.page_start}
                      onChange={(e) => update(index, { page_start: Number(e.target.value) })}
                    />
                  </label>
                  <label>
                    Đến trang PDF
                    <input
                      aria-label={`Đến trang PDF ${index + 1}`}
                      type="number"
                      min={row.page_start}
                      max={pageCount}
                      required
                      value={row.page_end}
                      onChange={(e) => update(index, { page_end: Number(e.target.value) })}
                    />
                  </label>
                </div>
                <label>
                  Tên chương (tùy chọn)
                  <input
                    aria-label={`Tên chương ${index + 1}`}
                    maxLength={120}
                    value={row.label || ''}
                    onChange={(e) => update(index, { label: e.target.value })}
                  />
                </label>
                <label>
                  Chủ đề ưu tiên
                  <select
                    aria-label={`Chủ đề ưu tiên ${index + 1}`}
                    value={row.topic_id || ''}
                    onChange={(e) => update(index, { topic_id: e.target.value || null })}
                  >
                    <option value="">Nguồn chung của học phần</option>
                    {topics.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code} · {t.title}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="text-button"
                  disabled={ranges.length === 1}
                  onClick={() => setRanges((rows) => rows.filter((_, i) => i !== index))}
                >
                  Bỏ khoảng {index + 1}
                </button>
              </div>
            ))}
          {!all && (
            <button
              type="button"
              className="button button-secondary"
              disabled={ranges.length >= 100}
              onClick={() =>
                setRanges((rows) => [
                  ...rows,
                  { page_start: 1, page_end: pageCount, topic_id: null, label: '' },
                ])
              }
            >
              Thêm khoảng trang
            </button>
          )}
          <p className="muted">
            Trang PDF bắt đầu từ1, có thể khác số in trên sách. Khoảng ngoài lựa chọn sẽ không được
            dùng trả lời. Không bắt buộc phân chương.
          </p>
          <button className="button button-primary" disabled={!dirty}>
            {busy ? 'Đang lưu…' : 'Lưu phạm vi nguồn'}
          </button>
          <button type="button" className="button button-secondary" onClick={reset}>
            Hủy sửa và tải phạm vi hiện tại
          </button>
        </fieldset>
      </form>
    </details>
  )
}

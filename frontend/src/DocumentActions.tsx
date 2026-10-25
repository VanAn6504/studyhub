import { useState } from 'react'
import type { FormEvent } from 'react'
import { request } from './api'
import type { LearningDocument } from './learningTypes'

export default function DocumentActions({
  document,
  csrfToken,
  onSaved,
  onDeleted,
  onFailure,
}: {
  document: LearningDocument
  csrfToken: string
  onSaved: (document: LearningDocument, replaced: boolean) => void
  onDeleted: () => void
  onFailure: (error: unknown) => void
}) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ code: document.code, title: document.title })
  const [busy, setBusy] = useState(false)
  const [replaceFile, setReplaceFile] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      let updated: LearningDocument
      if (replaceFile) {
        if (!file) throw new Error('Hãy chọn PDF mới trước khi xóa file cũ.')
        if (file.size > 20 * 1024 * 1024) throw new Error('PDF tối đa 20 MiB.')
        const body = new FormData()
        body.append('code', form.code)
        body.append('title', form.title)
        body.append('file', file)
        updated = await request<LearningDocument>(`/documents/${document.id}/file`, {
          method: 'PUT',
          csrfToken,
          body,
        })
      } else {
        updated = await request<LearningDocument>(`/documents/${document.id}`, {
          method: 'PATCH',
          csrfToken,
          body: form,
        })
      }
      setEditing(false)
      setFile(null)
      onSaved(updated, replaceFile)
    } catch (error) {
      onFailure(error)
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (
      !window.confirm(
        `Xóa vĩnh viễn “${document.title}” và tất cả file PDF của tài liệu? Không thể khôi phục. Liên kết trong chủ đề và nguồn trợ giảng sẽ bị xóa; điểm và log học tập được giữ.`,
      )
    )
      return
    setBusy(true)
    try {
      await request(`/documents/${document.id}`, { method: 'DELETE', csrfToken })
      onDeleted()
    } catch (error) {
      onFailure(error)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="document-management">
      <div className="workspace-actions">
        <button
          className="button button-secondary"
          disabled={busy}
          onClick={() => {
            setForm({ code: document.code, title: document.title })
            setReplaceFile(false)
            setFile(null)
            setEditing((v) => !v)
          }}
        >
          Chỉnh sửa thông tin
        </button>
        <button
          className="button button-secondary document-delete"
          disabled={busy}
          onClick={() => void remove()}
        >
          Xóa tài liệu
        </button>
      </div>
      {editing && (
        <form className="learning-form" onSubmit={save}>
          <fieldset disabled={busy}>
            <label>
              Mã tài liệu
              <input
                required
                maxLength={64}
                pattern="[A-Za-z0-9]([A-Za-z0-9_]|-)*"
                value={form.code}
                onChange={(e) => setForm((v) => ({ ...v, code: e.target.value }))}
              />
            </label>
            <label>
              Tên tài liệu
              <input
                required
                maxLength={200}
                value={form.title}
                onChange={(e) => setForm((v) => ({ ...v, title: e.target.value }))}
              />
            </label>
            <p className="muted">
              File hiện tại: {document.versions[0]?.original_filename || 'PDF'}
              {document.versions.length > 1 ? ` · ${document.versions.length} phiên bản` : ''}
            </p>
            <label className="review-confirm">
              <input
                type="checkbox"
                checked={replaceFile}
                onChange={(e) => {
                  setReplaceFile(e.target.checked)
                  setFile(null)
                }}
              />
              Thay file PDF — xóa file cũ
            </label>
            {replaceFile && (
              <>
                <label>
                  PDF thay thế
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    required
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </label>
                <p className="notice">
                  Khi lưu, các file PDF cũ sẽ bị xóa vĩnh viễn. Tài liệu về nháp; bạn cần gắn lại
                  vào chủ đề và công bố sau khi kiểm tra. Điểm và log cũ được giữ, nguồn PDF cũ
                  trong quiz sẽ không mở được.
                </p>
              </>
            )}
            <div className="workspace-actions">
              <button className="button button-primary">
                {busy ? 'Đang lưu…' : 'Lưu thông tin'}
              </button>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setEditing(false)}
              >
                Hủy chỉnh sửa
              </button>
            </div>
          </fieldset>
        </form>
      )}
    </div>
  )
}

import { useState } from 'react'
import type { FormEvent } from 'react'
import { request } from './api'
import type { Topic } from './api'
export default function TopicEditor({
  courseId,
  topic,
  topics,
  csrfToken,
  onSaved,
  onFailure,
}: {
  courseId: string
  topic?: Topic
  topics: Topic[]
  csrfToken: string
  onSaved: (id: string) => void
  onFailure: (value: unknown) => void
}) {
  const [id, setId] = useState(topic?.id || '')
  const [form, setForm] = useState({
    code: topic?.code || '',
    title: topic?.title || '',
    order: topic?.order_index || Math.max(0, ...topics.map((t) => t.order_index)) + 1,
    objectives: topic?.objectives.join('\n') || '',
  })
  const [prerequisites, setPrerequisites] = useState(topic?.prerequisite_topic_ids || [])
  const [busy, setBusy] = useState(false)
  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    try {
      const saved = await request<Topic>(id ? `/topics/${id}` : `/courses/${courseId}/topics`, {
        method: id ? 'PATCH' : 'POST',
        csrfToken,
        body: {
          code: form.code.trim(),
          title: form.title.trim(),
          order_index: form.order,
          objectives: form.objectives
            .split('\n')
            .map((s) => s.trim())
            .filter(Boolean),
        },
      })
      setId(saved.id)
      await request(`/topics/${saved.id}/prerequisites`, {
        method: 'PUT',
        csrfToken,
        body: { prerequisite_topic_ids: prerequisites },
      })
      onSaved(saved.id)
    } catch (value) {
      onFailure(value)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="learning-form workspace-form" onSubmit={save}>
      <fieldset disabled={busy}>
        <label>
          Tên chủ đề
          <input
            required
            maxLength={200}
            value={form.title}
            onChange={(e) => setForm((v) => ({ ...v, title: e.target.value }))}
          />
        </label>
        <div className="learning-form-grid">
          <label>
            Mã chủ đề
            <input
              required
              pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
              maxLength={64}
              value={form.code}
              onChange={(e) => setForm((v) => ({ ...v, code: e.target.value }))}
            />
          </label>
          <label>
            Thứ tự
            <input
              type="number"
              required
              min={1}
              max={1000}
              value={form.order}
              onChange={(e) => setForm((v) => ({ ...v, order: Number(e.target.value) }))}
            />
          </label>
        </div>
        <label>
          Mục tiêu học tập · mỗi dòng một mục
          <textarea
            rows={4}
            value={form.objectives}
            onChange={(e) => setForm((v) => ({ ...v, objectives: e.target.value }))}
          />
        </label>
        <details>
          <summary>Kiến thức tiên quyết</summary>
          {topics
            .filter((t) => t.id !== id)
            .map((t) => (
              <label className="workspace-checkbox" key={t.id}>
                <input
                  type="checkbox"
                  checked={prerequisites.includes(t.id)}
                  onChange={(e) =>
                    setPrerequisites((v) =>
                      e.target.checked ? [...v, t.id] : v.filter((x) => x !== t.id),
                    )
                  }
                />
                {t.code} · {t.title}
              </label>
            ))}
          {topics.filter((t) => t.id !== id).length === 0 && (
            <p className="muted">Chưa có chủ đề khác để chọn.</p>
          )}
        </details>
        <button className="button button-primary">{busy ? 'Đang lưu…' : 'Lưu chủ đề'}</button>
      </fieldset>
    </form>
  )
}

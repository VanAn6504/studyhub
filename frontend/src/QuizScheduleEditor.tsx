import { useEffect, useState } from 'react'
import { errorMessage, request } from './api'
import type { CourseRun } from './api'
import type { QuizDeadline } from './learningTypes'

export default function QuizScheduleEditor({ run, csrfToken }: { run: CourseRun; csrfToken: string }) {
  const [items, setItems] = useState<QuizDeadline[] | null>(null)
  const [dates, setDates] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [reload, setReload] = useState(0)
  const base = `/teaching/runs/${run.id}/quiz-schedule`
  useEffect(() => {
    let stopped = false
    request<{ items: QuizDeadline[] }>(base)
      .then(({ items }) => { if (!stopped) setItems(items) })
      .catch(error => { if (!stopped) setError(errorMessage(error)) })
    return () => { stopped = true }
  }, [base, reload])

  async function save(item: QuizDeadline, value: string | null) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const updated = await request<QuizDeadline>(`${base}/${item.quiz_version_id}`, {
        method: 'PUT', csrfToken, body: { due_local: value },
      })
      setItems(current => current?.map(row => row.quiz_version_id === item.quiz_version_id ? updated : row) ?? null)
      setDates(current => ({ ...current, [item.quiz_version_id]: updated.due_local || '' }))
      setMessage(value ? 'Đã lưu hạn nộp.' : 'Đã bỏ hạn nộp.')
    } catch (error) { setError(errorMessage(error)) }
    finally { setBusy(false) }
  }

  return <section className="class-members">
    <h4>Lịch quiz · {run.code}</h4>
    <p className="muted">Nhập theo múi giờ lớp {run.timezone}. Hạn nộp dùng để theo dõi tiến độ.</p>
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    {message && <p role="status">{message}</p>}
    {!items && (error
      ? <button className="text-button" onClick={() => { setError(''); setReload(value => value + 1) }}>Tải lại lịch quiz</button>
      : <p role="status">Đang tải lịch quiz…</p>)}
    {items?.length === 0 && <p>Chưa có quiz công bố để đặt hạn.</p>}
    {items?.map(item => {
      const value = dates[item.quiz_version_id] ?? item.due_local ?? ''
      const label = `${item.topic_code} · ${item.title} · Quiz v${item.version}`
      return item.current ? <form className="learning-form workspace-row" key={item.quiz_version_id}
        onSubmit={event => { event.preventDefault(); if (value) void save(item, value) }}>
        <label>Hạn nộp {label}<input type="datetime-local" value={value} required disabled={busy}
          onChange={event => setDates(current => ({ ...current, [item.quiz_version_id]: event.target.value }))} /></label>
        <div className="workspace-actions">
          <button className="button button-secondary" disabled={busy || !value || value === item.due_local}>Lưu hạn nộp</button>
          {item.due_at && <button type="button" className="text-button" disabled={busy}
            onClick={() => void save(item, null)}>Bỏ hạn nộp</button>}
        </div>
      </form> : <p key={item.quiz_version_id}>{label} · Phiên bản cũ · {new Date(item.due_at!).toLocaleString('vi-VN', { timeZone: run.timezone })}</p>
    })}
  </section>
}

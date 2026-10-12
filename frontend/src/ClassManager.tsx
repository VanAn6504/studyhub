import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { listAll, request } from './api'
import type { CourseRun } from './api'

type Member = {
  id: string
  student_id: string
  student_email: string
  display_name: string
  status: 'active' | 'inactive'
}
export default function ClassManager({
  run,
  csrfToken,
  onChanged,
  onFailure,
  onReport,
}: {
  run: CourseRun
  csrfToken: string
  onChanged: () => void
  onFailure: (error: unknown) => void
  onReport: () => void
}) {
  const [open, setOpen] = useState(false)
  const [members, setMembers] = useState<Member[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [email, setEmail] = useState('')
  const [reload, setReload] = useState(0)
  const [message, setMessage] = useState('')
  useEffect(() => {
    if (!open) return
    let stopped = false
    setLoading(true)
    listAll<Member>(`/course-runs/${run.id}/enrollments`)
      .then((value) => {
        if (!stopped) setMembers(value)
      })
      .catch((error) => {
        if (!stopped) onFailure(error)
      })
      .finally(() => {
        if (!stopped) setLoading(false)
      })
    return () => {
      stopped = true
    }
  }, [open, run.id, reload])
  async function mutate(action: () => Promise<unknown>, text: string) {
    setBusy(true)
    setMessage('')
    try {
      await action()
      setMessage(text)
      setReload((v) => v + 1)
      onChanged()
    } catch (error) {
      onFailure(error)
    } finally {
      setBusy(false)
    }
  }
  async function enroll(event: FormEvent) {
    event.preventDefault()
    await mutate(async () => {
      await request(`/course-runs/${run.id}/enrollments`, {
        method: 'POST',
        csrfToken,
        body: { student_email: email.trim() },
      })
      setEmail('')
    }, 'Sinh viên đã được thêm vào lớp.')
  }
  const editable = run.data_origin === 'real'
  return (
    <article className="class-card">
      <div className="section-heading">
        <div>
          <h3>{run.code}</h3>
          <p className="muted">
            Bắt đầu {new Date(run.course_run_start_date + 'T00:00:00').toLocaleDateString('vi-VN')}{' '}
            · {run.student_count || 0} sinh viên
          </p>
        </div>
        <span className="workspace-badge">
          {run.data_origin === 'synthetic'
            ? 'Dữ liệu mô phỏng'
            : run.status === 'active'
              ? 'Đang mở'
              : run.status === 'draft'
                ? 'Bản nháp'
                : 'Đã đóng'}
        </span>
      </div>
      <div className="workspace-actions">
        <button
          className="button button-secondary"
          onClick={() => setOpen((v) => !v)}
          disabled={busy}
        >
          {open ? 'Đóng danh sách' : 'Danh sách sinh viên'}
        </button>
        <button className="button button-secondary" onClick={onReport} disabled={busy}>
          Xem kết quả lớp
        </button>
        {editable && (
          <button
            className="button button-primary"
            disabled={busy}
            onClick={() =>
              void mutate(
                () =>
                  request(`/course-runs/${run.id}`, {
                    method: 'PATCH',
                    csrfToken,
                    body: { status: run.status === 'active' ? 'closed' : 'active' },
                  }),
                run.status === 'active' ? 'Đã đóng lớp.' : 'Đã mở lớp.',
              )
            }
          >
            {run.status === 'active' ? 'Đóng lớp' : 'Mở lớp'}
          </button>
        )}
      </div>
      {message && (
        <p className="notice notice-success" role="status">
          {message}
        </p>
      )}
      {open && (
        <div className="class-members">
          {loading ? (
            <p role="status">Đang tải danh sách sinh viên…</p>
          ) : !members.length ? (
            <p className="muted">Lớp chưa có sinh viên.</p>
          ) : (
            members.map((member) => (
              <div className="workspace-row" key={member.id}>
                <div>
                  <strong>{member.display_name}</strong>
                  <p>
                    {member.student_email} ·{' '}
                    {member.status === 'active' ? 'Đang đăng ký' : 'Đã ngừng đăng ký'}
                  </p>
                </div>
                {editable && (
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      void mutate(
                        () =>
                          request(`/enrollments/${member.id}`, {
                            method: 'PATCH',
                            csrfToken,
                            body: { status: member.status === 'active' ? 'inactive' : 'active' },
                          }),
                        'Đã cập nhật đăng ký học.',
                      )
                    }
                  >
                    {member.status === 'active' ? 'Ngừng đăng ký' : 'Kích hoạt lại'}
                  </button>
                )}
              </div>
            ))
          )}
          {editable && (
            <form className="learning-form" onSubmit={enroll}>
              <fieldset disabled={busy}>
                <label>
                  Email sinh viên đã có tài khoản
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </label>
                <button className="button button-secondary">Thêm sinh viên</button>
              </fieldset>
            </form>
          )}
        </div>
      )}
    </article>
  )
}

import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, errorMessage, request } from '../api'
import type { Session } from '../api'
import type { Profile } from './types'
import { FieldError, Link, Notice, State, useFormGuard, useResource } from './ui'

export function ProfilePage({
  session,
  onUpdated,
}: {
  session: Session
  onUpdated: (session: Session) => void
}) {
  const resource = useResource<Profile>('/me/profile'),
    [form, setForm] = useState({ display_name: '', bio: '' }),
    [saved, setSaved] = useState(form),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState('')
  useEffect(() => {
    if (resource.data) {
      const value = { display_name: resource.data.display_name, bio: resource.data.bio }
      setForm(value)
      setSaved(value)
    }
  }, [resource.data])
  const guard = useFormGuard(JSON.stringify(form) !== JSON.stringify(saved), busy)
  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const data = await request<Profile>('/me/profile', {
        method: 'PATCH',
        csrfToken: session.csrf_token,
        body: form,
      })
      setSaved({ display_name: data.display_name, bio: data.bio })
      setForm({ display_name: data.display_name, bio: data.bio })
      onUpdated({ ...session, user: { ...session.user, display_name: data.display_name } })
      setMessage('Đã lưu hồ sơ riêng tư của bạn.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="site-account-page">
      <span className="eyebrow">TÀI KHOẢN RIÊNG TƯ</span>
      <h1>Hồ sơ của bạn</h1>
      <p>
        Tên giảng viên có thể xuất hiện trên học phần đã công bố. Giới thiệu cá nhân và email không
        mặc định công khai.
      </p>
      <State {...resource}>
        {resource.data && (
          <section className="site-panel">
            <div className="site-profile-heading">
              <span className="site-avatar" aria-hidden="true">
                {form.display_name.slice(0, 2).toLocaleUpperCase('vi')}
              </span>
              <div>
                <strong>{resource.data.email}</strong>
                <p>{resource.data.role === 'teacher' ? 'Giảng viên' : 'Sinh viên'}</p>
              </div>
            </div>
            {error && <Notice>{error}</Notice>}
            {guard && <Notice>{guard}</Notice>}
            {message && <Notice kind="success">{message}</Notice>}
            <form className="site-form" onSubmit={save}>
              <fieldset disabled={busy}>
                <label>
                  Tên hiển thị
                  <input
                    required
                    maxLength={100}
                    autoComplete="name"
                    value={form.display_name}
                    onChange={(e) => setForm({ ...form, display_name: e.target.value })}
                  />
                </label>
                <label>
                  Giới thiệu ngắn
                  <textarea
                    aria-label="Giới thiệu ngắn"
                    maxLength={1200}
                    value={form.bio}
                    onChange={(e) => setForm({ ...form, bio: e.target.value })}
                  />
                </label>
                <label>
                  Email
                  <input readOnly value={resource.data.email} />
                </label>
                <label>
                  Vai trò
                  <input
                    readOnly
                    value={resource.data.role === 'teacher' ? 'Giảng viên' : 'Sinh viên'}
                  />
                </label>
                <div className="site-actions">
                  <button className="button button-primary">
                    {busy ? 'Đang lưu…' : 'Lưu hồ sơ'}
                  </button>
                  <button
                    className="button button-secondary"
                    type="button"
                    onClick={() => {
                      setForm(saved)
                      setError('')
                      setMessage('')
                    }}
                  >
                    Hủy chỉnh sửa
                  </button>
                </div>
              </fieldset>
            </form>
          </section>
        )}
      </State>
      <Link to="/settings/security">Đổi mật khẩu →</Link>
    </div>
  )
}
export function SecurityPage({ session, onChanged }: { session: Session; onChanged: () => void }) {
  const [current, setCurrent] = useState(''),
    [password, setPassword] = useState(''),
    [confirmation, setConfirmation] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [fields, setFields] = useState<Record<string, string>>({})
  const guard = useFormGuard(!!(current || password || confirmation), busy)
  async function save(e: FormEvent) {
    e.preventDefault()
    setError('')
    setFields({})
    if (password !== confirmation) {
      setFields({ confirmation: 'Mật khẩu xác nhận chưa khớp.' })
      document.getElementById('password-confirm')?.focus()
      return
    }
    setBusy(true)
    try {
      await request('/me/password', {
        method: 'POST',
        csrfToken: session.csrf_token,
        body: { current_password: current, new_password: password },
      })
      setCurrent('')
      setPassword('')
      setConfirmation('')
      onChanged()
    } catch (e) {
      setError(errorMessage(e))
      if (e instanceof ApiError && e.code === 'CURRENT_PASSWORD_INVALID') {
        setFields({ current: 'Mật khẩu hiện tại không đúng.' })
        document.getElementById('password-current')?.focus()
      }
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="site-account-page">
      <h1>Bảo mật tài khoản</h1>
      <p>
        Đổi mật khẩu sẽ thu hồi tất cả phiên đăng nhập hiện tại, kể cả phiên này. Bạn sẽ đăng nhập
        lại bằng mật khẩu mới.
      </p>
      <section className="site-panel">
        {error && <Notice>{error}</Notice>}
        {guard && <Notice>{guard}</Notice>}
        <form className="site-form" onSubmit={save}>
          <fieldset disabled={busy}>
            <label>
              Mật khẩu hiện tại
              <input
                id="password-current"
                aria-label="Mật khẩu hiện tại"
                type="password"
                required
                maxLength={128}
                autoComplete="current-password"
                value={current}
                aria-invalid={!!fields.current}
                aria-describedby={fields.current ? 'password-current-error' : undefined}
                onChange={(e) => setCurrent(e.target.value)}
              />
              <FieldError id="password-current-error" message={fields.current} />
            </label>
            <label>
              Mật khẩu mới
              <input
                type="password"
                required
                minLength={10}
                maxLength={128}
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            <label>
              Nhập lại mật khẩu mới
              <input
                id="password-confirm"
                aria-label="Nhập lại mật khẩu mới"
                type="password"
                required
                minLength={10}
                maxLength={128}
                autoComplete="new-password"
                value={confirmation}
                aria-invalid={!!fields.confirmation}
                aria-describedby={fields.confirmation ? 'password-confirm-error' : undefined}
                onChange={(e) => setConfirmation(e.target.value)}
              />
              <FieldError id="password-confirm-error" message={fields.confirmation} />
            </label>
            <button className="button button-primary">
              {busy ? 'Đang đổi…' : 'Đổi mật khẩu và đăng nhập lại'}
            </button>
          </fieldset>
        </form>
      </section>
      <Link to="/profile">Quay lại hồ sơ</Link>
    </div>
  )
}

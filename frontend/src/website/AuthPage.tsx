import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, errorMessage, request } from '../api'
import type { Session } from '../api'
import { navigate, safeReturn } from './navigation'
import { Link, Notice } from './ui'

export default function AuthPage({
  mode,
  next,
  initialMessage,
  onLogin,
}: {
  mode: 'login' | 'register'
  next: string | null
  initialMessage: string
  onLogin: (session: Session, next: string) => void
}) {
  const [email, setEmail] = useState(''),
    [password, setPassword] = useState(''),
    [name, setName] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(initialMessage)
  useEffect(() => {
    setPassword('')
    setError('')
  }, [mode])
  const target = safeReturn(next, '/dashboard'),
    other = (mode === 'login' ? '/register' : '/login') + '?next=' + encodeURIComponent(target)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      if (mode === 'register') {
        await request('/auth/register', {
          method: 'POST',
          body: { email, password, display_name: name },
        })
        setPassword('')
        setMessage('Tài khoản đã được tạo. Đăng nhập để tiếp tục; bạn chưa được ghi danh vào lớp.')
        await navigate('/login?next=' + encodeURIComponent(target), { replace: true })
      } else {
        const value = await request<Session>('/auth/login', {
          method: 'POST',
          body: { email, password },
        })
        setPassword('')
        onLogin(value, safeReturn(next, value.user.role === 'teacher' ? '/teaching' : '/dashboard'))
      }
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.status === 401
          ? 'Email hoặc mật khẩu không đúng.'
          : errorMessage(failure),
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="site-auth">
      <section>
        <span className="eyebrow">STUDYHUB · KHÔNG GIAN HỌC TẬP</span>
        <h1>
          Học từng chủ đề.
          <br />
          Vững từng bước.
        </h1>
        <p>Tài khoản giúp bạn tham gia lớp, đọc tài liệu, làm quiz và theo dõi việc học.</p>
        <p>Đăng nhập không tự gửi yêu cầu ghi danh. Bạn sẽ trở lại lớp đã chọn để xác nhận.</p>
        <Link to="/courses">Khám phá học phần →</Link>
      </section>
      <section className="site-panel">
        <h2>{mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản sinh viên'}</h2>
        {message && <Notice kind="info">{message}</Notice>}
        {error && <Notice>{error}</Notice>}
        <form className="site-form" onSubmit={submit}>
          <fieldset disabled={busy}>
            {mode === 'register' && (
              <label>
                Tên hiển thị
                <input
                  required
                  maxLength={100}
                  autoComplete="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            )}
            <label>
              Email
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Mật khẩu
              <input
                type="password"
                required
                minLength={mode === 'register' ? 10 : 1}
                maxLength={128}
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {mode === 'register' && (
              <p className="site-muted">
                Mật khẩu từ10 đến128 ký tự. Vai trò sinh viên được hệ thống cấp; giảng viên không
                đăng ký qua form này.
              </p>
            )}
            <button className="button button-primary">
              {busy ? 'Đang xử lý…' : mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}
            </button>
          </fieldset>
        </form>
        <p>
          {mode === 'login' ? 'Chưa có tài khoản?' : 'Đã có tài khoản?'}{' '}
          <Link to={other}>{mode === 'login' ? 'Đăng ký' : 'Đăng nhập'}</Link>
        </p>
        <p className="site-muted">
          Quên mật khẩu: liên hệ giảng viên phụ trách để được hướng dẫn. Chức năng gửi email đặt lại
          mật khẩu chưa được cung cấp.
        </p>
      </section>
    </div>
  )
}

import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ApiError, errorMessage, request } from './api'
import type { Session } from './api'
import Dashboard from './CourseDashboard'

function Icon({
  name,
  size = 20,
}: {
  name: 'book' | 'grid' | 'arrow' | 'exit' | 'plus' | 'check' | 'calendar' | 'users'
  size?: number
}) {
  const paths = {
    book: (
      <>
        <path d="M3 4h7a3 3 0 0 1 3 3v14a4 4 0 0 0-3-2H3V4Z" />
        <path d="M21 4h-5a3 3 0 0 0-3 3v14a4 4 0 0 1 3-2h5V4Z" />
      </>
    ),
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    arrow: (
      <>
        <path d="M5 12h14m-5-5 5 5-5 5" />
      </>
    ),
    exit: (
      <>
        <path d="M10 4H4v16h6m4-12 4 4-4 4m-6-4h10" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    check: <path d="m5 12 4 4L19 6" />,
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M7 3v4m10-4v4M3 11h18m-11 4h1m4 0h1" />
      </>
    ),
    users: (
      <>
        <circle cx="9" cy="8" r="3" />
        <path d="M3 20v-3a6 6 0 0 1 12 0v3m1-15a3 3 0 0 1 0 6m2 3a6 6 0 0 1 3 5" />
      </>
    ),
  }
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}

function Brand({ light = false }: { light?: boolean }) {
  return (
    <div className={`brand${light ? ' brand-light' : ''}`}>
      <span className="brand-mark">
        <Icon name="book" size={24} />
      </span>
      <span>
        StudyHub<span className="brand-dot">.</span>
      </span>
    </div>
  )
}

function Notice({ children, kind = 'error' }: { children: ReactNode; kind?: 'error' | 'success' }) {
  return (
    <div className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}

function Loading({ label = 'Đang tải dữ liệu…' }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" />
      {label}
    </div>
  )
}

function AuthScreen({
  onLogin,
  initialMessage,
}: {
  onLogin: (session: Session) => void
  initialMessage: string
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(initialMessage)
  const [success, setSuccess] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSuccess('')
    setBusy(true)
    try {
      if (mode === 'register') {
        await request('/auth/register', {
          method: 'POST',
          body: { email: email.trim(), password, display_name: name.trim() },
        })
        setPassword('')
        setMode('login')
        setSuccess('Tài khoản đã được tạo. Đăng nhập để vào không gian học tập của bạn.')
      } else {
        const session = await request<Session>('/auth/login', {
          method: 'POST',
          body: { email: email.trim(), password },
        })
        setPassword('')
        onLogin(session)
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

  function changeMode() {
    setMode(mode === 'login' ? 'register' : 'login')
    setPassword('')
    setError('')
    setSuccess('')
  }

  return (
    <main className="auth-shell">
      <section className="auth-intro" aria-label="Giới thiệu StudyHub">
        <Brand light />
        <div className="intro-content">
          <span className="eyebrow light">KHÔNG GIAN HỌC TẬP CỦA BẠN</span>
          <h1>
            Học từng chủ đề.
            <br />
            <span>Vững từng bước.</span>
          </h1>
          <p>Tập trung vào kiến thức cần học, trong một không gian được tổ chức rõ ràng.</p>
          <div className="course-illustration" aria-hidden="true">
            <div className="illustration-orbit orbit-one" />
            <div className="illustration-orbit orbit-two" />
            <div className="illustration-note">
              <span className="note-line" />
              <span className="note-line short" />
              <span className="note-line" />
              <span className="note-line shorter" />
              <span className="note-check">
                <Icon name="check" />
              </span>
            </div>
            <div className="illustration-book">
              <Icon name="book" size={50} />
            </div>
            <span className="illustration-spark">✦</span>
          </div>
          <div className="intro-course">
            <span className="intro-course-label">HỌC PHẦN MẪU</span>
            <strong>
              Phát triển ứng dụng di động
              <br />
              đa nền tảng
            </strong>
            <span>Flutter & Dart</span>
          </div>
        </div>
        <p className="intro-footer">Một bước nhỏ hôm nay, một nền tảng vững ngày mai.</p>
      </section>
      <section className="auth-panel">
        <div className="mobile-brand">
          <Brand />
        </div>
        <div className="auth-card">
          <span className="eyebrow">CHÀO MỪNG ĐẾN STUDYHUB</span>
          <h2>{mode === 'login' ? 'Tiếp tục hành trình học tập' : 'Tạo tài khoản sinh viên'}</h2>
          <p className="muted auth-description">
            {mode === 'login'
              ? 'Đăng nhập để xem học phần và các chủ đề của bạn.'
              : 'Bắt đầu với tài khoản của bạn. Giảng viên sẽ thêm bạn vào lớp học.'}
          </p>
          {error && <Notice>{error}</Notice>}
          {success && <Notice kind="success">{success}</Notice>}
          <form onSubmit={submit} className="auth-form">
            {mode === 'register' && (
              <label>
                Họ và tên
                <input
                  name="display_name"
                  autoComplete="name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  required
                  minLength={1}
                  maxLength={100}
                  placeholder="Nguyễn Văn An"
                  disabled={busy}
                />
              </label>
            )}
            <label>
              Email
              <input
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                maxLength={254}
                placeholder="ban@example.com"
                disabled={busy}
              />
            </label>
            <label>
              Mật khẩu
              <input
                name="password"
                type="password"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={mode === 'register' ? 10 : undefined}
                maxLength={128}
                placeholder={mode === 'register' ? 'Ít nhất 10 ký tự' : 'Nhập mật khẩu của bạn'}
                disabled={busy}
              />
            </label>
            <button className="button button-primary auth-submit" disabled={busy}>
              {busy ? (
                <>
                  <span className="spinner" />
                  Đang xử lý…
                </>
              ) : (
                <>
                  {mode === 'login' ? 'Đăng nhập' : 'Tạo tài khoản'}
                  <Icon name="arrow" />
                </>
              )}
            </button>
          </form>
          <p className="auth-switch">
            {mode === 'login' ? 'Chưa có tài khoản?' : 'Đã có tài khoản?'}{' '}
            <button className="text-button" type="button" onClick={changeMode} disabled={busy}>
              {mode === 'login' ? 'Đăng ký' : 'Đăng nhập'}
            </button>
          </p>
        </div>
        <div className="auth-footnote">StudyHub · Nền tảng học tập trực tuyến</div>
      </section>
    </main>
  )
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [restoring, setRestoring] = useState(true)
  const [restoreError, setRestoreError] = useState('')
  const [authMessage, setAuthMessage] = useState('')
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    let cancelled = false
    setRestoring(true)
    setRestoreError('')
    request<Session>('/auth/me')
      .then((current) => {
        if (!cancelled) setSession(current)
      })
      .catch((failure) => {
        if (cancelled) return
        setSession(null)
        if (!(failure instanceof ApiError && failure.status === 401))
          setRestoreError(errorMessage(failure))
      })
      .finally(() => {
        if (!cancelled) setRestoring(false)
      })
    return () => {
      cancelled = true
    }
  }, [retry])

  if (restoring)
    return (
      <div className="startup-screen">
        <Brand />
        <Loading label="Đang mở không gian học tập…" />
      </div>
    )
  if (restoreError)
    return (
      <div className="startup-screen">
        <Brand />
        <div className="startup-error">
          <Notice>{restoreError}</Notice>
          <button
            className="button button-primary"
            onClick={() => setRetry((current) => current + 1)}
          >
            Kết nối lại
          </button>
        </div>
      </div>
    )
  if (!session)
    return (
      <AuthScreen
        initialMessage={authMessage}
        onLogin={(current) => {
          setSession(current)
          setAuthMessage('')
        }}
      />
    )
  return (
    <Dashboard
      key={session.user.id}
      session={session}
      onLogout={() => {
        setSession(null)
        setAuthMessage('')
      }}
      onExpired={() => {
        setSession(null)
        setAuthMessage('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
      }}
    />
  )
}

import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { ApiError, errorMessage, listAll, request } from './api'
import type { Course, CourseRun, Session, Topic } from './api'

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

function localDate() {
  const today = new Date()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${today.getFullYear()}-${month}-${day}`
}

function formatDate(value: string) {
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
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
              : 'Bắt đầu với tài khoản của bạn. Giảng viên sẽ thêm bạn vào lượt học.'}
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

function StatusBadge({ run }: { run: CourseRun }) {
  const labels = { active: 'Đang mở', draft: 'Bản nháp', closed: 'Đã đóng' }
  return (
    <div className="run-badges">
      <span className={`badge badge-${run.status}`}>
        <i />
        {labels[run.status]}
      </span>
      {run.data_origin === 'synthetic' && (
        <span className="badge badge-synthetic">Dữ liệu mô phỏng</span>
      )}
    </div>
  )
}

function Topics({
  topics,
  loading,
  error,
  onRetry,
}: {
  topics: Topic[]
  loading: boolean
  error: string
  onRetry: () => void
}) {
  if (loading) return <Loading label="Đang tải các chủ đề…" />
  if (error)
    return (
      <>
        <Notice>{error}</Notice>
        <button className="button button-secondary" onClick={onRetry}>
          Thử lại
        </button>
      </>
    )
  if (!topics.length)
    return (
      <div className="empty-state">
        <Icon name="book" size={30} />
        <h3>Chưa có chủ đề</h3>
        <p>Các chủ đề sẽ xuất hiện khi giảng viên chuẩn bị nội dung.</p>
      </div>
    )
  const byId = new Map(topics.map((topic) => [topic.id, topic.code]))
  return (
    <div className="topic-list">
      {topics.map((topic) => (
        <article className="topic-card" key={topic.id}>
          <span className="topic-number">{String(topic.order_index).padStart(2, '0')}</span>
          <div className="topic-content">
            <div className="topic-title-row">
              <span className="topic-code">{topic.code}</span>
              <h3>{topic.title}</h3>
            </div>
            <ul className="objectives">
              {topic.objectives.map((objective, index) => (
                <li key={index}>{objective}</li>
              ))}
            </ul>
            <div className="prerequisites">
              <span>Kiến thức tiên quyết</span>
              {topic.prerequisite_topic_ids.length ? (
                topic.prerequisite_topic_ids.map((id) => (
                  <span className="prerequisite-chip" key={id}>
                    {byId.get(id) || 'Chủ đề liên quan'}
                  </span>
                ))
              ) : (
                <span className="no-prerequisite">Không có</span>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  )
}

function Dashboard({
  session,
  onLogout,
  onExpired,
}: {
  session: Session
  onLogout: () => void
  onExpired: () => void
}) {
  const isTeacher = session.user.role === 'teacher'
  const [courses, setCourses] = useState<Course[]>([])
  const [runs, setRuns] = useState<CourseRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [reload, setReload] = useState(0)
  const [selectedRunId, setSelectedRunId] = useState('')
  const [selectedCourseId, setSelectedCourseId] = useState('')
  const [topics, setTopics] = useState<Topic[]>([])
  const [topicLoading, setTopicLoading] = useState(false)
  const [topicError, setTopicError] = useState('')
  const [topicReload, setTopicReload] = useState(0)
  const [createOpen, setCreateOpen] = useState(false)
  const [code, setCode] = useState('')
  const [startDate, setStartDate] = useState(localDate)
  const [timezone, setTimezone] = useState('Asia/Ho_Chi_Minh')
  const [studentEmail, setStudentEmail] = useState('')
  const [mutation, setMutation] = useState('')
  const [formError, setFormError] = useState('')
  const [loggingOut, setLoggingOut] = useState(false)
  const selectedRun = runs.find((run) => run.id === selectedRunId)
  const selectedCourse = courses.find((course) => course.id === selectedCourseId)

  function handleFailure(failure: unknown): string {
    if (failure instanceof ApiError && failure.status === 401) onExpired()
    return errorMessage(failure)
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    Promise.all([
      listAll<CourseRun>('/course-runs'),
      isTeacher ? listAll<Course>('/courses') : Promise.resolve([]),
    ])
      .then(([loadedRuns, loadedCourses]) => {
        if (cancelled) return
        setRuns(loadedRuns)
        setCourses(loadedCourses)
        setSelectedCourseId((current) =>
          loadedCourses.some((course) => course.id === current)
            ? current
            : loadedCourses[0]?.id || '',
        )
        setSelectedRunId((current) =>
          loadedRuns.some((run) => run.id === current)
            ? current
            : !isTeacher
              ? loadedRuns[0]?.id || ''
              : '',
        )
      })
      .catch((failure) => {
        if (!cancelled) setError(handleFailure(failure))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // The session changes by remounting this component after login/logout.
  }, [reload, isTeacher])

  useEffect(() => {
    let cancelled = false
    const path = selectedRunId
      ? `/course-runs/${selectedRunId}/topics`
      : isTeacher && selectedCourseId
        ? `/courses/${selectedCourseId}/topics`
        : ''
    setTopics([])
    setTopicError('')
    if (!path) {
      setTopicLoading(false)
      return
    }
    setTopicLoading(true)
    listAll<Topic>(path)
      .then((loaded) => {
        if (!cancelled) setTopics(loaded.sort((a, b) => a.order_index - b.order_index))
      })
      .catch((failure) => {
        if (!cancelled) setTopicError(handleFailure(failure))
      })
      .finally(() => {
        if (!cancelled) setTopicLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [selectedRunId, selectedCourseId, isTeacher, topicReload])

  async function logout() {
    setLoggingOut(true)
    setError('')
    try {
      await request('/auth/logout', { method: 'POST', csrfToken: session.csrf_token })
      onLogout()
    } catch (failure) {
      setError(handleFailure(failure))
    } finally {
      setLoggingOut(false)
    }
  }

  async function createRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedCourseId || mutation) return
    setMutation('create')
    setFormError('')
    setSuccess('')
    try {
      const run = await request<CourseRun>(`/courses/${selectedCourseId}/runs`, {
        method: 'POST',
        csrfToken: session.csrf_token,
        body: { code: code.trim(), course_run_start_date: startDate, timezone },
      })
      setCreateOpen(false)
      setCode('')
      setSelectedRunId(run.id)
      setReload((current) => current + 1)
      setSuccess('Đã tạo lượt học ở trạng thái bản nháp. Bạn có thể thêm sinh viên và mở lượt học.')
    } catch (failure) {
      setFormError(handleFailure(failure))
    } finally {
      setMutation('')
    }
  }

  async function activateRun() {
    if (!selectedRun || mutation) return
    setMutation('activate')
    setError('')
    setSuccess('')
    try {
      await request(`/course-runs/${selectedRun.id}`, {
        method: 'PATCH',
        csrfToken: session.csrf_token,
        body: { status: 'active' },
      })
      setReload((current) => current + 1)
      setSuccess('Lượt học đã mở cho sinh viên được thêm vào.')
    } catch (failure) {
      setError(handleFailure(failure))
    } finally {
      setMutation('')
    }
  }

  async function enroll(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedRun || mutation) return
    setMutation('enroll')
    setFormError('')
    setSuccess('')
    try {
      await request(`/course-runs/${selectedRun.id}/enrollments`, {
        method: 'POST',
        csrfToken: session.csrf_token,
        body: { student_email: studentEmail.trim() },
      })
      setStudentEmail('')
      setReload((current) => current + 1)
      setSuccess('Sinh viên đã có trong lượt học này.')
    } catch (failure) {
      setFormError(handleFailure(failure))
    } finally {
      setMutation('')
    }
  }

  function selectRun(run: CourseRun) {
    setSelectedRunId(run.id)
    if (isTeacher) setSelectedCourseId(run.course_id)
    setFormError('')
    setSuccess('')
    setStudentEmail('')
  }

  const visibleRuns = isTeacher ? runs.filter((run) => run.course_id === selectedCourseId) : runs
  const displayName = session.user.display_name.trim() || session.user.email
  const initials = displayName
    .split(/\s+/)
    .slice(-2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Brand light />
        <span className="sidebar-label">KHÔNG GIAN LÀM VIỆC</span>
        <a
          className="nav-item nav-active"
          href="#main-content"
          aria-label={isTeacher ? 'Quản lý học phần' : 'Học phần của tôi'}
        >
          <Icon name="grid" />
          {isTeacher ? 'Quản lý học phần' : 'Học phần của tôi'}
        </a>
        <div className="sidebar-note">
          <span className="sidebar-note-symbol">✦</span>
          <strong>
            Mỗi chủ đề,
            <br />
            một bước tiến.
          </strong>
          <p>Khám phá mục tiêu và kiến thức cần học theo từng bước.</p>
        </div>
        <div className="sidebar-bottom">
          <span className="sidebar-version">StudyHub · Bản phát triển</span>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="topbar-mobile">
            <Brand />
          </div>
          <span className="topbar-context">
            {isTeacher ? 'Không gian giảng viên' : 'Không gian sinh viên'}
          </span>
          <div className="account">
            <span className="avatar">{initials}</span>
            <div>
              <strong>{displayName}</strong>
              <span>{isTeacher ? 'Giảng viên' : 'Sinh viên'}</span>
            </div>
            <button
              className="icon-button"
              aria-label="Đăng xuất"
              title="Đăng xuất"
              onClick={logout}
              disabled={loggingOut}
            >
              <Icon name="exit" />
            </button>
          </div>
        </header>
        <main className="workspace" id="main-content">
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {isTeacher ? 'GIẢNG DẠY & QUẢN LÝ' : 'HỌC TẬP MỖI NGÀY'}
              </span>
              <h1>{isTeacher ? 'Quản lý học phần' : 'Học phần của tôi'}</h1>
              <p className="muted">
                {isTeacher
                  ? 'Tổ chức lượt học và chuẩn bị nội dung cho sinh viên.'
                  : 'Chọn lượt học để khám phá các chủ đề và mục tiêu.'}
              </p>
            </div>
            <span className="heading-icon">
              <Icon name="book" size={30} />
            </span>
          </div>
          {error && (
            <div className="feedback">
              <Notice>{error}</Notice>
              <button
                className="button button-secondary"
                onClick={() => setReload((current) => current + 1)}
              >
                Thử lại
              </button>
            </div>
          )}
          {success && <Notice kind="success">{success}</Notice>}
          {loading ? (
            <Loading />
          ) : (
            !error && (
              <>
                {isTeacher && courses.length > 0 && (
                  <div className="course-selector">
                    <label htmlFor="course-select">Học phần</label>
                    <select
                      id="course-select"
                      value={selectedCourseId}
                      onChange={(event) => {
                        setSelectedCourseId(event.target.value)
                        setSelectedRunId('')
                        setFormError('')
                        setCreateOpen(false)
                        setSuccess('')
                      }}
                    >
                      {courses.map((course) => (
                        <option value={course.id} key={course.id}>
                          {course.title}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                {isTeacher && !courses.length ? (
                  <div className="empty-state">
                    <Icon name="book" size={32} />
                    <h3>Chưa có học phần</h3>
                    <p>Chạy bước khởi tạo nội dung mẫu để đưa học phần vào hệ thống.</p>
                  </div>
                ) : (
                  <>
                    <section className="course-banner">
                      <div>
                        <span className="banner-caption">
                          {isTeacher ? 'HỌC PHẦN ĐANG QUẢN LÝ' : 'LƯỢT HỌC ĐÃ ĐĂNG KÝ'}
                        </span>
                        <h2>
                          {selectedCourse?.title ||
                            selectedRun?.course_title ||
                            'Không gian học tập của bạn'}
                        </h2>
                        <p>
                          {isTeacher
                            ? 'Chủ đề rõ ràng, mục tiêu cụ thể, thứ tự học có hướng dẫn.'
                            : selectedRun
                              ? `Lượt học ${selectedRun.code} · Bắt đầu ${formatDate(selectedRun.course_run_start_date)}`
                              : 'Các lượt học sẽ xuất hiện sau khi giảng viên thêm tài khoản của bạn.'}
                        </p>
                      </div>
                      <div className="banner-stat">
                        <strong>{visibleRuns.length.toString().padStart(2, '0')}</strong>
                        <span>Lượt học</span>
                      </div>
                    </section>
                    <section className="runs-section" aria-labelledby="runs-heading">
                      <div className="section-heading">
                        <div>
                          <h2 id="runs-heading">
                            {isTeacher ? 'Các lượt học' : 'Lượt học của bạn'}
                          </h2>
                          <p className="muted">
                            {isTeacher
                              ? 'Mỗi lượt học có ngày bắt đầu và danh sách sinh viên riêng.'
                              : 'Bạn chỉ thấy những lượt học đã được giảng viên thêm vào.'}
                          </p>
                        </div>
                        {isTeacher && (
                          <button
                            className="button button-primary button-compact"
                            onClick={() => {
                              setCreateOpen(!createOpen)
                              setFormError('')
                              setSuccess('')
                            }}
                            disabled={!!mutation}
                          >
                            <Icon name="plus" />
                            {createOpen ? 'Đóng biểu mẫu' : 'Tạo lượt học'}
                          </button>
                        )}
                      </div>
                      {createOpen && (
                        <form className="management-form create-form" onSubmit={createRun}>
                          <h3>Tạo lượt học mới</h3>
                          <p className="muted form-help">
                            Chọn ngày bắt đầu thực tế. Mốc này được dùng để tính ngày học và thời
                            điểm dự báo.
                          </p>
                          {formError && <Notice>{formError}</Notice>}
                          <div className="form-grid">
                            <label>
                              Mã lượt học
                              <input
                                name="run_code"
                                value={code}
                                onChange={(event) => setCode(event.target.value)}
                                placeholder="VD: MOBILE-2026-A"
                                required
                                pattern={'[A-Za-z0-9][A-Za-z0-9_\\-]*'}
                                title="Bắt đầu bằng chữ hoặc số; chỉ dùng chữ Latin, số, dấu gạch nối và gạch dưới."
                                maxLength={64}
                                disabled={!!mutation}
                              />
                            </label>
                            <label>
                              Ngày bắt đầu
                              <input
                                name="start_date"
                                type="date"
                                value={startDate}
                                onChange={(event) => setStartDate(event.target.value)}
                                required
                                disabled={!!mutation}
                              />
                            </label>
                            <label>
                              Múi giờ
                              <select
                                name="timezone"
                                value={timezone}
                                onChange={(event) => setTimezone(event.target.value)}
                                disabled={!!mutation}
                              >
                                <option value="Asia/Ho_Chi_Minh">Việt Nam (UTC+7)</option>
                                <option value="Asia/Bangkok">Bangkok (UTC+7)</option>
                                <option value="UTC">UTC</option>
                              </select>
                            </label>
                          </div>
                          <div className="form-actions">
                            <button
                              className="button button-secondary"
                              type="button"
                              onClick={() => {
                                setCreateOpen(false)
                                setFormError('')
                              }}
                              disabled={!!mutation}
                            >
                              Hủy
                            </button>
                            <button className="button button-primary" disabled={!!mutation}>
                              {mutation === 'create' ? 'Đang tạo…' : 'Tạo bản nháp'}
                            </button>
                          </div>
                        </form>
                      )}
                      {visibleRuns.length ? (
                        <div className="run-grid">
                          {visibleRuns.map((run) => (
                            <button
                              className={`run-card${run.id === selectedRunId ? ' run-selected' : ''}`}
                              key={run.id}
                              onClick={() => selectRun(run)}
                              aria-pressed={run.id === selectedRunId}
                            >
                              <div className="run-card-top">
                                <span className="run-symbol">
                                  <Icon name="book" />
                                </span>
                                <StatusBadge run={run} />
                              </div>
                              <strong>{run.code}</strong>
                              {!isTeacher && (
                                <span className="run-course-title">{run.course_title}</span>
                              )}
                              <div className="run-card-bottom">
                                <span>
                                  <Icon name="calendar" size={15} />
                                  {formatDate(run.course_run_start_date)}
                                </span>
                                {isTeacher && run.student_count !== undefined && (
                                  <span>
                                    <Icon name="users" size={15} />
                                    {run.student_count} sinh viên
                                  </span>
                                )}
                                <Icon name="arrow" size={18} />
                              </div>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="empty-state compact-empty">
                          <Icon name="calendar" size={28} />
                          <h3>
                            {isTeacher
                              ? 'Học phần chưa có lượt học'
                              : 'Bạn chưa được thêm vào lượt học'}
                          </h3>
                          <p>
                            {isTeacher ? (
                              'Tạo lượt học để thiết lập ngày bắt đầu và thêm sinh viên.'
                            ) : (
                              <>
                                Gửi email <strong>{session.user.email}</strong> cho giảng viên để
                                được thêm vào học phần.
                              </>
                            )}
                          </p>
                        </div>
                      )}
                    </section>
                    {isTeacher && selectedRun && (
                      <section className="run-management" aria-labelledby="run-management-heading">
                        <div className="section-heading">
                          <div>
                            <span className="eyebrow">LƯỢT HỌC ĐÃ CHỌN</span>
                            <h2 id="run-management-heading">{selectedRun.code}</h2>
                            <p className="muted">
                              Bắt đầu {formatDate(selectedRun.course_run_start_date)} ·{' '}
                              {selectedRun.timezone}
                            </p>
                          </div>
                          {selectedRun.status === 'draft' && selectedRun.data_origin === 'real' && (
                            <button
                              className="button button-primary button-compact"
                              onClick={activateRun}
                              disabled={!!mutation}
                            >
                              <Icon name="check" />
                              {mutation === 'activate' ? 'Đang mở…' : 'Mở lượt học'}
                            </button>
                          )}
                        </div>
                        {selectedRun.data_origin === 'synthetic' ? (
                          <p className="muted">
                            Đây là lượt học mô phỏng, dùng để đọc và trình diễn dữ liệu.
                          </p>
                        ) : selectedRun.status === 'closed' ? (
                          <p className="muted">
                            Lượt học đã đóng. Thông tin chủ đề vẫn có thể được xem.
                          </p>
                        ) : (
                          <form className="enrollment-form" onSubmit={enroll}>
                            <label htmlFor="student-email">Thêm sinh viên đã đăng ký</label>
                            <div className="inline-form">
                              <input
                                id="student-email"
                                name="student_email"
                                type="email"
                                autoComplete="off"
                                placeholder="Email tài khoản sinh viên"
                                value={studentEmail}
                                onChange={(event) => setStudentEmail(event.target.value)}
                                required
                                disabled={!!mutation}
                              />
                              <button className="button button-secondary" disabled={!!mutation}>
                                {mutation === 'enroll' ? 'Đang thêm…' : 'Thêm sinh viên'}
                              </button>
                            </div>
                            {formError && !createOpen && <Notice>{formError}</Notice>}
                          </form>
                        )}
                      </section>
                    )}
                    {(selectedRun || (isTeacher && selectedCourse)) && (
                      <section className="topics-section" aria-labelledby="topics-heading">
                        <div className="section-heading">
                          <div>
                            <h2 id="topics-heading">Nội dung học phần</h2>
                            <p className="muted">
                              Mục tiêu theo chủ đề và kiến thức tiên quyết để định hướng việc học.
                            </p>
                          </div>
                          {!topicLoading && !topicError && (
                            <span className="topic-count">{topics.length} chủ đề</span>
                          )}
                        </div>
                        <Topics
                          topics={topics}
                          loading={topicLoading}
                          error={topicError}
                          onRetry={() => setTopicReload((current) => current + 1)}
                        />
                      </section>
                    )}
                  </>
                )}
              </>
            )
          )}
          <footer className="workspace-footer">
            <span>StudyHub</span>
            <span>Học có mục tiêu. Tiến từng bước.</span>
          </footer>
        </main>
      </div>
    </div>
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

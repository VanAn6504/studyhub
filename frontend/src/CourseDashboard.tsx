import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, errorMessage, listAll, request } from './api'
import type { Course, CourseRun, Session, Topic } from './api'
import LearningWorkspace from './LearningWorkspace'
import ClassManager from './ClassManager'
import { isWorkspaceUrl, readWorkspaceRoute, routeHash } from './workspaceNavigation'
import { Link } from './website/ui'
import {
  navigate as siteNavigate,
  registerNavigationGuard,
  replacePosition,
  useLocation,
} from './website/navigation'
import type { NavigationGuard, WorkspaceRoute } from './workspaceNavigation'
import './workspace.css'

export default function CourseDashboard({
  session,
  onLogout,
  onExpired,
}: {
  session: Session
  onLogout: () => void
  onExpired: () => void
}) {
  const teacher = session.user.role === 'teacher'
  const siteLocation = useLocation()
  const [route, setRoute] = useState(() => ({ ...readWorkspaceRoute(), actor: session.user.role }))
  const routeRef = useRef(route)
  routeRef.current = route
  const guard = useRef<NavigationGuard | null>(null)
  const navigating = useRef(false)
  const [courses, setCourses] = useState<Course[]>([])
  const [runs, setRuns] = useState<CourseRun[]>([])
  const [topics, setTopics] = useState<Topic[]>([])
  const [topicContext, setTopicContext] = useState('')
  const [loading, setLoading] = useState(true)
  const [topicLoading, setTopicLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [reload, setReload] = useState(0)
  const [topicReload, setTopicReload] = useState(0)
  const [busy, setBusy] = useState(false)
  const [chatSignal, setChatSignal] = useState(0)
  const [courseDraft, setCourseDraft] = useState({ code: '', title: '' })
  const [classDraft, setClassDraft] = useState({
    code: '',
    date: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10),
    timezone: 'Asia/Bangkok',
  })
  const fail = useCallback(
    (value: unknown) => {
      setError(errorMessage(value))
      if (value instanceof ApiError && value.status === 401) onExpired()
    },
    [onExpired],
  )
  const registerGuard = useCallback((value: NavigationGuard | null) => {
    guard.current = value
  }, [])
  const formState = useRef({ busy, courseDraft, classDraft, view: route.view })
  formState.current = { busy, courseDraft, classDraft, view: route.view }
  useEffect(
    () =>
      registerNavigationGuard(async (nextUrl) => {
        const next = isWorkspaceUrl(nextUrl) ? readWorkspaceRoute(nextUrl) : null
        const local = formState.current
        if (local.busy) return false
        const dirty =
          (local.view === 'new-course' && (local.courseDraft.code || local.courseDraft.title)) ||
          (local.view === 'new-class' && local.classDraft.code)
        if (
          dirty &&
          (!next || next.view !== local.view) &&
          !window.confirm('Biểu mẫu có thay đổi chưa lưu. Rời trang và bỏ thay đổi?')
        )
          return false
        return guard.current ? guard.current(next) : true
      }),
    [],
  )
  const navigate = useCallback(async (next: WorkspaceRoute, saved = false) => {
    if (navigating.current) return false
    navigating.current = true
    try {
      if (!(await siteNavigate(routeHash({ ...next, actor: session.user.role }), { force: saved })))
        return false
      if (next.courseId !== routeRef.current.courseId || next.runId !== routeRef.current.runId)
        setChatSignal(0)
      setRoute({ ...next, actor: session.user.role })
      setError('')
      setMessage('')
      window.scrollTo({ top: 0 })
      return true
    } finally {
      navigating.current = false
    }
  }, [])
  useEffect(() => {
    setRoute({ ...readWorkspaceRoute(siteLocation), actor: session.user.role })
  }, [siteLocation, session.user.role])
  useEffect(() => {
    let stopped = false
    setLoading(true)
    Promise.all([
      listAll<CourseRun>('/course-runs'),
      teacher ? listAll<Course>('/courses') : Promise.resolve([]),
    ])
      .then(([newRuns, newCourses]) => {
        if (stopped) return
        setRuns(newRuns)
        setCourses(
          teacher
            ? newCourses
            : [
                ...new Map(
                  newRuns.map((run) => [
                    run.course_id,
                    { id: run.course_id, code: '', title: run.course_title },
                  ]),
                ).values(),
              ],
        )
      })
      .catch((value) => {
        if (!stopped) fail(value)
      })
      .finally(() => {
        if (!stopped) setLoading(false)
      })
    return () => {
      stopped = true
    }
  }, [teacher, reload, fail])
  const course = courses.find((value) => value.id === route.courseId)
  const courseRuns = runs.filter((value) => value.course_id === route.courseId)
  const run = courseRuns.find((value) => value.id === route.runId)
  useEffect(() => {
    if (!loading && route.runId && !route.courseId) {
      const found = runs.find((item) => item.id === route.runId)
      if (found) replacePosition(routeHash({ ...route, courseId: found.course_id }))
    }
  }, [loading, route.runId, route.courseId, runs])
  useEffect(() => {
    if (
      teacher ||
      !run ||
      !course ||
      !['topic', 'pdf', 'quiz', 'progress', 'results'].includes(route.view) ||
      (['topic', 'quiz'].includes(route.view) && !route.topicId)
    )
      return
    const timer = window.setTimeout(() => {
      void request('/me/resume', {
        method: 'PUT',
        csrfToken: session.csrf_token,
        body: {
          run_id: run.id,
          topic_id: route.topicId || null,
          document_version_id: route.view === 'pdf' ? route.versionId || null : null,
          view: route.view,
          page: route.view === 'pdf' ? route.page || 1 : 1,
        },
      }).catch(() => {})
    }, 300)
    return () => window.clearTimeout(timer)
  }, [
    teacher,
    run?.id,
    course?.id,
    route.view,
    route.topicId,
    route.versionId,
    route.page,
    session.csrf_token,
  ])
  useEffect(() => {
    if (!route.courseId || (!teacher && !run)) {
      setTopics([])
      return
    }
    let stopped = false
    setTopicLoading(true)
    const path = teacher ? `/courses/${route.courseId}/topics` : `/course-runs/${run!.id}/topics`
    listAll<Topic>(path)
      .then((value) => {
        if (!stopped) {
          setTopics(value.sort((a, b) => a.order_index - b.order_index))
          setTopicContext(route.courseId)
        }
      })
      .catch((value) => {
        if (!stopped) fail(value)
      })
      .finally(() => {
        if (!stopped) setTopicLoading(false)
      })
    return () => {
      stopped = true
    }
  }, [route.courseId, run?.id, teacher, topicReload, fail])
  const go = (view: WorkspaceRoute['view'], fields: Partial<WorkspaceRoute> = {}) =>
    void navigate({ ...route, view, ...fields })
  const changed = useCallback(() => setTopicReload((value) => value + 1), [])
  async function logout() {
    if (guard.current && !(await guard.current(null))) return
    setBusy(true)
    try {
      await request('/auth/logout', { method: 'POST', csrfToken: session.csrf_token })
      replacePosition('/workspace?view=home')
      onLogout()
    } catch (value) {
      fail(value)
    } finally {
      setBusy(false)
    }
  }
  async function createCourse(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const value = await request<Course>('/courses', {
        method: 'POST',
        csrfToken: session.csrf_token,
        body: { code: courseDraft.code.trim(), title: courseDraft.title.trim() },
      })
      setCourses((all) => [...all, value])
      setCourseDraft({ code: '', title: '' })
      await navigate({ view: 'topics', courseId: value.id, runId: '' }, true)
      setReload((v) => v + 1)
    } catch (value) {
      fail(value)
    } finally {
      setBusy(false)
    }
  }
  async function createClass(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const value = await request<CourseRun>(`/courses/${route.courseId}/runs`, {
        method: 'POST',
        csrfToken: session.csrf_token,
        body: {
          code: classDraft.code.trim(),
          course_run_start_date: classDraft.date,
          timezone: classDraft.timezone,
        },
      })
      setRuns((all) => [...all, value])
      setClassDraft((old) => ({ ...old, code: '' }))
      await navigate({ ...route, view: 'classes', runId: value.id }, true)
      setMessage('Đã tạo lớp nháp. Thêm sinh viên và mở lớp khi sẵn sàng.')
    } catch (value) {
      fail(value)
    } finally {
      setBusy(false)
    }
  }
  const items: [WorkspaceRoute['view'], string][] = teacher
    ? [
        ['topics', 'Chủ đề'],
        ['materials', 'Tài liệu'],
        ['classes', 'Lớp học'],
        ['report', 'Kết quả'],
      ]
    : [
        ['topics', 'Nội dung học phần'],
        ['progress', 'Lộ trình & tiến độ'],
        ['results', 'Kết quả'],
      ]
  const inCourse = route.view !== 'home' && route.view !== 'new-course'
  const active = ['topic', 'quiz', 'quiz-editor', 'topic-editor', 'pdf'].includes(route.view)
    ? 'topics'
    : ['upload', 'document'].includes(route.view)
      ? 'materials'
      : route.view === 'new-class'
        ? 'classes'
        : route.view
  return (
    <div className="app-shell course-dashboard">
      <aside className="sidebar">
        <strong className="workspace-brand">StudyHub</strong>
        <p className="sidebar-label">{teacher ? 'KHÔNG GIAN GIẢNG DẠY' : 'KHÔNG GIAN HỌC TẬP'}</p>
        <button
          className={`nav-item ${!inCourse ? 'nav-active' : ''}`}
          onClick={() => go('home')}
          disabled={busy}
        >
          Học phần của tôi
        </button>
        {inCourse && course && (
          <nav aria-label="Điều hướng học phần">
            <p className="sidebar-label">{course.code || course.title}</p>
            {items.map(([view, title]) => (
              <button
                key={view}
                className={`nav-item ${active === view ? 'nav-active' : ''}`}
                onClick={() => go(view)}
                disabled={busy}
              >
                {title}
              </button>
            ))}
          </nav>
        )}
      </aside>
      <div className="app-body">
        <header className="topbar">
          <strong className="workspace-mobile-brand">StudyHub</strong>
          <span className="topbar-context">
            {teacher ? 'Không gian giảng viên' : 'Không gian sinh viên'}
          </span>
          <div className="account">
            <div>
              <strong>{session.user.display_name}</strong>
              <span>{teacher ? 'Giảng viên' : 'Sinh viên'}</span>
            </div>
            <button
              className="button button-secondary"
              onClick={() => void logout()}
              disabled={busy}
            >
              Đăng xuất
            </button>
          </div>
        </header>
        <main className="workspace" id="main-content">
          {route.view !== 'home' && (
            <div className="workspace-breadcrumb">
              <button className="text-button" onClick={() => go('home')}>
                Học phần của tôi
              </button>
              {course && (
                <>
                  <span>›</span>
                  <button className="text-button" onClick={() => go('topics')}>
                    {course.title}
                  </button>
                </>
              )}
            </div>
          )}
          {error && (
            <div className="notice notice-error" role="alert">
              {error}
              <button
                className="text-button"
                onClick={() => {
                  setReload((v) => v + 1)
                  changed()
                  setError('')
                }}
              >
                Thử lại
              </button>
            </div>
          )}
          {message && (
            <p className="notice notice-success" role="status">
              {message}
            </p>
          )}
          {loading && <p role="status">Đang tải học phần…</p>}
          {!loading &&
            ((route.courseId && !course) ||
              (route.runId && !runs.some((item) => item.id === route.runId))) && (
              <section className="workspace-empty" role="alert">
                <h1>Không tìm thấy không gian học phần</h1>
                <p>Lớp không tồn tại hoặc tài khoản không còn quyền truy cập.</p>
                <Link to={teacher ? '/teaching' : '/my-courses'}>Về danh sách của tôi</Link>
              </section>
            )}
          {route.view === 'home' && (
            <>
              <div className="section-heading">
                <div>
                  <h1>Học phần của tôi</h1>
                  <p className="muted">
                    {teacher
                      ? 'Chuẩn bị nội dung và quản lý lớp học.'
                      : 'Chọn học phần để tiếp tục học.'}
                  </p>
                </div>
                {teacher && (
                  <button className="button button-primary" onClick={() => go('new-course')}>
                    Tạo học phần
                  </button>
                )}
              </div>
              {!loading && !courses.length && (
                <div className="workspace-empty">
                  <h2>Chưa có học phần</h2>
                  <p>
                    {teacher
                      ? 'Tạo học phần đầu tiên để thêm chủ đề và tài liệu.'
                      : 'Học phần sẽ xuất hiện khi giảng viên thêm bạn vào lớp.'}
                  </p>
                </div>
              )}
              <div className="workspace-grid">
                {courses.map((value) => (
                  <article className="workspace-card" key={value.id}>
                    <span className="eyebrow">{value.code || 'HỌC PHẦN ĐÃ ĐĂNG KÝ'}</span>
                    <h2>{value.title}</h2>
                    <p className="muted">
                      {runs.filter((item) => item.course_id === value.id).length} lớp học
                    </p>
                    <button
                      className="button button-primary"
                      onClick={() =>
                        void navigate({
                          courseId: value.id,
                          runId: teacher
                            ? ''
                            : runs.find((item) => item.course_id === value.id)?.id || '',
                          view: 'topics',
                        })
                      }
                    >
                      {teacher ? 'Quản lý học phần' : 'Vào học phần'}
                    </button>
                  </article>
                ))}
              </div>
            </>
          )}
          {teacher && route.view === 'new-course' && (
            <>
              <h1>Tạo học phần</h1>
              <form className="learning-form workspace-form" onSubmit={createCourse}>
                <fieldset disabled={busy}>
                  <label>
                    Tên học phần
                    <input
                      required
                      maxLength={200}
                      value={courseDraft.title}
                      onChange={(e) => setCourseDraft((old) => ({ ...old, title: e.target.value }))}
                    />
                  </label>
                  <label>
                    Mã học phần
                    <input
                      required
                      pattern="[A-Za-z0-9]([A-Za-z0-9_]|-)*"
                      maxLength={64}
                      value={courseDraft.code}
                      onChange={(e) => setCourseDraft((old) => ({ ...old, code: e.target.value }))}
                    />
                  </label>
                  <button className="button button-primary">
                    Tạo học phần và chuẩn bị nội dung
                  </button>
                </fieldset>
              </form>
            </>
          )}
          {inCourse && course && (
            <>
              <div className="section-heading">
                <div>
                  <h1>{course.title}</h1>
                  <p className="muted">
                    {teacher
                      ? 'Nội dung dùng chung cho các lớp của học phần.'
                      : run
                        ? `Lớp ${run.code} · Bắt đầu ${new Date(run.course_run_start_date + 'T00:00:00').toLocaleDateString('vi-VN')}`
                        : 'Chọn lớp đã đăng ký.'}
                  </p>
                  {!teacher &&
                    run &&
                    (run.data_origin === 'synthetic' || run.status !== 'active') && (
                      <span className="workspace-badge">
                        {run.data_origin === 'synthetic'
                          ? 'Dữ liệu mô phỏng · chỉ xem'
                          : run.status === 'draft'
                            ? 'Lớp chưa mở · chỉ xem'
                            : 'Lớp đã đóng · chỉ xem'}
                      </span>
                    )}
                </div>
                <div className="workspace-actions">
                  {!teacher && run && (
                    <button
                      className="button button-secondary"
                      onClick={() => setChatSignal((v) => v + 1)}
                    >
                      Hỏi trợ giảng
                    </button>
                  )}
                  <button
                    className="button button-secondary"
                    onClick={() => {
                      changed()
                      setReload((v) => v + 1)
                    }}
                  >
                    Làm mới học phần
                  </button>
                </div>
              </div>
              <nav className="workspace-mobile-tabs" aria-label="Các phần của học phần">
                {items.map(([view, title]) => (
                  <button
                    className="button button-secondary"
                    key={view}
                    aria-pressed={active === view}
                    onClick={() => go(view)}
                  >
                    {title}
                  </button>
                ))}
              </nav>
              {teacher && (
                <div className="site-actions">
                  <Link to={`/teaching/courses/${course.id}/overview`}>Giới thiệu công khai</Link>
                  <Link to="/teaching/classes">Tuyển sinh các lớp</Link>
                </div>
              )}
              {((!teacher && courseRuns.length > 1) || (teacher && route.view === 'report')) && (
                <label className="workspace-class-selector">
                  Lớp học
                  <select
                    aria-label="Lớp học"
                    value={route.runId}
                    onChange={(e) => go(route.view, { runId: e.target.value })}
                  >
                    <option value="">Chọn lớp học</option>
                    {courseRuns.map((value) => (
                      <option value={value.id} key={value.id}>
                        {value.code}
                        {value.data_origin === 'synthetic' ? ' · Mô phỏng' : ''}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {teacher && route.view === 'classes' && (
                <>
                  <div className="section-heading">
                    <h2>Lớp học</h2>
                    <button className="button button-primary" onClick={() => go('new-class')}>
                      Tạo lớp học
                    </button>
                  </div>
                  <p className="muted">Mỗi lớp có ngày bắt đầu, sinh viên và kết quả riêng.</p>
                  {!courseRuns.length && (
                    <p className="workspace-empty">Chưa có lớp học. Tạo lớp để thêm sinh viên.</p>
                  )}
                  {courseRuns.map((value) => (
                    <ClassManager
                      key={value.id}
                      run={value}
                      csrfToken={session.csrf_token}
                      onFailure={fail}
                      onChanged={() => setReload((v) => v + 1)}
                      onReport={() => go('report', { runId: value.id })}
                    />
                  ))}
                </>
              )}
              {teacher && route.view === 'new-class' && (
                <>
                  <h2>Tạo lớp học</h2>
                  <form className="learning-form workspace-form" onSubmit={createClass}>
                    <fieldset disabled={busy}>
                      <label>
                        Mã lớp (ví dụ CNTT01_HK1_2026)
                        <input
                          required
                          pattern="[A-Za-z0-9]([A-Za-z0-9_]|-)*"
                          value={classDraft.code}
                          onChange={(e) =>
                            setClassDraft((old) => ({ ...old, code: e.target.value }))
                          }
                        />
                      </label>
                      <label>
                        Ngày bắt đầu
                        <input
                          required
                          type="date"
                          value={classDraft.date}
                          onChange={(e) =>
                            setClassDraft((old) => ({ ...old, date: e.target.value }))
                          }
                        />
                      </label>
                      <label>
                        Múi giờ
                        <select
                          value={classDraft.timezone}
                          onChange={(e) =>
                            setClassDraft((old) => ({ ...old, timezone: e.target.value }))
                          }
                        >
                          <option value="Asia/Bangkok">Asia/Bangkok · UTC+7</option>
                          <option value="Asia/Ho_Chi_Minh">Asia/Ho_Chi_Minh · UTC+7</option>
                        </select>
                      </label>
                      <p className="muted">Ngày bắt đầu dùng để tính cửa sổ dữ liệu dự báo.</p>
                      <button className="button button-primary">Tạo lớp nháp</button>
                    </fieldset>
                  </form>
                </>
              )}
            </>
          )}
          {inCourse && !loading && !course && (
            <p className="notice notice-error">
              Không tìm thấy học phần hoặc bạn chưa có quyền truy cập.
            </p>
          )}
          {course && (teacher || run) && (
            <div hidden={!inCourse || route.view === 'classes' || route.view === 'new-class'}>
              <LearningWorkspace
                key={`${course.id}:${teacher ? 'teacher' : run?.id || ''}`}
                courseId={course.id}
                run={run}
                topics={topicContext === route.courseId ? topics : []}
                session={session}
                onChanged={changed}
                onExpired={onExpired}
                route={route}
                onNavigate={navigate}
                onRegisterGuard={registerGuard}
                topicsLoading={topicLoading || topicContext !== route.courseId}
                chatSignal={chatSignal}
              />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

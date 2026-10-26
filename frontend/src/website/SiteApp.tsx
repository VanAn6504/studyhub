import { useCallback, useEffect, useState } from 'react'
import { ApiError, errorMessage, request } from '../api'
import type { Session } from '../api'
import CourseDashboard from '../CourseDashboard'
import { isWorkspaceUrl, readWorkspaceRoute, routeHash } from '../workspaceNavigation'
import SiteLayout from './SiteLayout'
import AuthPage from './AuthPage'
import { CatalogPage, CourseDetailPage, HomePage } from './CatalogPages'
import { EnrollmentRequestsPage, LearnerOverview, MyCoursesPage } from './LearnerPages'
import { ProfilePage, SecurityPage } from './AccountPages'
import { AdmissionsPage, PublicationPage, TeacherOverview } from './TeacherPages'
import InformationPage from './InformationPages'
import { canLeave, getLocation, navigate, safeReturn, useLocation } from './navigation'
import { Empty, Link, Notice, State } from './ui'
import './website.css'

function decodeSegment(value: string) {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

export default function SiteApp() {
  const href = useLocation(),
    url = new URL(href, location.origin),
    path = url.pathname,
    params = url.searchParams
  const [session, setSession] = useState<Session | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState<unknown>(null),
    [retry, setRetry] = useState(0),
    [authMessage, setAuthMessage] = useState(''),
    [actionError, setActionError] = useState('')
  useEffect(() => {
    let stopped = false
    setLoading(true)
    setError(null)
    request<Session>('/auth/me')
      .then((value) => {
        if (!stopped) setSession(value)
      })
      .catch((failure) => {
        if (stopped) return
        setSession(null)
        if (!(failure instanceof ApiError && failure.status === 401)) setError(failure)
      })
      .finally(() => {
        if (!stopped) setLoading(false)
      })
    return () => {
      stopped = true
    }
  }, [retry])
  const expired = useCallback(() => {
    setSession(null)
    setAuthMessage('Phiên đăng nhập đã hết hạn. Đăng nhập lại để tiếp tục.')
    void navigate('/login?next=' + encodeURIComponent(safeReturn(getLocation(), '/dashboard')), {
      replace: true,
      force: true,
    })
  }, [])
  useEffect(() => {
    window.addEventListener('studyhub:expired', expired)
    return () => window.removeEventListener('studyhub:expired', expired)
  }, [expired])
  useEffect(() => {
    if (!loading && url.hash.startsWith('#view='))
      void navigate(routeHash({ ...readWorkspaceRoute(), actor: session?.user.role }), {
        replace: true,
        force: true,
      })
  }, [href, loading, session?.user.role])
  const workspace =
    path === '/workspace' ||
    path.startsWith('/learn/') ||
    path.startsWith('/teaching/workspace/') ||
    path === '/teaching/new-course'
  const teacherPath = path.startsWith('/teaching'),
    studentPath =
      ['/dashboard', '/my-courses', '/enrollments'].includes(path) || path.startsWith('/learn/')
  const protectedPage =
    workspace || teacherPath || studentPath || path === '/profile' || path === '/settings/security'
  useEffect(() => {
    if (loading || error) return
    if (protectedPage && !session) {
      void navigate('/login?next=' + encodeURIComponent(safeReturn(href, '/dashboard')), {
        replace: true,
        force: true,
      })
    } else if (session && (path === '/login' || path === '/register'))
      void navigate(
        safeReturn(
          params.get('next'),
          session.user.role === 'teacher' ? '/teaching' : '/dashboard',
        ),
        { replace: true, force: true },
      )
  }, [loading, error, session?.user.id, href])
  useEffect(() => {
    const labels: Record<string, string> = {
      '/': 'Học từng chủ đề',
      '/courses': 'Khám phá học phần',
      '/dashboard': 'Tổng quan học tập',
      '/my-courses': 'Học phần của tôi',
      '/profile': 'Hồ sơ',
      '/settings/security': 'Bảo mật',
      '/enrollments': 'Yêu cầu tham gia',
      '/teaching': 'Tổng quan giảng dạy',
      '/login': 'Đăng nhập',
      '/register': 'Đăng ký',
      '/help': 'Hướng dẫn',
      '/about': 'Giới thiệu',
      '/privacy': 'Thông tin riêng tư',
    }
    document.title =
      (labels[path] || (workspace ? 'Không gian học phần' : 'StudyHub')) + ' · StudyHub'
    let meta = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'description'
      document.head.append(meta)
    }
    meta.content = 'StudyHub: khám phá học phần, tham gia lớp, học theo chủ đề và theo dõi tiến độ.'
    // Move focus after SPA navigation, preserving the skip link as the first
    // keyboard stop when the document initially loads.
    if (!loading) document.getElementById('main-content')?.focus({ preventScroll: true })
  }, [path])
  async function logout() {
    if (!(await canLeave('/login'))) return
    setActionError('')
    try {
      await request('/auth/logout', { method: 'POST', csrfToken: session!.csrf_token })
      setSession(null)
      setAuthMessage('')
      await navigate('/login', { replace: true, force: true })
    } catch (e) {
      setActionError(errorMessage(e))
    }
  }
  const wrongRole =
    session &&
    ((teacherPath && session.user.role !== 'teacher') ||
      (studentPath && session.user.role !== 'student'))
  let content
  if (loading) content = <State loading />
  else if (error) content = <State error={error} retry={() => setRetry((v) => v + 1)} />
  else if (wrongRole)
    content = (
      <Empty title="Bạn không có quyền mở trang này">
        <p>
          Trang dành cho {teacherPath ? 'giảng viên' : 'sinh viên'}. Tài khoản của bạn vẫn sử dụng
          được những chức năng thuộc vai trò hiện tại.
        </p>
        <Link to={session!.user.role === 'teacher' ? '/teaching' : '/dashboard'}>Về tổng quan</Link>
      </Empty>
    )
  else if (protectedPage && !session) content = <State loading />
  else if (workspace && !isWorkspaceUrl(href))
    content = (
      <Empty title="404 · Không tìm thấy trang học tập">
        <Link to={session?.user.role === 'teacher' ? '/teaching' : '/my-courses'}>
          Về không gian của tôi
        </Link>
      </Empty>
    )
  else if (workspace && session)
    content = (
      <CourseDashboard
        session={session}
        onLogout={() => {
          setSession(null)
          void navigate('/login', { replace: true, force: true })
        }}
        onExpired={expired}
      />
    )
  else if (path === '/') content = <HomePage session={session} />
  else if (path === '/courses') content = <CatalogPage search={url.search} />
  else if (/^\/courses\/[^/]+$/.test(path))
    content = (
      <CourseDetailPage
        slug={decodeSegment(path.split('/')[2])}
        session={session}
        selectedRun={params.get('run')}
      />
    )
  else if (path === '/login' || path === '/register')
    content = (
      <AuthPage
        mode={path === '/login' ? 'login' : 'register'}
        next={params.get('next')}
        initialMessage={authMessage}
        onLogin={(value, next) => {
          setSession(value)
          setAuthMessage('')
          void navigate(next, { replace: true, force: true })
        }}
      />
    )
  else if (path === '/dashboard' && session) content = <LearnerOverview session={session} />
  else if (path === '/my-courses') content = <MyCoursesPage search={url.search} />
  else if (path === '/enrollments' && session)
    content = <EnrollmentRequestsPage session={session} search={url.search} />
  else if (path === '/profile' && session)
    content = <ProfilePage session={session} onUpdated={setSession} />
  else if (path === '/settings/security' && session)
    content = (
      <SecurityPage
        session={session}
        onChanged={() => {
          setSession(null)
          setAuthMessage('Đã đổi mật khẩu và thu hồi các phiên cũ. Đăng nhập bằng mật khẩu mới.')
          void navigate('/login', { replace: true, force: true })
        }}
      />
    )
  else if (
    ['/teaching', '/teaching/courses', '/teaching/classes', '/teaching/requests'].includes(path)
  )
    content = (
      <TeacherOverview
        section={
          path === '/teaching'
            ? 'overview'
            : (path.split('/')[2] as 'courses' | 'classes' | 'requests')
        }
      />
    )
  else if (/^\/teaching\/courses\/[^/]+\/overview$/.test(path) && session)
    content = <PublicationPage key={path} courseId={path.split('/')[3]} session={session} />
  else if (/^\/teaching\/runs\/[^/]+\/admissions$/.test(path) && session)
    content = (
      <AdmissionsPage key={path} runId={path.split('/')[3]} session={session} search={url.search} />
    )
  else if (['/help', '/about', '/privacy'].includes(path))
    content = <InformationPage page={path.slice(1) as 'help' | 'about' | 'privacy'} />
  else
    content = (
      <Empty title="404 · Không tìm thấy trang">
        <p>Đường dẫn không tồn tại hoặc đã thay đổi.</p>
        <div className="site-actions">
          <Link to="/" className="button button-primary">
            Về trang chủ
          </Link>
          <Link to="/courses">Khám phá học phần</Link>
        </div>
      </Empty>
    )
  return (
    <SiteLayout
      session={session}
      path={path}
      workspace={workspace && !!session && !wrongRole && !loading}
      onLogout={() => void logout()}
    >
      {actionError && <Notice>{actionError}</Notice>}
      {content}
    </SiteLayout>
  )
}

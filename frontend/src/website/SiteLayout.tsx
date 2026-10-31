import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { Session } from '../api'
import { Link } from './ui'
import { safeReturn } from './navigation'
import ActionMenu from '../workspace/ActionMenu'

export default function SiteLayout({
  session,
  path,
  children,
  onLogout,
  workspace = false,
}: {
  session: Session | null
  path: string
  children: ReactNode
  onLogout: () => void
  workspace?: boolean
}) {
  const [menu, setMenu] = useState(false)
  useEffect(() => setMenu(false), [path])
  const teacher = session?.user.role === 'teacher'
  const intended =
    path === '/login' || path === '/register'
      ? new URLSearchParams(location.search).get('next')
      : path.startsWith('/courses/')
        ? location.pathname + location.search
        : null
  const authSuffix = intended ? '?next=' + encodeURIComponent(safeReturn(intended)) : ''
  const links = session
    ? teacher
      ? [
          ['/teaching', 'Tổng quan giảng dạy'],
          ['/teaching/courses', 'Học phần quản lý'],
          ['/teaching/classes', 'Lớp học'],
          ['/teaching/requests', 'Yêu cầu tham gia'],
        ]
      : [
          ['/dashboard', 'Tổng quan'],
          ['/courses', 'Khám phá'],
          ['/my-courses', 'Học phần của tôi'],
          ['/enrollments', 'Yêu cầu tham gia'],
        ]
    : [
        ['/courses', 'Khám phá học phần'],
        ['/help', 'Hướng dẫn'],
      ]
  return (
    <div className={`site-shell ${workspace ? 'site-workspace' : ''}`}>
      <a className="site-skip" href="#main-content">
        Chuyển đến nội dung
      </a>
      <header className="site-header">
        <Link to="/" className="site-brand">
          <span aria-hidden="true" className="site-brand-mark">
            SH
          </span>
          StudyHub<span className="site-brand-dot">.</span>
        </Link>
        <button
          className="button button-secondary site-menu-button"
          aria-expanded={menu}
          aria-controls="site-navigation"
          onClick={() => setMenu((v) => !v)}
        >
          Menu
        </button>
        <div className={`site-header-navigation ${menu ? 'is-open' : ''}`} id="site-navigation">
          <nav
            aria-label={
              session
                ? teacher
                  ? 'Không gian giảng dạy'
                  : 'Không gian học tập'
                : 'Điều hướng chính'
            }
          >
            {links
              .filter(
                ([to]) =>
                  !workspace ||
                  (teacher
                    ? ['/teaching', '/teaching/courses']
                    : ['/dashboard', '/my-courses', '/courses']
                  ).includes(to),
              )
              .map(([to, label]) => (
                <Link key={to} to={to} aria-current={path === to ? 'page' : undefined}>
                  {label}
                </Link>
              ))}
          </nav>
          <nav aria-label="Tài khoản">
            {session ? (
              <>
                {workspace ? (
                  <ActionMenu label={session.user.display_name}>
                    <Link to="/profile">Hồ sơ cá nhân</Link>
                    <Link to="/settings/security">Bảo mật tài khoản</Link>
                    <Link to="/help">Hướng dẫn</Link>
                  </ActionMenu>
                ) : (
                  <Link to="/profile">{session.user.display_name}</Link>
                )}
                <button className="text-button" onClick={onLogout}>
                  Đăng xuất
                </button>
              </>
            ) : (
              <>
                <Link to={'/login' + authSuffix}>Đăng nhập</Link>
                <Link to={'/register' + authSuffix} className="button button-primary">
                  Đăng ký
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>
      {workspace ? (
        <div className="site-workspace-body">{children}</div>
      ) : (
        <main className="site-main" id="main-content" tabIndex={-1}>
          {children}
        </main>
      )}
      <footer className="site-footer">
        <div>
          <Link to="/" className="site-brand">
            StudyHub.
          </Link>
          <p>Học từng chủ đề. Vững từng bước.</p>
        </div>
        <nav aria-label="Thông tin website">
          <Link to="/help">Hướng dẫn</Link>
          <Link to="/about">Giới thiệu</Link>
          <Link to="/privacy">Thông tin riêng tư</Link>
          {session && <Link to="/settings/security">Bảo mật tài khoản</Link>}
        </nav>
      </footer>
    </div>
  )
}

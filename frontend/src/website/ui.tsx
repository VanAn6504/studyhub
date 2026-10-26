import { useEffect, useId, useRef, useState } from 'react'
import type { AnchorHTMLAttributes, ReactNode } from 'react'
import { errorMessage, request } from '../api'
import { navigate, registerNavigationGuard } from './navigation'
import type { Page, PublicCourse } from './types'
import { levels } from './types'

export function Link({
  to,
  children,
  ...props
}: { to: string; children: ReactNode } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>) {
  return (
    <a
      href={to}
      {...props}
      onClick={(event) => {
        props.onClick?.(event)
        if (
          event.defaultPrevented ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey ||
          event.button !== 0
        )
          return
        event.preventDefault()
        void navigate(to)
      }}
    >
      {children}
    </a>
  )
}
export function Notice({
  children,
  kind = 'error',
}: {
  children: ReactNode
  kind?: 'error' | 'success' | 'info'
}) {
  return (
    <div className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  )
}
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="site-empty">
      <h2>{title}</h2>
      {children && <div>{children}</div>}
    </div>
  )
}
export function State({
  loading,
  error,
  retry,
  children,
}: {
  loading?: boolean
  error?: unknown
  retry?: () => void
  children?: ReactNode
}) {
  if (loading)
    return (
      <div className="site-loading" role="status">
        <span className="spinner" />
        Đang tải dữ liệu…
      </div>
    )
  if (error)
    return (
      <Notice>
        {errorMessage(error)}
        {retry && (
          <button className="button button-secondary" onClick={retry}>
            Thử lại
          </button>
        )}
      </Notice>
    )
  return <>{children}</>
}
export function useResource<T>(url: string, reload = 0) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState<unknown>(null),
    [loading, setLoading] = useState(true),
    [retry, setRetry] = useState(0)
  useEffect(() => {
    let stopped = false
    setLoading(true)
    setError(null)
    setData(null)
    request<T>(url)
      .then((value) => {
        if (!stopped) setData(value)
      })
      .catch((value) => {
        if (!stopped) setError(value)
      })
      .finally(() => {
        if (!stopped) setLoading(false)
      })
    return () => {
      stopped = true
    }
  }, [url, reload, retry])
  return { data, error, loading, retry: () => setRetry((v) => v + 1), setData }
}
export function Pagination({
  page,
  total,
  limit,
  onPage,
}: {
  page: number
  total: number
  limit: number
  onPage: (page: number) => void
}) {
  const count = Math.max(1, Math.ceil(total / limit))
  if (total <= limit) return null
  return (
    <nav className="site-pagination" aria-label="Phân trang">
      <button
        className="button button-secondary"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Trang trước
      </button>
      <span>
        Trang {page}/{count} · {total} kết quả
      </span>
      <button
        className="button button-secondary"
        disabled={page >= count}
        onClick={() => onPage(page + 1)}
      >
        Trang sau
      </button>
    </nav>
  )
}
export function CourseCard({ course }: { course: PublicCourse }) {
  const available = course.runs.some((run) => run.availability === 'accepting')
  return (
    <article className="catalog-card">
      <div
        className={`catalog-cover ${course.category_code === 'data-science' ? 'cover-data' : ''}`}
        aria-hidden="true"
      >
        <span>{course.category_name || 'StudyHub'}</span>
        <strong>{course.code}</strong>
      </div>
      <div className="catalog-card-body">
        <span className="site-badge">{levels[course.level]}</span>
        <h2>
          <Link to={'/courses/' + course.slug}>{course.title}</Link>
        </h2>
        <p>{course.summary}</p>
        <p className="site-muted">Giảng viên: {course.instructor_name}</p>
        <span className="site-muted">
          {available ? 'Có lớp đang nhận đăng ký' : 'Xem thông tin lớp'}
        </span>
        <Link className="button button-secondary" to={'/courses/' + course.slug}>
          Xem chi tiết
        </Link>
      </div>
    </article>
  )
}
export function useFormGuard(dirty: boolean, busy = false) {
  const ref = useRef({ dirty, busy }),
    [notice, setNotice] = useState('')
  ref.current = { dirty, busy }
  const id = useId()
  useEffect(() => {
    const remove = registerNavigationGuard(() => {
      if (ref.current.busy) {
        setNotice('Đang lưu dữ liệu. Hãy đợi thao tác hoàn tất.')
        return false
      }
      return (
        !ref.current.dirty ||
        window.confirm('Biểu mẫu có thay đổi chưa lưu. Rời trang và bỏ thay đổi?')
      )
    })
    const unload = (e: BeforeUnloadEvent) => {
      if (ref.current.dirty || ref.current.busy) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', unload)
    return () => {
      remove()
      window.removeEventListener('beforeunload', unload)
    }
  }, [id])
  return notice
}
export function FieldError({ message, id }: { message?: string; id: string }) {
  return message ? (
    <span className="site-field-error" id={id}>
      {message}
    </span>
  ) : null
}
export function formatDate(value: string | null, zone = 'Asia/Bangkok') {
  return value
    ? new Date(value).toLocaleString('vi-VN', {
        timeZone: zone,
        dateStyle: 'short',
        timeStyle: 'short',
      })
    : 'Không giới hạn'
}
export function pageNumber(params: URLSearchParams) {
  const value = Number(params.get('page'))
  return Number.isInteger(value) && value > 0 ? Math.min(value, 8334) : 1
}
export function pageUrl(
  path: string,
  params: URLSearchParams,
  changes: Record<string, string | number>,
) {
  const next = new URLSearchParams(params)
  for (const [key, value] of Object.entries(changes)) {
    if (value === '') next.delete(key)
    else next.set(key, String(value))
  }
  return path + (next.size ? '?' + next.toString() : '')
}
export function pageEnvelope<T>(items: T[]): Page<T> {
  return { items, total: items.length, limit: items.length, offset: 0 }
}

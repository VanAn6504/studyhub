import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, errorMessage, request } from '../api'
import type { Session } from '../api'
import { navigate } from './navigation'
import {
  CourseCard,
  Empty,
  formatDate,
  Link,
  Notice,
  pageNumber,
  pageUrl,
  Pagination,
  State,
  useResource,
} from './ui'
import type { Category, JoinRequest, Metadata, Page, PublicCourse, PublicRun } from './types'
import { levels, modeLabels } from './types'

export function MetadataContent({ metadata }: { metadata: Metadata }) {
  return (
    <>
      <section className="site-panel">
        <h2>Về học phần</h2>
        <p className="site-prose">
          {metadata.description || 'Giảng viên chưa bổ sung giới thiệu.'}
        </p>
      </section>
      {(
        [
          ['Mục tiêu học tập', metadata.objectives],
          ['Kiến thức đầu vào', metadata.prerequisites],
          ['Đề cương học phần', metadata.outline],
          ['Tài liệu được giới thiệu', metadata.material_titles],
        ] as [string, string[]][]
      ).map(([title, items]) => (
        <section className="site-panel" key={title}>
          <h2>{title}</h2>
          {items.length ? (
            <ul className="site-list">
              {items.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          ) : (
            <p className="site-muted">Chưa có thông tin được bổ sung.</p>
          )}
        </section>
      ))}
    </>
  )
}
export function HomePage({ session }: { session: Session | null }) {
  const courses = useResource<Page<PublicCourse>>('/catalog/courses?limit=3&sort=newest'),
    categories = useResource<Category[]>('/catalog/categories')
  function search(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const q = new FormData(e.currentTarget).get('q') as string
    void navigate('/courses' + (q ? '?q=' + encodeURIComponent(q) : ''))
  }
  return (
    <>
      <section className="site-hero">
        <div>
          <span className="eyebrow">HỌC THEO TỪNG CHỦ ĐỀ</span>
          <h1>
            Tìm học phần phù hợp.
            <br />
            Học có lộ trình.
          </h1>
          <p>
            Khám phá học phần, chọn lớp và học tập trong một không gian có tài liệu, quiz và tiến độ
            rõ ràng.
          </p>
          <form className="site-search" onSubmit={search}>
            <label className="site-sr" htmlFor="home-q">
              Tìm học phần
            </label>
            <input id="home-q" name="q" maxLength={160} placeholder="Tên hoặc mã học phần" />
            <button className="button button-primary">Tìm học phần</button>
          </form>
          {session && (
            <Link
              className="text-button"
              to={session.user.role === 'teacher' ? '/teaching' : '/dashboard'}
            >
              Về không gian của tôi →
            </Link>
          )}
        </div>
        <div className="site-journey" aria-label="Ba bước học tập">
          <h2>Từng bước, rõ hướng đi.</h2>
          <div>
            <span>01</span>
            <strong>Khám phá học phần</strong>
            <p>Xem giới thiệu và chọn lớp phù hợp.</p>
          </div>
          <div>
            <span>02</span>
            <strong>Học theo chủ đề</strong>
            <p>Đọc tài liệu, làm quiz và ôn kiến thức.</p>
          </div>
          <div>
            <span>03</span>
            <strong>Theo dõi tiến độ</strong>
            <p>Xem kết quả và bước học tiếp theo.</p>
          </div>
        </div>
      </section>
      {!!categories.data?.length && (
        <section>
          <h2>Lĩnh vực học tập</h2>
          <div className="site-chips">
            {categories.data.map((c) => (
              <Link
                key={c.code}
                to={'/courses?category=' + encodeURIComponent(c.code)}
                className="site-badge"
              >
                {c.name} · {c.course_count} học phần
              </Link>
            ))}
          </div>
        </section>
      )}
      <section>
        <div className="section-heading">
          <h2>Mới công bố</h2>
          <Link to="/courses">Khám phá tất cả →</Link>
        </div>
        <State {...courses}>
          {courses.data?.items.length ? (
            <div className="site-card-grid">
              {courses.data.items.map((c) => (
                <CourseCard key={c.slug} course={c} />
              ))}
            </div>
          ) : (
            <Empty title="Danh mục đang được chuẩn bị">
              <p>
                Các học phần sẽ xuất hiện khi giảng viên công bố thông tin giới thiệu. Học phần đã
                tham gia vẫn có trong không gian của bạn.
              </p>
              <Link to="/help">Xem cách bắt đầu</Link>
            </Empty>
          )}
        </State>
      </section>
      <section className="site-feature-grid">
        <div>
          <h2>Tài liệu đúng chủ đề</h2>
          <p>PDF và quiz được giảng viên tổ chức trong từng chủ đề của học phần.</p>
        </div>
        <div>
          <h2>Tiến độ từ kết quả thực tế</h2>
          <p>Lộ trình dựa vào quiz hiện hành; chủ đề chưa làm bài được ghi là chưa đánh giá.</p>
        </div>
        <div>
          <h2>Trợ giảng có nguồn</h2>
          <p>Câu trả lời dựa trên nguồn được cho phép, kèm tài liệu và trang để đối chiếu.</p>
        </div>
      </section>
    </>
  )
}
export function CatalogPage({ search }: { search: string }) {
  const params = new URLSearchParams(search),
    page = pageNumber(params),
    q = params.get('q') || ''
  const [input, setInput] = useState(q),
    [open, setOpen] = useState(false)
  useEffect(() => setInput(q), [q])
  const category = params.get('category') || '',
    level = params.get('level') || '',
    availability = params.get('availability') || 'all',
    sort = params.get('sort') || 'newest'
  const api = new URLSearchParams({
    q,
    category,
    level,
    availability,
    sort,
    limit: '12',
    offset: String((page - 1) * 12),
  })
  const resource = useResource<Page<PublicCourse>>('/catalog/courses?' + api),
    categories = useResource<Category[]>('/catalog/categories')
  const change = (changes: Record<string, string | number>) =>
    void navigate(pageUrl('/courses', params, { page: 1, ...changes }))
  return (
    <>
      <span className="eyebrow">DANH MỤC HỌC PHẦN</span>
      <h1>Học điều bạn đang tìm kiếm.</h1>
      <p className="site-lead">Tìm hiểu nội dung trước, chọn lớp phù hợp để bắt đầu.</p>
      <form
        className="site-search"
        onSubmit={(e) => {
          e.preventDefault()
          change({ q: input })
        }}
      >
        <label className="site-sr" htmlFor="catalog-q">
          Từ khóa tìm kiếm
        </label>
        <input
          id="catalog-q"
          maxLength={160}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Tên hoặc mã học phần"
        />
        <button className="button button-primary">Tìm kiếm</button>
      </form>
      <button
        className="button button-secondary site-filter-toggle"
        aria-expanded={open}
        aria-controls="catalog-filters"
        onClick={() => setOpen((v) => !v)}
      >
        Bộ lọc
      </button>
      <div className="site-catalog">
        <aside className={`site-filters ${open ? 'is-open' : ''}`} id="catalog-filters">
          <h2>Bộ lọc</h2>
          <label>
            Lĩnh vực
            <select
              aria-label="Lĩnh vực"
              value={category}
              onChange={(e) => change({ category: e.target.value })}
            >
              <option value="">Tất cả lĩnh vực</option>
              {categories.data?.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Trình độ
            <select
              aria-label="Trình độ"
              value={level}
              onChange={(e) => change({ level: e.target.value })}
            >
              <option value="">Tất cả trình độ</option>
              {Object.entries(levels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Nhận đăng ký
            <select
              aria-label="Nhận đăng ký"
              value={availability}
              onChange={(e) => change({ availability: e.target.value })}
            >
              <option value="all">Tất cả học phần</option>
              <option value="accepting">Có lớp đang nhận</option>
            </select>
          </label>
          <button className="text-button" onClick={() => void navigate('/courses')}>
            Xóa tất cả bộ lọc
          </button>
        </aside>
        <section aria-label="Kết quả tìm kiếm">
          <div className="section-heading">
            <p role="status">{resource.data ? `${resource.data.total} học phần` : 'Đang tìm…'}</p>
            <label>
              Sắp xếp
              <select
                aria-label="Sắp xếp"
                value={sort}
                onChange={(e) => change({ sort: e.target.value })}
              >
                <option value="newest">Mới công bố</option>
                <option value="title">Tên A–Z</option>
                <option value="relevance">Độ liên quan</option>
              </select>
            </label>
          </div>
          {(q || category || level || availability === 'accepting') && (
            <p className="site-muted">
              Đang lọc:{' '}
              {[
                q && `“${q}”`,
                category && categories.data?.find((c) => c.code === category)?.name,
                level && levels[level as keyof typeof levels],
                availability === 'accepting' && 'Có lớp đang nhận',
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          )}
          <State {...resource}>
            {resource.data?.items.length ? (
              <div className="site-card-grid catalog-grid">
                {resource.data.items.map((c) => (
                  <CourseCard key={c.slug} course={c} />
                ))}
              </div>
            ) : (
              <Empty
                title={
                  resource.data?.total ? 'Trang này chưa có kết quả' : 'Chưa có học phần phù hợp'
                }
              >
                <p>Thử từ khóa khác, xóa bộ lọc hoặc quay lại khi có học phần được công bố.</p>
                <button
                  className="button button-secondary"
                  onClick={() => void navigate('/courses')}
                >
                  Xem toàn bộ danh mục
                </button>
              </Empty>
            )}
            {resource.data && (
              <Pagination
                page={page}
                total={resource.data.total}
                limit={12}
                onPage={(p) => change({ page: p })}
              />
            )}
          </State>
        </section>
      </div>
    </>
  )
}
function RunCard({
  run,
  course,
  session,
  selected,
}: {
  run: PublicRun
  course: PublicCourse
  session: Session | null
  selected: boolean
}) {
  const [membership, setMembership] = useState<{
      course_id: string
      enrollment_status: string | null
      request: JoinRequest | null
    } | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [reload, setReload] = useState(0)
  useEffect(() => {
    let stopped = false
    if (session?.user.role === 'student')
      request<typeof membership>(`/me/run-status/${run.id}`)
        .then((value) => {
          if (!stopped) setMembership(value)
        })
        .catch(() => {})
    else setMembership(null)
    return () => {
      stopped = true
    }
  }, [session?.user.id, run.id, reload])
  async function join() {
    setBusy(true)
    setError('')
    try {
      await request(
        `/course-runs/${run.id}/${run.enrollment_mode === 'open' ? 'join' : 'enrollment-requests'}`,
        {
          method: 'POST',
          csrfToken: session!.csrf_token,
          body: { expected_revision: run.admissions_revision },
        },
      )
      setReload((v) => v + 1)
      setMessage(
        run.enrollment_mode === 'open'
          ? 'Đã tham gia lớp. Bạn có thể vào học.'
          : 'Đã gửi yêu cầu. Yêu cầu chờ duyệt không giữ chỗ.',
      )
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  let action
  if (membership?.enrollment_status === 'active')
    action = (
      <Link
        className="button button-primary"
        to={`/learn/${run.id}?course=${membership.course_id}&view=topics`}
      >
        Vào lớp
      </Link>
    )
  else if (membership?.enrollment_status === 'inactive')
    action = (
      <Notice kind="info">
        Giảng viên đã vô hiệu đăng ký học. Hãy liên hệ giảng viên để được kích hoạt lại.
      </Notice>
    )
  else if (membership?.request?.status === 'pending')
    action = (
      <>
        <span className="site-badge">Đang chờ duyệt</span>
        <Link to="/enrollments">Xem yêu cầu của tôi</Link>
      </>
    )
  else if (run.availability !== 'accepting')
    action = (
      <p className="site-muted">
        {
          {
            full: 'Lớp đã đủ chỗ.',
            closed: 'Đã đóng đăng ký.',
            not_started: 'Chưa đến thời gian nhận đăng ký.',
            invite_only: 'Giảng viên thêm sinh viên bằng email tài khoản.',
          }[run.availability]
        }
      </p>
    )
  else if (!session)
    action = (
      <Link
        className="button button-primary"
        to={'/login?next=' + encodeURIComponent('/courses/' + course.slug + '?run=' + run.id)}
      >
        Đăng nhập để tham gia
      </Link>
    )
  else if (session.user.role !== 'student')
    action = <p>Chức năng tham gia dành cho tài khoản sinh viên.</p>
  else
    action = (
      <button className="button button-primary" disabled={busy} onClick={() => void join()}>
        {busy
          ? 'Đang gửi…'
          : run.enrollment_mode === 'open'
            ? 'Tham gia lớp'
            : 'Gửi yêu cầu tham gia'}
      </button>
    )
  return (
    <article
      className={`site-panel site-run ${selected ? 'is-selected' : ''}`}
      id={'run-' + run.id}
    >
      <h3>Lớp {run.code}</h3>
      <span className="site-badge">{modeLabels[run.enrollment_mode]}</span>
      <p>
        Bắt đầu: {new Date(run.start_date + 'T00:00:00').toLocaleDateString('vi-VN')}
        <br />
        Giảng viên: {run.instructor_name}
      </p>
      <dl>
        <dt>Nhận đăng ký</dt>
        <dd>
          {formatDate(run.opens_at, run.timezone)} → {formatDate(run.closes_at, run.timezone)}
        </dd>
        <dt>Múi giờ</dt>
        <dd>{run.timezone}</dd>
        <dt>Chỗ học</dt>
        <dd>
          {run.capacity === null
            ? 'Không giới hạn'
            : `${run.seats_remaining} chỗ còn lại / ${run.capacity}`}
        </dd>
      </dl>
      {error && (
        <Notice>
          {error}
          <button className="button button-secondary" onClick={() => location.reload()}>
            Tải lại thông tin lớp
          </button>
        </Notice>
      )}
      {message && <Notice kind="success">{message}</Notice>}
      <div className="site-actions">{action}</div>
    </article>
  )
}
export function CourseDetailPage({
  slug,
  session,
  selectedRun,
}: {
  slug: string
  session: Session | null
  selectedRun: string | null
}) {
  const resource = useResource<PublicCourse>('/catalog/courses/' + encodeURIComponent(slug))
  if (resource.error instanceof ApiError && resource.error.status === 404)
    return (
      <Empty title="Không tìm thấy học phần công khai">
        <p>
          Học phần chưa được công bố hoặc đã ẩn khỏi danh mục. Lớp đã tham gia vẫn có trong Học phần
          của tôi.
        </p>
        <Link to="/courses">Quay lại khám phá</Link>
      </Empty>
    )
  const course = resource.data
  return (
    <State {...resource}>
      {course && (
        <>
          <p className="site-breadcrumb">
            <Link to="/courses">Khám phá</Link> / {course.title}
          </p>
          <div className="site-detail">
            <section>
              <span className="eyebrow">{course.code}</span>
              <h1>{course.title}</h1>
              <p className="site-lead">{course.summary}</p>
              <div className="site-chips">
                <span className="site-badge">{course.category_name}</span>
                <span className="site-badge">{levels[course.level]}</span>
              </div>
              <p>Giảng viên: {course.instructor_name}</p>
              <MetadataContent metadata={course} />
              <Notice kind="info">
                Trang này giới thiệu học phần. PDF, quiz, trợ giảng và kết quả học tập chỉ mở cho
                thành viên lớp hợp lệ.
              </Notice>
            </section>
            <aside aria-label="Chọn lớp">
              <h2>Chọn lớp học</h2>
              <p className="site-muted">
                Đăng nhập rồi xác nhận tham gia. Yêu cầu chờ duyệt không giữ chỗ.
              </p>
              {course.runs.length ? (
                course.runs.map((run) => (
                  <RunCard
                    key={run.id}
                    run={run}
                    course={course}
                    session={session}
                    selected={selectedRun === run.id}
                  />
                ))
              ) : (
                <Empty title="Chưa có lớp được giới thiệu">
                  <p>Giảng viên chưa công bố lớp nhận đăng ký cho học phần này.</p>
                </Empty>
              )}
            </aside>
          </div>
        </>
      )}
    </State>
  )
}

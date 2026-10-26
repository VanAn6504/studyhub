import { useState } from 'react'
import type { Session } from '../api'
import { errorMessage, request } from '../api'
import { navigate } from './navigation'
import {
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
import type { JoinRequest, MyCourse, Overview, Page, Resume } from './types'
import { requestLabels } from './types'

export function resumeUrl(value: Resume) {
  const q = new URLSearchParams({
    course: value.course_id,
    view: value.view,
    page: String(value.page),
  })
  if (value.topic_id) q.set('topic', value.topic_id)
  if (value.document_version_id) q.set('document', value.document_version_id)
  return `/learn/${value.run_id}?` + q
}
export function classUrl(course: MyCourse) {
  return course.resume
    ? resumeUrl(course.resume)
    : `/learn/${course.run_id}?course=${course.course_id}&view=topics`
}
export function MyClassCard({ course }: { course: MyCourse }) {
  const state = course.progress
  return (
    <article className="site-panel my-class">
      <div className="site-chips">
        <span className="site-badge">Lớp {course.run_code}</span>
        {course.data_origin === 'synthetic' && (
          <span className="site-badge">Mô phỏng · chỉ xem</span>
        )}
        <span className="site-badge">
          {course.enrollment_status === 'inactive'
            ? 'Đăng ký bị vô hiệu'
            : course.run_status === 'closed'
              ? 'Lớp đã đóng'
              : course.run_status === 'draft'
                ? 'Lớp chưa mở'
                : 'Đang học'}
        </span>
      </div>
      <h2>{course.course_title}</h2>
      <p className="site-muted">{course.course_code}</p>
      {state && (
        <div className="site-progress">
          <strong>
            {state.percent === null
              ? 'Chưa đủ dữ liệu'
              : `${state.mastered}/${state.available} chủ đề đã đạt`}
          </strong>
          {state.percent !== null && (
            <progress value={state.mastered} max={state.available} aria-label="Tiến độ chủ đề" />
          )}
          <p>Tính theo quiz đang công bố; tỷ lệ có thể đổi khi giảng viên cập nhật quiz.</p>
        </div>
      )}
      {course.resume?.notice && <Notice kind="info">{course.resume.notice}</Notice>}
      {course.enrollment_status === 'active' ? (
        <Link to={classUrl(course)} className="button button-primary">
          {course.resume ? 'Tiếp tục học' : 'Vào lớp'}
        </Link>
      ) : (
        <p>Giảng viên đã vô hiệu đăng ký. Bạn cần liên hệ giảng viên để kích hoạt lại.</p>
      )}
    </article>
  )
}
export function LearnerOverview({ session }: { session: Session }) {
  const resource = useResource<Overview>('/me/overview'),
    data = resource.data
  return (
    <>
      <span className="eyebrow">KHÔNG GIAN HỌC TẬP</span>
      <h1>Chào {session.user.display_name}.</h1>
      <p className="site-lead">Tiếp tục việc đang học, theo dõi kết quả và chọn bước tiếp theo.</p>
      <State {...resource}>
        {data && (
          <>
            <section className="site-panel site-continue">
              <span className="site-badge">Tiếp tục học</span>
              {data.resume ? (
                <>
                  <h2>{data.resume.course_title}</h2>
                  <p>
                    Lớp {data.resume.run_code} ·{' '}
                    {data.resume.updated_at && formatDate(data.resume.updated_at)}
                  </p>
                  {data.resume.notice && <Notice kind="info">{data.resume.notice}</Notice>}
                  <Link className="button button-primary" to={resumeUrl(data.resume)}>
                    Tiếp tục học →
                  </Link>
                </>
              ) : (
                <>
                  <h2>Sẵn sàng bắt đầu một chủ đề mới?</h2>
                  <p>Chọn một lớp đã tham gia hoặc khám phá học phần để bắt đầu.</p>
                  <div className="site-actions">
                    <Link className="button button-primary" to="/my-courses">
                      Học phần của tôi
                    </Link>
                    <Link className="button button-secondary" to="/courses">
                      Khám phá học phần
                    </Link>
                  </div>
                </>
              )}
            </section>
            <div className="site-detail">
              <section>
                <div className="section-heading">
                  <h2>Lớp học của bạn</h2>
                  <Link to="/my-courses">Xem tất cả</Link>
                </div>
                {data.courses.length ? (
                  <div className="site-class-grid">
                    {data.courses.map((course) => (
                      <MyClassCard key={course.run_id} course={course} />
                    ))}
                  </div>
                ) : (
                  <Empty title="Chưa có lớp học">
                    <p>Tham gia lớp mở hoặc gửi yêu cầu để giảng viên xét duyệt.</p>
                    <Link to="/courses" className="button button-secondary">
                      Khám phá học phần
                    </Link>
                  </Empty>
                )}
                <h2>Chủ đề cần ôn</h2>
                {data.review_topics.length ? (
                  <div className="site-panel">
                    {data.review_topics.map((topic) => (
                      <p key={topic.run_id + topic.topic_id}>
                        <Link
                          to={`/learn/${topic.run_id}?course=${topic.course_id}&topic=${topic.topic_id}&view=topic`}
                        >
                          {topic.code} · {topic.title}
                        </Link>
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="site-muted">
                    Chưa có chủ đề cần ôn được xác định từ bài quiz hiện hành. Chủ đề chưa làm bài
                    vẫn là chưa đánh giá.
                  </p>
                )}
              </section>
              <aside>
                <h2>Yêu cầu đang chờ</h2>
                <div className="site-panel">
                  {data.pending_requests.length ? (
                    data.pending_requests.map((row) => (
                      <p key={row.id}>
                        {row.course_title}
                        <br />
                        <span className="site-muted">
                          Lớp {row.run_code} · {formatDate(row.requested_at)}
                        </span>
                      </p>
                    ))
                  ) : (
                    <p>Hiện không có yêu cầu chờ duyệt.</p>
                  )}
                  <Link to="/enrollments">Xem các yêu cầu của tôi →</Link>
                  <p className="site-muted">Yêu cầu chờ duyệt không giữ chỗ.</p>
                </div>
              </aside>
            </div>
          </>
        )}
      </State>
    </>
  )
}
export function MyCoursesPage({ search }: { search: string }) {
  const params = new URLSearchParams(search),
    page = pageNumber(params),
    q = params.get('q') || '',
    status = params.get('status') || 'all'
  const resource = useResource<Page<MyCourse>>(
    '/me/courses?' +
      new URLSearchParams({ q, status, limit: '12', offset: String((page - 1) * 12) }),
  )
  const change = (changes: Record<string, string | number>) =>
    void navigate(pageUrl('/my-courses', params, { page: 1, ...changes }))
  return (
    <>
      <span className="eyebrow">CÁC LỚP ĐÃ ĐĂNG KÝ</span>
      <h1>Học phần của tôi</h1>
      <p>Mỗi thẻ là một lớp học; kết quả và tiến độ được giữ riêng theo lớp.</p>
      <form
        className="site-search"
        onSubmit={(e) => {
          e.preventDefault()
          change({ q: new FormData(e.currentTarget).get('q') as string })
        }}
        key={q}
      >
        <label className="site-sr" htmlFor="my-q">
          Tìm trong lớp của tôi
        </label>
        <input
          id="my-q"
          name="q"
          defaultValue={q}
          maxLength={160}
          placeholder="Tên học phần hoặc mã lớp"
        />
        <button className="button button-primary">Tìm kiếm</button>
        <label className="site-sr" htmlFor="my-status">
          Trạng thái lớp
        </label>
        <select id="my-status" value={status} onChange={(e) => change({ status: e.target.value })}>
          <option value="all">Tất cả lớp</option>
          <option value="learning">Đang học / chưa mở</option>
          <option value="closed">Lớp đã đóng</option>
          <option value="inactive">Đăng ký bị vô hiệu</option>
        </select>
      </form>
      <State {...resource}>
        {resource.data?.items.length ? (
          <div className="site-card-grid">
            {resource.data.items.map((course) => (
              <MyClassCard key={course.run_id} course={course} />
            ))}
          </div>
        ) : (
          <Empty title="Chưa có lớp phù hợp">
            <p>Thay đổi bộ lọc hoặc khám phá học phần để chọn lớp.</p>
            <Link to="/courses">Khám phá học phần</Link>
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
    </>
  )
}
export function EnrollmentRequestsPage({ session, search }: { session: Session; search: string }) {
  const params = new URLSearchParams(search),
    status = params.get('status') || 'all',
    page = pageNumber(params)
  const [reload, setReload] = useState(0),
    [busy, setBusy] = useState(''),
    [error, setError] = useState('')
  const resource = useResource<Page<JoinRequest>>(
    '/me/enrollment-requests?' +
      new URLSearchParams({ status, limit: '12', offset: String((page - 1) * 12) }),
    reload,
  )
  async function cancel(row: JoinRequest) {
    setBusy(row.id)
    setError('')
    try {
      await request(`/me/enrollment-requests/${row.id}/cancel`, {
        method: 'POST',
        csrfToken: session.csrf_token,
      })
      setReload((v) => v + 1)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy('')
    }
  }
  return (
    <>
      <h1>Yêu cầu tham gia lớp</h1>
      <p>Yêu cầu chờ duyệt không giữ chỗ. Giảng viên sẽ kiểm tra điều kiện và chỗ học khi duyệt.</p>
      <label className="site-compact-field">
        Trạng thái
        <select
          aria-label="Trạng thái"
          value={status}
          onChange={(e) =>
            void navigate(pageUrl('/enrollments', params, { status: e.target.value, page: 1 }))
          }
        >
          <option value="all">Tất cả trạng thái</option>
          {Object.entries(requestLabels).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {error && <Notice>{error}</Notice>}
      <State {...resource}>
        {resource.data?.items.length ? (
          resource.data.items.map((row) => (
            <article className="site-panel" key={row.id}>
              <div className="section-heading">
                <h2>{row.course_title}</h2>
                <span className="site-badge">{requestLabels[row.status]}</span>
              </div>
              <p>
                Lớp {row.run_code} · Gửi {formatDate(row.requested_at)}
              </p>
              {row.reason && <p>Lý do: {row.reason}</p>}
              <div className="site-actions">
                {row.status === 'pending' && (
                  <button
                    className="button button-secondary"
                    disabled={!!busy}
                    onClick={() => void cancel(row)}
                  >
                    {busy === row.id ? 'Đang hủy…' : 'Hủy yêu cầu'}
                  </button>
                )}
                {row.slug && (
                  <Link to={'/courses/' + row.slug + '?run=' + row.run_id}>Xem thông tin lớp</Link>
                )}
                {row.status === 'approved' && (
                  <Link to="/my-courses" className="button button-primary">
                    Học phần của tôi
                  </Link>
                )}
              </div>
            </article>
          ))
        ) : (
          <Empty title="Chưa có yêu cầu phù hợp">
            <Link to="/courses">Khám phá lớp học</Link>
          </Empty>
        )}
        {resource.data && (
          <Pagination
            page={page}
            total={resource.data.total}
            limit={12}
            onPage={(p) => void navigate(pageUrl('/enrollments', params, { page: p }))}
          />
        )}
      </State>
    </>
  )
}

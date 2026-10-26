import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage, request } from '../api'
import type { Session } from '../api'
import { MetadataContent } from './CatalogPages'
import {
  Empty,
  formatDate,
  Link,
  Notice,
  pageNumber,
  pageUrl,
  Pagination,
  State,
  useFormGuard,
  useResource,
} from './ui'
import { navigate } from './navigation'
import type {
  AdmissionSettings,
  Category,
  JoinRequest,
  Metadata,
  Page,
  Publication,
  TeachingOverview,
} from './types'
import { levels, modeLabels, requestLabels } from './types'

export function TeacherOverview({
  section = 'overview',
}: {
  section?: 'overview' | 'courses' | 'classes' | 'requests'
}) {
  const resource = useResource<TeachingOverview>('/teaching/overview'),
    data = resource.data
  const titles = {
    overview: 'Tổng quan giảng dạy',
    courses: 'Học phần quản lý',
    classes: 'Lớp học',
    requests: 'Yêu cầu cần duyệt',
  }
  return (
    <>
      <span className="eyebrow">KHÔNG GIAN GIẢNG VIÊN</span>
      <div className="section-heading">
        <h1>{titles[section]}</h1>
        <Link className="button button-primary" to="/teaching/new-course">
          Tạo học phần
        </Link>
      </div>
      <State {...resource}>
        {data && (
          <>
            {section === 'overview' && (
              <section className="site-feature-grid site-stats">
                <div>
                  <strong>{data.courses.length}</strong>
                  <p>Học phần thuộc quyền quản lý</p>
                </div>
                <div>
                  <strong>{data.runs.filter((r) => r.status === 'active').length}</strong>
                  <p>Lớp đang mở</p>
                </div>
                <div>
                  <strong>{data.pending_requests}</strong>
                  <p>Yêu cầu đang chờ xét duyệt</p>
                  <Link to="/teaching/requests">Xem yêu cầu →</Link>
                </div>
              </section>
            )}
            {['overview', 'courses'].includes(section) && (
              <section>
                <h2>Học phần của bạn</h2>
                {data.courses.length ? (
                  <div className="site-card-grid">
                    {data.courses.map((course) => (
                      <article key={course.id} className="site-panel">
                        <span className="eyebrow">{course.code}</span>
                        <h2>{course.title}</h2>
                        <span className="site-badge">
                          {course.publication_status === 'published'
                            ? 'Có trong danh mục'
                            : 'Đang ẩn khỏi danh mục'}
                        </span>
                        <div className="site-actions">
                          <Link
                            className="button button-primary"
                            to={`/teaching/workspace/${course.id}?view=topics`}
                          >
                            Quản lý nội dung
                          </Link>
                          <Link to={`/teaching/courses/${course.id}/overview`}>
                            Giới thiệu công khai
                          </Link>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <Empty title="Chưa có học phần">
                    <p>Tạo học phần để chuẩn bị chủ đề, tài liệu và các lớp riêng.</p>
                  </Empty>
                )}
              </section>
            )}
            {section !== 'courses' && (
              <section>
                <h2>{section === 'requests' ? 'Các lớp có yêu cầu chờ' : 'Các lớp của bạn'}</h2>
                {data.runs.filter((run) => section !== 'requests' || run.pending_requests > 0)
                  .length ? (
                  data.runs
                    .filter((run) => section !== 'requests' || run.pending_requests > 0)
                    .map((run) => (
                      <article className="site-panel" key={run.id}>
                        <div className="section-heading">
                          <div>
                            <h3>{run.code}</h3>
                            <p>{data.courses.find((c) => c.id === run.course_id)?.title}</p>
                          </div>
                          <span className="site-badge">
                            {run.status === 'active'
                              ? 'Đang mở'
                              : run.status === 'closed'
                                ? 'Đã đóng'
                                : 'Bản nháp'}{' '}
                            · {run.pending_requests} chờ duyệt
                          </span>
                        </div>
                        <div className="site-actions">
                          <Link
                            className="button button-primary"
                            to={`/teaching/runs/${run.id}/admissions`}
                          >
                            Tuyển sinh và duyệt yêu cầu
                          </Link>
                          <Link
                            to={`/teaching/workspace/${run.course_id}?view=classes&class=${run.id}`}
                          >
                            Quản lý lớp
                          </Link>
                        </div>
                      </article>
                    ))
                ) : (
                  <Empty
                    title={
                      section === 'requests' ? 'Không có yêu cầu chờ duyệt' : 'Chưa có lớp học'
                    }
                  >
                    <p>Chuẩn bị nội dung học phần, sau đó tạo lớp trong màn hình quản lý.</p>
                  </Empty>
                )}
              </section>
            )}
          </>
        )}
      </State>
    </>
  )
}
export function PublicationPage({ courseId, session }: { courseId: string; session: Session }) {
  const [reload, setReload] = useState(0),
    [form, setForm] = useState<Metadata | null>(null),
    [saved, setSaved] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [preview, setPreview] = useState(false),
    [reviewed, setReviewed] = useState(false)
  const resource = useResource<Publication>(`/teaching/courses/${courseId}/publication`, reload),
    categories = useResource<Category[]>('/teaching/categories')
  useEffect(() => {
    if (resource.data) {
      setForm(resource.data.draft)
      setSaved(JSON.stringify(resource.data.draft))
      setReviewed(false)
    }
  }, [resource.data])
  const dirty = !!form && JSON.stringify(form) !== saved,
    guard = useFormGuard(dirty, busy)
  async function save(e: FormEvent) {
    e.preventDefault()
    if (!form) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      const value = await request<Publication>(`/teaching/courses/${courseId}/publication`, {
        method: 'PATCH',
        csrfToken: session.csrf_token,
        body: {
          ...form,
          ...Object.fromEntries(
            ['objectives', 'prerequisites', 'outline', 'material_titles'].map((key) => [
              key,
              form[key as 'objectives'].map((line) => line.trim()).filter(Boolean),
            ]),
          ),
        },
      })
      setForm(value.draft)
      setSaved(JSON.stringify(value.draft))
      setMessage('Đã lưu bản nháp giới thiệu. Thông tin công khai chưa thay đổi.')
      setReviewed(false)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  async function publish(action: 'publish' | 'hide') {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await request(`/teaching/courses/${courseId}/${action}`, {
        method: 'POST',
        csrfToken: session.csrf_token,
      })
      setReload((v) => v + 1)
      setMessage(
        action === 'publish'
          ? 'Đã công bố thông tin giới thiệu trong danh mục.'
          : 'Đã ẩn khỏi danh mục. Quyền học và kết quả của sinh viên vẫn được giữ.',
      )
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <p>
        <Link to="/teaching/courses">Học phần quản lý</Link> / Giới thiệu công khai
      </p>
      <h1>Giới thiệu học phần</h1>
      <p>Chỉ metadata bên dưới được công bố. Tài liệu PDF, quiz, đáp án và kết quả vẫn riêng tư.</p>
      <State {...resource}>
        {form && resource.data && (
          <>
            <div className="site-actions">
              <span className="site-badge">
                {resource.data.status === 'published' ? 'Đang công bố' : 'Đang ẩn'}
              </span>
              <Link to={`/teaching/workspace/${courseId}?view=topics`}>
                Quản lý nội dung học tập
              </Link>
              {resource.data.status === 'published' && (
                <Link to={'/courses/' + resource.data.slug}>Xem trang công khai</Link>
              )}
            </div>
            {error && <Notice>{error}</Notice>}
            {guard && <Notice>{guard}</Notice>}
            {message && <Notice kind="success">{message}</Notice>}
            <section className="site-panel">
              <form className="site-form" onSubmit={save}>
                <fieldset disabled={busy}>
                  <label>
                    Tên giới thiệu học phần
                    <input
                      required
                      maxLength={200}
                      value={form.title}
                      onChange={(e) => setForm({ ...form, title: e.target.value })}
                    />
                  </label>
                  <label>
                    Tóm tắt
                    <textarea
                      aria-label="Tóm tắt"
                      maxLength={400}
                      value={form.summary}
                      onChange={(e) => setForm({ ...form, summary: e.target.value })}
                    />
                  </label>
                  <label>
                    Giới thiệu chi tiết
                    <textarea
                      aria-label="Giới thiệu chi tiết"
                      maxLength={12000}
                      value={form.description}
                      onChange={(e) => setForm({ ...form, description: e.target.value })}
                    />
                  </label>
                  <div className="site-form-grid">
                    <label>
                      Lĩnh vực
                      <select
                        aria-label="Lĩnh vực"
                        value={form.category_code || ''}
                        onChange={(e) =>
                          setForm({ ...form, category_code: e.target.value || null })
                        }
                      >
                        <option value="">Chọn lĩnh vực</option>
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
                        value={form.level}
                        onChange={(e) =>
                          setForm({ ...form, level: e.target.value as Metadata['level'] })
                        }
                      >
                        {Object.entries(levels).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {(
                    [
                      ['objectives', 'Mục tiêu học tập'],
                      ['prerequisites', 'Kiến thức đầu vào'],
                      ['outline', 'Đề cương'],
                      ['material_titles', 'Tên tài liệu được giới thiệu'],
                    ] as const
                  ).map(([key, label]) => (
                    <label key={key}>
                      {label} · mỗi dòng một mục
                      <textarea
                        aria-label={`${label} · mỗi dòng một mục`}
                        value={form[key].join('\n')}
                        onChange={(e) => setForm({ ...form, [key]: e.target.value.split('\n') })}
                      />
                    </label>
                  ))}
                  <p className="site-muted">
                    Không nhập đáp án quiz, nội dung PDF riêng tư hoặc thông tin cá nhân vào phần
                    giới thiệu.
                  </p>
                  <div className="site-actions">
                    <button className="button button-primary">
                      {busy ? 'Đang lưu…' : 'Lưu bản nháp giới thiệu'}
                    </button>
                    <button
                      className="button button-secondary"
                      type="button"
                      onClick={() => {
                        setForm(JSON.parse(saved))
                        setError('')
                        setMessage('')
                      }}
                    >
                      Hủy chỉnh sửa
                    </button>
                    <button
                      className="button button-secondary"
                      type="button"
                      aria-expanded={preview}
                      onClick={() => setPreview((v) => !v)}
                    >
                      Xem trước giới thiệu
                    </button>
                  </div>
                </fieldset>
              </form>
            </section>
            {preview && (
              <section className="site-preview" aria-label="Bản xem trước giới thiệu">
                <span className="eyebrow">XEM TRƯỚC · CHƯA TỰ CÔNG BỐ</span>
                <h2>{form.title}</h2>
                <p>{form.summary}</p>
                <MetadataContent
                  metadata={{
                    ...form,
                    objectives: form.objectives.filter(Boolean),
                    prerequisites: form.prerequisites.filter(Boolean),
                    outline: form.outline.filter(Boolean),
                    material_titles: form.material_titles.filter(Boolean),
                  }}
                />
              </section>
            )}
            <section className="site-panel">
              <h2>Công bố trong danh mục</h2>
              <p>
                Lưu nháp, xem trước và kiểm tra tóm tắt, giới thiệu, lĩnh vực trước khi công bố.
              </p>
              <label className="site-checkbox">
                <input
                  type="checkbox"
                  checked={reviewed}
                  disabled={busy || dirty}
                  onChange={(e) => setReviewed(e.target.checked)}
                />
                Tôi đã xem trước và kiểm tra thông tin sẽ công khai.
              </label>
              <div className="site-actions">
                <button
                  className="button button-primary"
                  disabled={busy || dirty || !reviewed}
                  onClick={() => void publish('publish')}
                >
                  Công bố giới thiệu
                </button>
                {resource.data.status === 'published' && (
                  <button
                    className="button button-secondary"
                    disabled={busy || dirty}
                    onClick={() => void publish('hide')}
                  >
                    Ẩn khỏi danh mục
                  </button>
                )}
              </div>
              {dirty && (
                <p className="site-muted">Có thay đổi chưa lưu. Lưu bản nháp trước khi công bố.</p>
              )}
            </section>
          </>
        )}
      </State>
    </>
  )
}
function localDate(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
export function AdmissionsPage({
  runId,
  session,
  search,
}: {
  runId: string
  session: Session
  search: string
}) {
  const [reload, setReload] = useState(0),
    [form, setForm] = useState({
      enrollment_mode: 'invite_only',
      listed: false,
      opens_at: '',
      closes_at: '',
      capacity: '',
    }),
    [saved, setSaved] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [reasons, setReasons] = useState<Record<string, string>>({})
  const params = new URLSearchParams(search),
    status = params.get('status') || 'pending',
    page = pageNumber(params)
  const resource = useResource<AdmissionSettings>(`/teaching/runs/${runId}/admissions`, reload),
    requests = useResource<Page<JoinRequest>>(
      `/teaching/runs/${runId}/requests?` +
        new URLSearchParams({ status, limit: '12', offset: String((page - 1) * 12) }),
      reload,
    )
  useEffect(() => {
    if (resource.data) {
      const row = resource.data,
        value = {
          enrollment_mode: row.enrollment_mode,
          listed: row.listed,
          opens_at: localDate(row.opens_at),
          closes_at: localDate(row.closes_at),
          capacity: row.capacity?.toString() || '',
        }
      setForm(value)
      setSaved(JSON.stringify(value))
    }
  }, [resource.data])
  const dirty = !!saved && JSON.stringify(form) !== saved,
    guard = useFormGuard(dirty || Object.values(reasons).some(Boolean), busy)
  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await request(`/teaching/runs/${runId}/admissions`, {
        method: 'PATCH',
        csrfToken: session.csrf_token,
        body: {
          enrollment_mode: form.enrollment_mode,
          listed: form.listed,
          opens_at: form.opens_at ? new Date(form.opens_at).toISOString() : null,
          closes_at: form.closes_at ? new Date(form.closes_at).toISOString() : null,
          capacity: form.capacity ? Number(form.capacity) : null,
          expected_revision: resource.data!.admissions_revision,
        },
      })
      setReload((v) => v + 1)
      setMessage('Đã lưu cấu hình tuyển sinh.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  async function decide(row: JoinRequest, action: 'approve' | 'reject') {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await request(`/teaching/requests/${row.id}/decision`, {
        method: 'POST',
        csrfToken: session.csrf_token,
        body: { action, reason: reasons[row.id] || '' },
      })
      setReasons((all) => ({ ...all, [row.id]: '' }))
      setReload((v) => v + 1)
      setMessage(action === 'approve' ? 'Đã duyệt sinh viên vào lớp.' : 'Đã từ chối yêu cầu.')
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <h1>Tuyển sinh và yêu cầu tham gia</h1>
      <State {...resource}>
        {resource.data && (
          <>
            <p>
              {resource.data.course_title} · Lớp {resource.data.code}
            </p>
            <div className="site-actions">
              <Link
                to={`/teaching/workspace/${resource.data.course_id}?view=classes&class=${runId}`}
              >
                Quản lý lớp và thêm sinh viên bằng email
              </Link>
            </div>
            {error && <Notice>{error}</Notice>}
            {guard && <Notice>{guard}</Notice>}
            {message && <Notice kind="success">{message}</Notice>}
            <Notice kind="info">
              Yêu cầu chờ duyệt không giữ chỗ. Hệ thống kiểm tra cửa sổ nhận đăng ký và chỗ trống
              tại thời điểm tham gia hoặc duyệt.
            </Notice>
            <section className="site-panel">
              <h2>Chính sách tham gia lớp</h2>
              <p>
                {resource.data.active_students} sinh viên đang được kích hoạt ·{' '}
                {resource.data.status === 'active'
                  ? 'Lớp đang mở'
                  : resource.data.status === 'closed'
                    ? 'Lớp đã đóng'
                    : 'Lớp nháp'}
              </p>
              <form className="site-form" onSubmit={save}>
                <fieldset disabled={busy || resource.data.data_origin === 'synthetic'}>
                  <label>
                    Hình thức tham gia
                    <select
                      aria-label="Hình thức tham gia"
                      value={form.enrollment_mode}
                      onChange={(e) => setForm({ ...form, enrollment_mode: e.target.value })}
                    >
                      {Object.entries(modeLabels).map(([key, label]) => (
                        <option key={key} value={key}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="site-checkbox">
                    <input
                      type="checkbox"
                      checked={form.listed}
                      onChange={(e) => setForm({ ...form, listed: e.target.checked })}
                    />
                    Giới thiệu lớp trên trang học phần đã công bố
                  </label>
                  <p className="site-muted">
                    Giờ nhập theo thiết bị: {Intl.DateTimeFormat().resolvedOptions().timeZone}. Lớp
                    dùng múi giờ {resource.data.timezone}; ngày bắt đầu học độc lập với tuyển sinh.
                  </p>
                  <div className="site-form-grid">
                    <label>
                      Mở nhận đăng ký
                      <input
                        type="datetime-local"
                        value={form.opens_at}
                        onChange={(e) => setForm({ ...form, opens_at: e.target.value })}
                      />
                    </label>
                    <label>
                      Đóng nhận đăng ký
                      <input
                        type="datetime-local"
                        min={form.opens_at || undefined}
                        value={form.closes_at}
                        onChange={(e) => setForm({ ...form, closes_at: e.target.value })}
                      />
                    </label>
                  </div>
                  <label>
                    Giới hạn chỗ · để trống nếu không giới hạn
                    <input
                      type="number"
                      min={Math.max(1, resource.data.active_students)}
                      max={100000}
                      step={1}
                      value={form.capacity}
                      onChange={(e) => setForm({ ...form, capacity: e.target.value })}
                    />
                  </label>
                  <div className="site-actions">
                    <button className="button button-primary">Lưu cấu hình tuyển sinh</button>
                    <button
                      className="button button-secondary"
                      type="button"
                      onClick={() => {
                        setForm(JSON.parse(saved))
                        setError('')
                      }}
                    >
                      Hủy chỉnh sửa
                    </button>
                  </div>
                </fieldset>
              </form>
            </section>
            <div className="section-heading">
              <h2>Yêu cầu tham gia</h2>
              <label>
                Lọc yêu cầu
                <select
                  aria-label="Lọc yêu cầu"
                  value={status}
                  onChange={(e) =>
                    void navigate(
                      pageUrl(`/teaching/runs/${runId}/admissions`, params, {
                        status: e.target.value,
                        page: 1,
                      }),
                    )
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
            </div>
            <State {...requests}>
              {requests.data?.items.length ? (
                requests.data.items.map((row) => (
                  <article className="site-panel" key={row.id}>
                    <div className="section-heading">
                      <h3>{row.student_name}</h3>
                      <span className="site-badge">{requestLabels[row.status]}</span>
                    </div>
                    <p>
                      {row.student_email} · Gửi{' '}
                      {formatDate(row.requested_at, resource.data!.timezone)}
                    </p>
                    {row.status === 'pending' ? (
                      <>
                        <label>
                          Lý do phản hồi cho {row.student_name}
                          <textarea
                            aria-label={`Lý do phản hồi cho ${row.student_name}`}
                            maxLength={1000}
                            disabled={busy}
                            value={reasons[row.id] || ''}
                            onChange={(e) =>
                              setReasons((all) => ({ ...all, [row.id]: e.target.value }))
                            }
                          />
                        </label>
                        <div className="site-actions">
                          <button
                            className="button button-primary"
                            disabled={busy || dirty}
                            onClick={() => void decide(row, 'approve')}
                          >
                            Duyệt vào lớp
                          </button>
                          <button
                            className="button button-secondary"
                            disabled={busy || dirty}
                            onClick={() => void decide(row, 'reject')}
                          >
                            Từ chối yêu cầu
                          </button>
                        </div>
                      </>
                    ) : (
                      <p>Phản hồi: {row.reason || 'Không có nội dung phản hồi.'}</p>
                    )}
                  </article>
                ))
              ) : (
                <Empty title="Không có yêu cầu phù hợp" />
              )}
              {requests.data && (
                <Pagination
                  page={page}
                  total={requests.data.total}
                  limit={12}
                  onPage={(p) =>
                    void navigate(
                      pageUrl(`/teaching/runs/${runId}/admissions`, params, { page: p }),
                    )
                  }
                />
              )}
            </State>
          </>
        )}
      </State>
    </>
  )
}

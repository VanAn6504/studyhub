import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, errorMessage, listAll, request } from './api'
import type { CourseRun, Material, Session, Topic } from './api'
import type {
  ActivityEvent,
  Attempt,
  LearningDocument,
  LearningEventInput,
  StudentReport,
} from './learningTypes'
const PdfViewer = lazy(() => import('./PdfViewer'))
import QuizPlayer from './QuizPlayer'
import TeacherQuizEditor from './TeacherQuizEditor'
import GuidancePanel, { stateLabels } from './GuidancePanel'
import RagDocumentPanel from './RagDocumentPanel'
import ChatPanel from './ChatPanel'
import './learning.css'

export default function LearningWorkspace({
  courseId,
  run,
  topics,
  session,
  onChanged,
  onExpired,
}: {
  courseId: string
  run?: CourseRun
  topics: Topic[]
  session: Session
  onChanged: () => void
  onExpired: () => void
}) {
  const teacher = session.user.role === 'teacher'
  const [documents, setDocuments] = useState<LearningDocument[]>([])
  const [topicId, setTopicId] = useState(topics[0]?.id || '')
  const topic = topics.find((value) => value.id === topicId) || topics[0]
  const [history, setHistory] = useState<Attempt[]>([])
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [eventCount, setEventCount] = useState(0)
  const [report, setReport] = useState<StudentReport[]>([])
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [viewer, setViewer] = useState<{ versionId: string; title: string; page: number } | null>(
    null,
  )
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [upload, setUpload] = useState({ code: '', title: '' })
  const [mapping, setMapping] = useState({ version: '', start: 1, end: 1 })
  const [pending, setPending] = useState(0)
  const [logError, setLogError] = useState('')
  const queue = useRef<LearningEventInput[]>([])
  const flushing = useRef(false)
  const mounted = useRef(true)
  const topicAnchor = useRef<HTMLDivElement>(null)
  const csrfToken = session.csrf_token
  const canWrite = !teacher && run?.status === 'active' && run.data_origin === 'real'
  const fail = useCallback(
    (failure: unknown) => {
      if (!mounted.current) return
      setError(errorMessage(failure))
      if (failure instanceof ApiError && failure.status === 401) onExpired()
    },
    [onExpired],
  )
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])
  useEffect(() => {
    let stopped = false
    setLoading(true)
    setError('')
    const path = teacher ? `/courses/${courseId}/documents` : `/course-runs/${run?.id}/documents`
    const tasks = [
      listAll<LearningDocument>(path).then((value) => {
        if (!stopped) setDocuments(value)
      }),
    ]
    if (run && !teacher) {
      tasks.push(
        listAll<Attempt>(`/course-runs/${run.id}/results`).then((value) => {
          if (!stopped) setHistory(value)
        }),
      )
      tasks.push(
        request<{ items: ActivityEvent[]; total: number }>(
          `/course-runs/${run.id}/events?limit=10`,
        ).then((value) => {
          if (!stopped) {
            setEvents(value.items)
            setEventCount(value.total)
          }
        }),
      )
    }
    if (run && teacher)
      tasks.push(
        listAll<StudentReport>(`/course-runs/${run.id}/report`).then((value) => {
          if (!stopped) setReport(value)
        }),
      )
    Promise.all(tasks)
      .catch((failure) => {
        if (!stopped) fail(failure)
      })
      .finally(() => {
        if (!stopped) setLoading(false)
      })
    return () => {
      stopped = true
    }
  }, [courseId, run?.id, teacher, reload])
  function changed() {
    setReload((value) => value + 1)
    onChanged()
  }
  async function mutate(action: () => Promise<unknown>, success: string) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await action()
      setMessage(success)
      changed()
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }
  async function uploadPdf(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    if (file.size > 20 * 1024 * 1024) {
      fail(new Error('PDF tối đa 20 MiB.'))
      return
    }
    const body = new FormData()
    body.append('file', file)
    body.append('code', upload.code)
    body.append('title', upload.title)
    await mutate(
      () => request(`/courses/${courseId}/documents`, { method: 'POST', csrfToken, body }),
      'Đã upload PDF nháp. Kiểm tra và công bố để sinh viên xem.',
    )
  }
  async function addVersion(document: LearningDocument, file?: File) {
    if (!file) return
    if (file.size > 20 * 1024 * 1024) {
      fail(new Error('PDF tối đa 20 MiB.'))
      return
    }
    const body = new FormData()
    body.append('file', file)
    await mutate(
      () => request(`/documents/${document.id}/versions`, { method: 'POST', csrfToken, body }),
      'Đã thêm phiên bản PDF. Liên kết chủ đề vẫn dùng bản đã chọn trước đó.',
    )
  }
  async function mapMaterial(event: FormEvent) {
    event.preventDefault()
    if (!topic) return
    const items = topic.materials.map((value) => ({
      document_version_id: value.document_version_id,
      page_start: value.page_start,
      page_end: value.page_end,
      order_index: value.order_index,
    }))
    items.push({
      document_version_id: mapping.version,
      page_start: mapping.start,
      page_end: mapping.end,
      order_index: Math.max(0, ...items.map((value) => value.order_index)) + 1,
    })
    await mutate(
      () => request(`/topics/${topic.id}/materials`, { method: 'PUT', csrfToken, body: { items } }),
      'Đã gắn tài liệu vào chủ đề.',
    )
  }
  function removeMaterial(material: Material) {
    if (!topic) return
    const items = topic.materials
      .filter((value) => value.order_index !== material.order_index)
      .map((value) => ({
        document_version_id: value.document_version_id,
        page_start: value.page_start,
        page_end: value.page_end,
        order_index: value.order_index,
      }))
    void mutate(
      () => request(`/topics/${topic.id}/materials`, { method: 'PUT', csrfToken, body: { items } }),
      'Đã bỏ liên kết tài liệu; PDF và lịch sử vẫn được giữ.',
    )
  }
  const flush = useCallback(async () => {
    if (flushing.current || !run || !canWrite || !queue.current.length) return
    flushing.current = true
    if (mounted.current) setLogError('')
    try {
      while (queue.current.length && mounted.current) {
        const batch = queue.current.slice(0, 50)
        await request(`/course-runs/${run.id}/events`, {
          method: 'POST',
          csrfToken,
          body: { schema_version: 'learning_event_v1', events: batch },
        })
        queue.current.splice(0, batch.length)
        if (mounted.current) setPending(queue.current.length)
      }
      if (mounted.current) setReload((value) => value + 1)
    } catch (failure) {
      if (mounted.current)
        setLogError(
          'Chưa gửi được log. Bấm gửi lại trước khi rời lượt học; ID log được giữ nguyên để tránh ghi trùng.',
        )
      if (failure instanceof ApiError && failure.status === 401) fail(failure)
    } finally {
      flushing.current = false
    }
  }, [run?.id, canWrite, csrfToken, fail])
  const record = useCallback(
    (event: LearningEventInput) => {
      if (!canWrite) return
      queue.current.push(event)
      setPending(queue.current.length)
      void flush()
    },
    [canWrite, flush],
  )
  async function resume(value: Attempt) {
    try {
      setAttempt(await request<Attempt>(`/attempts/${value.id}`))
      setTopicId(value.topic_id)
      setError('')
    } catch (failure) {
      fail(failure)
    }
  }
  const sourceVersions = documents
    .filter((value) => value.status === 'published')
    .flatMap((document) => document.versions.map((version) => ({ ...version, document })))
  return (
    <section className="learning-workspace" aria-labelledby="learning-workspace-heading">
      <div className="section-heading">
        <div>
          <span className="eyebrow">{teacher ? 'TÀI LIỆU & ĐÁNH GIÁ' : 'KHÔNG GIAN HỌC TẬP'}</span>
          <h2 id="learning-workspace-heading">
            {teacher ? 'Chuẩn bị nội dung học tập' : 'Đọc tài liệu và làm quiz'}
          </h2>
        </div>
        <button
          className="button button-secondary"
          disabled={loading}
          onClick={() => {
            changed()
            setError('')
          }}
        >
          Làm mới
        </button>
      </div>
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="notice notice-success" role="status">
          {message}
        </p>
      )}
      {loading && <p role="status">Đang tải tài liệu và bài làm…</p>}
      {!teacher && run && <GuidancePanel key={run.id} run={run} csrfToken={csrfToken} refresh={reload} topics={topics}
        onExpired={onExpired} onTopic={id => {
          setTopicId(id); setAttempt(null)
          requestAnimationFrame(() => topicAnchor.current?.scrollIntoView({ block: 'start' }))
        }}
        onRead={material => setViewer({ versionId: material.document_version_id, title: material.title, page: material.page_start })} />}
      {teacher && (
        <details className="upload-section">
          <summary>Upload tài liệu PDF mới</summary>
          <form className="learning-form" onSubmit={uploadPdf}>
            <fieldset disabled={busy}>
              <div className="learning-form-grid">
                <label>
                  Mã tài liệu (ví dụ CH01)
                  <input
                    required
                    pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                    maxLength={64}
                    value={upload.code}
                    onChange={(event) => setUpload({ ...upload, code: event.target.value })}
                  />
                </label>
                <label>
                  Tên tài liệu
                  <input
                    required
                    maxLength={200}
                    value={upload.title}
                    onChange={(event) => setUpload({ ...upload, title: event.target.value })}
                  />
                </label>
              </div>
              <label>
                Tệp PDF · tối đa 20 MiB, 500 trang
                <input
                  required
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(event) => setFile(event.target.files?.[0] || null)}
                />
              </label>
              <button className="button button-primary" disabled={!file}>
                {busy ? 'Đang upload…' : 'Upload PDF nháp'}
              </button>
            </fieldset>
          </form>
        </details>
      )}
      <div className="document-grid">
        {documents.map((document) => (
          <article className="document-card" key={document.id}>
            <div>
              <span className="topic-code">{document.code}</span>
              <h3>{document.title}</h3>
              <p className="muted">
                {document.status === 'published'
                  ? 'Đã công bố'
                  : document.status === 'draft'
                    ? 'Bản nháp'
                    : 'Đã lưu trữ'}{' '}
                · {document.versions.length} phiên bản
              </p>
            </div>
            {document.versions.map((version) => (
              <div className="document-version-group" key={version.id}>
              <div className="document-version">
                <span>
                  Bản {version.version} · {version.page_count} trang
                </span>
                <button
                  className="text-button"
                  disabled={!run}
                  onClick={() =>
                    setViewer({
                      versionId: version.id,
                      title: `${document.code} · ${document.title} · bản ${version.version}`,
                      page: 1,
                    })
                  }
                >
                  Xem PDF
                </button>
              </div>
              {teacher && <RagDocumentPanel versionId={version.id} documentStatus={document.status} csrfToken={csrfToken}
                onExpired={onExpired} onPublished={() => { setReload(v => v + 1); onChanged() }} />}
              </div>
            ))}
            {teacher && (
              <div className="document-actions">
                <button
                  className="button button-secondary"
                  disabled={busy}
                  onClick={() =>
                    void mutate(
                      () =>
                        request(`/documents/${document.id}`, {
                          method: 'PATCH',
                          csrfToken,
                          body: {
                            status: document.status === 'published' ? 'archived' : 'published',
                          },
                        }),
                      document.status === 'published' ? 'Đã lưu trữ tài liệu.' : 'Đã công bố PDF.',
                    )
                  }
                >
                  {document.status === 'published' ? 'Lưu trữ PDF' : 'Chỉ công bố PDF'}
                </button>
                <label>
                  Thêm bản PDF
                  <input
                    type="file"
                    accept="application/pdf,.pdf"
                    disabled={busy}
                    onChange={(event) => {
                      void addVersion(document, event.target.files?.[0])
                      event.target.value = ''
                    }}
                  />
                </label>
              </div>
            )}
          </article>
        ))}
      </div>
      {!loading && !documents.length && (
        <p className="muted">
          {teacher
            ? 'Chưa có PDF. Upload tài liệu nguồn của học phần để bắt đầu.'
            : 'Giảng viên chưa công bố tài liệu PDF.'}
        </p>
      )}
      {!run && teacher && (
        <p className="muted">Chọn một lượt học để xem thử PDF trong trình xem.</p>
      )}
      {!teacher && run && <ChatPanel key={run.id} run={run} csrfToken={csrfToken} onExpired={onExpired}
        onRead={citation => setViewer({ versionId: citation.document_version_id,
          title: `${citation.document_code} · ${citation.title} · bản ${citation.version}`, page: citation.pdf_page })} />}
      {viewer && run && (
        <Suspense fallback={<p role="status">Đang mở trình xem PDF…</p>}>
          <PdfViewer
            key={`${run.id}:${viewer.versionId}:${viewer.page}`}
            runId={run.id}
            versionId={viewer.versionId}
            title={viewer.title}
            initialPage={viewer.page}
            onEvent={canWrite ? record : undefined}
            onClose={() => setViewer(null)}
          />
        </Suspense>
      )}
      {pending > 0 && (
        <p className="notice" role="status">
          {logError || `Đang gửi ${pending} log học tập…`}
          {logError && (
            <button className="text-button" onClick={() => void flush()}>
              Gửi lại log
            </button>
          )}
        </p>
      )}
      <div className="topic-tabs" aria-label="Chọn chủ đề học tập">
        {topics.map((value) => (
          <button
            className={`button ${value.id === topic?.id ? 'button-primary' : 'button-secondary'}`}
            aria-pressed={value.id === topic?.id}
            key={value.id}
            onClick={() => {
              setTopicId(value.id)
              setAttempt(null)
              setError('')
            }}
          >
            {value.code}
          </button>
        ))}
      </div>
      {topic && (
        <div className="topic-learning-content" ref={topicAnchor}>
          <h3>
            {topic.code} · {topic.title}
          </h3>
          <div className="topic-material-list">
            {topic.materials.map((material) => (
              <div key={material.order_index}>
                <span>
                  {material.document_code} · bản {material.version} · trang {material.page_start}–
                  {material.page_end}
                </span>
                <button
                  className="text-button"
                  disabled={!run}
                  onClick={() =>
                    setViewer({
                      versionId: material.document_version_id,
                      title: material.title,
                      page: material.page_start,
                    })
                  }
                >
                  Đọc tài liệu
                </button>
                {teacher && (
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => removeMaterial(material)}
                  >
                    Bỏ liên kết
                  </button>
                )}
              </div>
            ))}
          </div>
          {teacher ? (
            <>
              <details>
                <summary>Gắn khoảng trang PDF vào chủ đề</summary>
                <form className="learning-form" onSubmit={mapMaterial}>
                  <fieldset disabled={busy}>
                    <label>
                      Phiên bản PDF đã công bố
                      <select
                        aria-label="Phiên bản PDF đã công bố"
                        required
                        value={mapping.version}
                        onChange={(event) =>
                          setMapping({ ...mapping, version: event.target.value })
                        }
                      >
                        <option value="">Chọn PDF</option>
                        {sourceVersions.map((value) => (
                          <option key={value.id} value={value.id}>
                            {value.document.code} · bản {value.version} · {value.page_count} trang
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="learning-form-grid">
                      <label>
                        Từ trang
                        <input
                          required
                          type="number"
                          min={1}
                          max={500}
                          value={mapping.start}
                          onChange={(event) =>
                            setMapping({ ...mapping, start: Number(event.target.value) })
                          }
                        />
                      </label>
                      <label>
                        Đến trang
                        <input
                          required
                          type="number"
                          min={mapping.start}
                          max={500}
                          value={mapping.end}
                          onChange={(event) =>
                            setMapping({ ...mapping, end: Number(event.target.value) })
                          }
                        />
                      </label>
                    </div>
                    <button className="button button-secondary">Thêm liên kết tài liệu</button>
                  </fieldset>
                </form>
              </details>
              <TeacherQuizEditor
                key={topic.id}
                topic={topic}
                documents={documents}
                session={session}
                onChanged={changed}
                onFailure={fail}
              />
            </>
          ) : (
            run && (
              <QuizPlayer
                key={topic.id}
                run={run}
                topicId={topic.id}
                quiz={topic.quiz}
                csrfToken={csrfToken}
                attempt={attempt}
                onAttempt={setAttempt}
                onFailure={fail}
                onCompleted={changed}
              />
            )
          )}
        </div>
      )}
      {!teacher && run && (
        <section className="learning-history">
          <h3>Lịch sử bài làm</h3>
          {history.length ? (
            history.map((value) => (
              <div className="history-row" key={value.id}>
                <span>
                  {topics.find((t) => t.id === value.topic_id)?.code} ·{' '}
                  {value.status === 'completed'
                    ? `${value.score_percent?.toFixed(1)}% · ${value.passed_for_attempt_version ? 'Đạt' : 'Chưa đạt'}`
                    : 'Đang làm'}
                  <small>{new Date(value.started_at).toLocaleString('vi-VN')}</small>
                </span>
                <button className="text-button" onClick={() => void resume(value)}>
                  {value.status === 'completed' ? 'Xem kết quả' : 'Làm tiếp'}
                </button>
              </div>
            ))
          ) : (
            <p className="muted">Bạn chưa có bài làm.</p>
          )}
          <details>
            <summary>Log học tập của tôi ({eventCount} sự kiện)</summary>
            <p className="muted">
              Log ghi trang đã hiển thị; không suy ra thời gian đọc hoặc mức độ hiểu bài.
            </p>
            {events.map((value) => (
              <p key={value.id}>
                {value.type === 'page_view' ? `Xem trang ${value.pdf_page}` : 'Mở tài liệu'} ·{' '}
                {new Date(value.occurred_at).toLocaleString('vi-VN')}
              </p>
            ))}
          </details>
        </section>
      )}
      {teacher && run && (
        <section className="learning-report">
          <h3>Kết quả lượt học · {run.code}</h3>
          <p className="muted">
            Số lượt xem trang và kết quả quiz là dữ liệu quan sát; sinh viên chưa làm bài chưa được
            đánh giá.
          </p>
          {report.map((value) => (
            <article className="student-report" key={value.enrollment_id}>
              <strong>{value.display_name}</strong>
              <p>
                {value.student_email} ·{' '}
                {value.enrollment_status === 'active' ? 'Đang học' : 'Ngừng đăng ký'}
              </p>
              <p>
                {value.page_views} lượt xem trang · {value.attempt_count} bài làm
              </p>
              <p>Lộ trình {value.learning_path.revision} · {value.learning_path.steps.length} bước học/ôn</p>
              <div className="path-states">{value.learning_path.topic_states.map(item => <span className={`path-state path-${item.state}`} key={item.topic_id}>
                {item.topic_code}: {stateLabels[item.state]}{item.score_percent !== null && ` ${item.score_percent.toFixed(1)}%`}
              </span>)}</div>
              {value.latest_results.length ? (
                value.latest_results.map((result) => (
                  <p key={result.id}>
                    {topics.find((t) => t.id === result.topic_id)?.code}:{' '}
                    {result.score_percent?.toFixed(1)}% ·{' '}
                    {result.passed_for_attempt_version ? 'Đạt bản đã làm' : 'Chưa đạt'}
                    {!result.counts_for_current_mastery && ' · Có quiz mới'}
                  </p>
                ))
              ) : (
                <p className="muted">Chưa có kết quả quiz.</p>
              )}
            </article>
          ))}
        </section>
      )}
    </section>
  )
}

import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
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
import TopicEditor from './TopicEditor'
import DocumentActions from './DocumentActions'
import type { NavigationGuard, WorkspaceRoute } from './workspaceNavigation'
import './learning.css'
import { replacePosition } from './website/navigation'
import { routeHash } from './workspaceNavigation'

export default function LearningWorkspace({
  courseId,
  run,
  topics,
  session,
  onChanged,
  onExpired,
  route,
  onNavigate,
  onRegisterGuard,
  topicsLoading,
  chatSignal,
}: {
  courseId: string
  run?: CourseRun
  topics: Topic[]
  session: Session
  onChanged: () => void
  onExpired: () => void
  route: WorkspaceRoute
  onNavigate: (route: WorkspaceRoute) => Promise<boolean>
  onRegisterGuard: (guard: NavigationGuard | null) => void
  topicsLoading: boolean
  chatSignal: number
}) {
  const teacher = session.user.role === 'teacher'
  const reportVisible = teacher && route.view === 'report'
  const [documents, setDocuments] = useState<LearningDocument[]>([])
  const [topicId, setTopicId] = useState(topics[0]?.id || '')
  const topic = route.topicId
    ? topics.find((value) => value.id === route.topicId)
    : topics.find((value) => value.id === topicId) || topics[0]
  const [history, setHistory] = useState<Attempt[]>([])
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [eventCount, setEventCount] = useState(0)
  const [report, setReport] = useState<StudentReport[]>([])
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const [chatVisited, setChatVisited] = useState(false)
  const [guidanceVisited, setGuidanceVisited] = useState(false)
  const [quizVisited, setQuizVisited] = useState('')
  const [editorVisited, setEditorVisited] = useState('')
  const [quizDirty, setQuizDirty] = useState(false)
  const [quizBusy, setQuizBusy] = useState(false)
  const viewerReturn = useRef<WorkspaceRoute['view']>('topic')
  const [uploadTarget, setUploadTarget] = useState({ topicId: '', start: 1, end: '' })
  const [pendingLink, setPendingLink] = useState<{
    versionId: string
    topicId: string
    start: number
    end: number
  } | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)
  const [activityReload, setActivityReload] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [upload, setUpload] = useState({ code: '', title: '' })
  const [mapping, setMapping] = useState({ version: '', start: 1, end: 1 })
  const [pending, setPending] = useState(0)
  const [logError, setLogError] = useState('')
  const queue = useRef<LearningEventInput[]>([])
  const flushing = useRef(false)
  const flushFlight = useRef<Promise<boolean> | null>(null)
  const mounted = useRef(true)
  const csrfToken = session.csrf_token
  const canWrite = !teacher && run?.status === 'active' && run.data_origin === 'real'
  function go(view: WorkspaceRoute['view'], fields: Partial<WorkspaceRoute> = {}) {
    onNavigate({ ...route, view, ...fields })
  }
  function readPdf(versionId: string, page: number) {
    if (route.view !== 'pdf') viewerReturn.current = route.view
    setChatOpen(false)
    go('pdf', { versionId, page })
  }
  useEffect(() => {
    if (route.view === 'progress') setGuidanceVisited(true)
  }, [route.view])
  useEffect(() => {
    if (chatSignal > 0) {
      setChatVisited(true)
      setChatOpen(true)
    }
  }, [chatSignal])
  useEffect(() => {
    if (route.view === 'quiz' && topic) setQuizVisited(topic.id)
    if (route.view === 'quiz-editor' && topic) setEditorVisited(topic.id)
    setTopicId(topic?.id || '')
    setAttempt((old) => (old?.topic_id === topic?.id ? old : null))
  }, [route.view, topic?.id])
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
    setReport([])
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
    }
    if (run && reportVisible)
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
  }, [courseId, run?.id, teacher, reload, reportVisible])
  useEffect(() => {
    if (!run || teacher) return
    let stopped = false
    request<{ items: ActivityEvent[]; total: number }>(`/course-runs/${run.id}/events?limit=10`)
      .then((value) => {
        if (!stopped) {
          setEvents(value.items)
          setEventCount(value.total)
        }
      })
      .catch((failure) => {
        if (!stopped) fail(failure)
      })
    return () => {
      stopped = true
    }
  }, [run?.id, teacher, reload, activityReload])
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
    if (file.size > 100 * 1024 * 1024) {
      fail(new Error('PDF tối đa 100 MiB.'))
      return
    }
    const body = new FormData()
    body.append('file', file)
    body.append('code', upload.code)
    body.append('title', upload.title)
    setBusy(true)
    setError('')
    try {
      const uploaded = await request<LearningDocument>(`/courses/${courseId}/documents`, {
        method: 'POST',
        csrfToken,
        body,
      })
      const version = uploaded.versions[0]
      setDocuments((old) => [...old, uploaded])
      setFile(null)
      changed()
      if (uploadTarget.topicId)
        setPendingLink({
          versionId: version.id,
          topicId: uploadTarget.topicId,
          start: uploadTarget.start,
          end: Number(uploadTarget.end) || version.page_count,
        })
      go('document', { versionId: version.id })
      setMessage('Đã lưu PDF nháp. Xem trước và công bố khi sẵn sàng.')
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }
  async function addVersion(document: LearningDocument, file?: File) {
    if (!file) return
    if (file.size > 100 * 1024 * 1024) {
      fail(new Error('PDF tối đa 100 MiB.'))
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
  const flush = useCallback((): Promise<boolean> => {
    if (flushFlight.current) return flushFlight.current
    const task = (async () => {
      if (!queue.current.length) return true
      if (!run || !canWrite) return false
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
        if (mounted.current) setActivityReload((value) => value + 1)
        return queue.current.length === 0
      } catch (failure) {
        if (mounted.current)
          setLogError(
            'Chưa gửi được log. Bấm gửi lại trước khi rời lớp học; ID log được giữ nguyên để tránh ghi trùng.',
          )
        if (failure instanceof ApiError && failure.status === 401) fail(failure)
        return false
      } finally {
        flushing.current = false
      }
    })()
    flushFlight.current = task
    void task.finally(() => {
      if (flushFlight.current === task) flushFlight.current = null
    })
    return task
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
  function updateAttempt(value: Attempt | null) {
    setAttempt(value)
    if (value) setHistory((all) => [value, ...all.filter((item) => item.id !== value.id)])
    if (value?.status === 'completed' && run && !teacher) {
      void request('/me/resume', {
        method: 'PUT',
        csrfToken,
        body: {
          run_id: run.id,
          topic_id: value.topic_id,
          document_version_id: null,
          view: 'results',
          page: 1,
        },
      }).catch(() => {})
    }
  }
  async function resume(value: Attempt) {
    if (quizDirty) {
      setError('Hãy lưu hoặc đóng bài đang làm trước khi mở bài khác từ lịch sử.')
      return
    }
    try {
      const saved = await request<Attempt>(`/attempts/${value.id}`)
      if (!mounted.current) return
      if (await onNavigate({ ...route, view: 'quiz', topicId: value.topic_id })) {
        setAttempt(saved)
        setTopicId(value.topic_id)
        setError('')
      }
    } catch (failure) {
      fail(failure)
    }
  }
  useEffect(() => {
    const guard: NavigationGuard = async (next) => {
      const changingContext = !next || next.courseId !== courseId || next.runId !== (run?.id || '')
      const changingTopic = next?.topicId && next.topicId !== topic?.id
      if (quizBusy || (busy && changingContext)) {
        setError('Đang lưu dữ liệu. Hãy đợi thao tác hoàn tất.')
        return false
      }
      if (
        quizDirty &&
        (changingContext || changingTopic) &&
        !window.confirm('Bài làm có lựa chọn chưa lưu. Rời trang và bỏ các lựa chọn chưa lưu?')
      )
        return false
      if (changingContext && !(await flush())) {
        setError('Log chưa gửi xong. Gửi lại log trước khi đổi lớp hoặc rời học phần.')
        return false
      }
      return true
    }
    onRegisterGuard(guard)
    const unload = (event: BeforeUnloadEvent) => {
      if (queue.current.length || quizDirty || quizBusy) {
        event.preventDefault()
        event.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', unload)
    return () => {
      onRegisterGuard(null)
      window.removeEventListener('beforeunload', unload)
    }
  }, [courseId, run?.id, topic?.id, busy, quizBusy, quizDirty, flush, onRegisterGuard])

  async function afterPublished(versionId: string) {
    changed()
    if (!pendingLink || pendingLink.versionId !== versionId) return
    const selected = topics.find((t) => t.id === pendingLink.topicId)
    if (!selected) {
      setError('Tài liệu đã công bố nhưng chưa tìm thấy chủ đề để gắn.')
      return
    }
    try {
      if (
        selected.materials.some(
          (m) =>
            m.document_version_id === versionId &&
            m.page_start === pendingLink.start &&
            m.page_end === pendingLink.end,
        )
      ) {
        setPendingLink(null)
        return
      }
      await request(`/topics/${selected.id}/materials`, {
        method: 'PUT',
        csrfToken,
        body: {
          items: [
            ...selected.materials.map((m) => ({
              document_version_id: m.document_version_id,
              page_start: m.page_start,
              page_end: m.page_end,
              order_index: m.order_index,
            })),
            {
              document_version_id: versionId,
              page_start: pendingLink.start,
              page_end: pendingLink.end,
              order_index: Math.max(0, ...selected.materials.map((m) => m.order_index)) + 1,
            },
          ],
        },
      })
      setPendingLink(null)
      setMessage('Đã công bố và gắn tài liệu vào chủ đề.')
      onChanged()
    } catch (failure) {
      fail(failure)
    }
  }
  async function setDocumentStatus(document: LearningDocument, versionId: string) {
    setBusy(true)
    setError('')
    try {
      const status = document.status === 'published' ? 'archived' : 'published'
      await request(`/documents/${document.id}`, { method: 'PATCH', csrfToken, body: { status } })
      changed()
      if (status === 'published') await afterPublished(versionId)
      setMessage(status === 'published' ? 'Đã công bố PDF.' : 'Đã lưu trữ PDF.')
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }
  const sourceVersions = documents
    .filter((d) => d.status === 'published')
    .flatMap((document) => document.versions.map((version) => ({ ...version, document })))
  const versions = documents.flatMap((document) =>
    document.versions.map((version) => ({ ...version, document })),
  )
  const selectedVersion = versions.find((v) => v.id === route.versionId)
  const heading = (title: string, actions?: ReactNode) => (
    <div className="section-heading">
      <div>
        <h2 id="learning-workspace-heading">{title}</h2>
      </div>
      {actions}
    </div>
  )
  function quizState(value: Topic) {
    const current = history
      .filter(
        (a) =>
          a.topic_id === value.id &&
          a.status === 'completed' &&
          a.quiz_version_id === value.quiz?.published_version_id,
      )
      .sort((a, b) => (b.graded_at || '').localeCompare(a.graded_at || ''))[0]
    return !value.quiz
      ? 'Chưa có quiz'
      : !current
        ? 'Chưa đánh giá'
        : current.passed_for_attempt_version
          ? 'Đã đạt'
          : 'Cần ôn tập'
  }
  return (
    <section className="learning-workspace" aria-labelledby="learning-workspace-heading">
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
      {route.view === 'topics' && (
        <>
          {heading(
            teacher ? 'Chủ đề' : 'Nội dung học phần',
            <div className="workspace-actions">
              {teacher ? (
                <button
                  className="button button-primary"
                  onClick={() => go('topic-editor', { topicId: undefined })}
                >
                  Thêm chủ đề
                </button>
              ) : null}
            </div>,
          )}
          {topicsLoading ? (
            <p role="status">Đang tải chủ đề…</p>
          ) : !topics.length ? (
            <div className="workspace-empty">
              <h3>Chưa có chủ đề</h3>
              <p>
                {teacher
                  ? 'Thêm chủ đề đầu tiên hoặc vào Tài liệu để upload PDF.'
                  : 'Giảng viên chưa chuẩn bị chủ đề.'}
              </p>
            </div>
          ) : (
            <div className="workspace-grid">
              {topics.map((value) => (
                <article className="workspace-card topic-card" key={value.id}>
                  <span className="eyebrow">{value.code}</span>
                  <h3>{value.title}</h3>
                  <p className="muted">
                    {value.materials.length} mục tài liệu ·{' '}
                    {value.quiz ? `${value.quiz.question_count} câu quiz` : 'Chưa có quiz'}
                  </p>
                  <span className="workspace-badge">
                    {teacher
                      ? value.quiz
                        ? 'Quiz đã công bố'
                        : 'Cần chuẩn bị quiz'
                      : quizState(value)}
                  </span>
                  <div className="workspace-actions">
                    <button
                      className="button button-primary"
                      onClick={() => go('topic', { topicId: value.id })}
                    >
                      {teacher ? 'Quản lý chủ đề' : 'Vào học'}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}
      {teacher && route.view === 'topic-editor' && (
        <>
          {heading(route.topicId ? 'Chỉnh chủ đề' : 'Thêm chủ đề')}
          <TopicEditor
            key={route.topicId || 'new'}
            courseId={courseId}
            topic={route.topicId ? topic : undefined}
            topics={topics}
            csrfToken={csrfToken}
            onFailure={fail}
            onSaved={(id) => {
              changed()
              go('topic', { topicId: id })
            }}
          />
        </>
      )}
      {route.view === 'topic' && topic && (
        <>
          {heading(
            `${topic.code} · ${topic.title}`,
            <div className="workspace-actions">
              {teacher ? (
                <button className="button button-secondary" onClick={() => go('topic-editor')}>
                  Chỉnh chủ đề
                </button>
              ) : null}
            </div>,
          )}
          <div className="workspace-topic-detail">
            <h3>Mục tiêu học tập</h3>
            {topic.objectives.length ? (
              <ul>
                {topic.objectives.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">Chưa có mục tiêu.</p>
            )}
            {!!topic.prerequisite_topic_ids.length && (
              <p className="muted">
                Kiến thức tiên quyết:{' '}
                {topic.prerequisite_topic_ids
                  .map((id) => topics.find((t) => t.id === id)?.code || '')
                  .join(', ')}
              </p>
            )}
            <h2>Tài liệu học tập</h2>
            {!topic.materials.length && (
              <p className="muted">Chưa có tài liệu gắn với chủ đề này.</p>
            )}
            {topic.materials.map((material) => (
              <div className="workspace-row" key={material.order_index}>
                <div>
                  <strong>{material.title}</strong>
                  <p className="muted">
                    {material.document_code} · Bản {material.version} · Trang {material.page_start}–
                    {material.page_end}
                  </p>
                </div>
                <div className="workspace-actions">
                  <button
                    className="button button-secondary"
                    onClick={() => readPdf(material.document_version_id, material.page_start)}
                  >
                    {teacher ? 'Xem trước PDF' : 'Đọc tài liệu'}
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
              </div>
            ))}
            {teacher && (
              <>
                <div className="workspace-actions" style={{ marginTop: 15 }}>
                  <button
                    className="button button-secondary"
                    onClick={() => {
                      setUploadTarget({ topicId: topic.id, start: 1, end: '' })
                      go('upload')
                    }}
                  >
                    Upload tài liệu mới
                  </button>
                </div>
                <details>
                  <summary>Gắn tài liệu đã công bố</summary>
                  <form className="learning-form" onSubmit={mapMaterial}>
                    <fieldset disabled={busy}>
                      <label>
                        Phiên bản PDF đã công bố
                        <select
                          required
                          value={mapping.version}
                          onChange={(e) => setMapping((v) => ({ ...v, version: e.target.value }))}
                        >
                          <option value="">Chọn PDF</option>
                          {sourceVersions.map((value) => (
                            <option key={value.id} value={value.id}>
                              {value.document.code} · Bản {value.version}
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
                            max={2000}
                            value={mapping.start}
                            onChange={(e) =>
                              setMapping((v) => ({ ...v, start: Number(e.target.value) }))
                            }
                          />
                        </label>
                        <label>
                          Đến trang
                          <input
                            required
                            type="number"
                            min={mapping.start}
                            max={2000}
                            value={mapping.end}
                            onChange={(e) =>
                              setMapping((v) => ({ ...v, end: Number(e.target.value) }))
                            }
                          />
                        </label>
                      </div>
                      <button className="button button-secondary">Gắn khoảng trang</button>
                    </fieldset>
                  </form>
                </details>
              </>
            )}
            <h2>Quiz chủ đề</h2>
            <p>
              {topic.quiz
                ? `${topic.quiz.question_count} câu hỏi · Ngưỡng đạt ${topic.quiz.pass_percent}%`
                : 'Giảng viên chưa công bố quiz.'}
            </p>
            <div className="workspace-actions">
              {teacher ? (
                <button className="button button-primary" onClick={() => go('quiz-editor')}>
                  Biên soạn quiz
                </button>
              ) : (
                topic.quiz && (
                  <button className="button button-primary" onClick={() => go('quiz')}>
                    Làm quiz
                  </button>
                )
              )}
            </div>
          </div>
        </>
      )}
      {['topic', 'quiz', 'quiz-editor'].includes(route.view) && !topic && (
        <p role="status">
          {topicsLoading
            ? 'Đang tải chủ đề…'
            : 'Không tìm thấy chủ đề. Quay lại nội dung học phần để chọn lại.'}
        </p>
      )}
      {teacher && topic && editorVisited === topic.id && (
        <div hidden={route.view !== 'quiz-editor'}>
          {heading(
            'Biên soạn quiz: ' + topic.title,
            <button className="button button-secondary" onClick={() => go('topic')}>
              Về chủ đề
            </button>,
          )}
          <TeacherQuizEditor
            key={topic.id}
            topic={topic}
            documents={documents}
            session={session}
            onChanged={changed}
            onFailure={fail}
            onActionStart={() => setError('')}
            onDirtyChange={setQuizDirty}
            onBusyChange={setQuizBusy}
          />
        </div>
      )}
      {!teacher && topic && run && quizVisited === topic.id && (
        <div className="workspace-quiz-screen" hidden={route.view !== 'quiz'}>
          {heading(
            'Quiz: ' + topic.title,
            <button className="button button-secondary" onClick={() => go('topic')}>
              Về chủ đề
            </button>,
          )}
          <QuizPlayer
            key={topic.id}
            run={run}
            topicId={topic.id}
            quiz={topic.quiz}
            csrfToken={csrfToken}
            attempt={attempt}
            onAttempt={updateAttempt}
            onFailure={fail}
            onCompleted={changed}
            onDirtyChange={setQuizDirty}
            onBusyChange={setQuizBusy}
          />
        </div>
      )}
      {route.view === 'pdf' && selectedVersion && (
        <>
          {heading(
            selectedVersion.document.title,
            <div className="workspace-actions">
              <button className="button button-secondary" onClick={() => go(viewerReturn.current)}>
                Về {viewerReturn.current === 'document' ? 'tài liệu' : 'chủ đề'}
              </button>
            </div>,
          )}
          <div className="workspace-reader">
            <aside>
              <h3>{topic?.title || 'Tài liệu học phần'}</h3>
              {topic?.quiz && !teacher && (
                <button className="button button-primary" onClick={() => go('quiz')}>
                  Chuyển sang quiz
                </button>
              )}
            </aside>
            <Suspense fallback={<p role="status">Đang mở trình xem PDF…</p>}>
              <PdfViewer
                key={`${teacher ? 'teacher' : run?.id}:${selectedVersion.id}`}
                runId={run?.id}
                versionId={selectedVersion.id}
                title={`${selectedVersion.document.code} · ${selectedVersion.document.title} · Bản ${selectedVersion.version}`}
                teacherPreview={teacher}
                initialPage={route.page || 1}
                onEvent={canWrite ? record : undefined}
                onPosition={(page) => {
                  if (page !== (route.page || 1))
                    replacePosition(
                      routeHash({ ...route, page, actor: teacher ? 'teacher' : 'student' }),
                    )
                }}
                onClose={() => go(viewerReturn.current)}
              />
            </Suspense>
          </div>
        </>
      )}
      {route.view === 'pdf' && !loading && !selectedVersion && (
        <p className="notice notice-error">
          Tài liệu chưa công bố, đã bị thu hồi hoặc không thuộc học phần này.
        </p>
      )}
      {!teacher && run && guidanceVisited && (
        <div hidden={route.view !== 'progress'}>
          <GuidancePanel
            key={`guidance:${run.id}`}
            run={run}
            csrfToken={csrfToken}
            refresh={reload}
            activityRefresh={activityReload}
            topics={topics}
            onExpired={onExpired}
            onTopic={(id) => go('quiz', { topicId: id })}
            onRead={(material) => readPdf(material.document_version_id, material.page_start)}
          />
        </div>
      )}
      {!teacher && run && chatVisited && (
        <aside
          className="workspace-chat-container"
          hidden={!chatOpen}
          aria-label="Trợ giảng học phần"
        >
          <div className="section-heading">
            <span>Trợ giảng · {run.course_title}</span>
            <button className="text-button" onClick={() => setChatOpen(false)}>
              Đóng trợ giảng
            </button>
          </div>
          <ChatPanel
            key={`chat:${run.id}`}
            run={run}
            csrfToken={csrfToken}
            onExpired={onExpired}
            onRead={(citation) => readPdf(citation.document_version_id, citation.pdf_page)}
          />
        </aside>
      )}
      {teacher && route.view === 'upload' && (
        <>
          {heading(
            'Thêm tài liệu',
            <button className="button button-secondary" onClick={() => go('materials')}>
              Về danh sách
            </button>,
          )}
          <form className="learning-form workspace-form" onSubmit={uploadPdf}>
            <fieldset disabled={busy}>
              <label>
                Mã tài liệu (ví dụ CH01)
                <input
                  required
                  pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                  maxLength={64}
                  value={upload.code}
                  onChange={(e) => setUpload((v) => ({ ...v, code: e.target.value }))}
                />
              </label>
              <label>
                Tên tài liệu
                <input
                  required
                  maxLength={200}
                  value={upload.title}
                  onChange={(e) => setUpload((v) => ({ ...v, title: e.target.value }))}
                />
              </label>
              <label>
                Tệp PDF · tối đa 100 MiB, 2.000 trang
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
              {file && <p className="muted">Đã chọn: {file.name}</p>}
              <label>
                Gắn vào chủ đề sau khi công bố
                <select
                  value={uploadTarget.topicId}
                  onChange={(e) => setUploadTarget((v) => ({ ...v, topicId: e.target.value }))}
                >
                  <option value="">Để gắn sau</option>
                  {topics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.code} · {t.title}
                    </option>
                  ))}
                </select>
              </label>
              {uploadTarget.topicId && (
                <div className="learning-form-grid">
                  <label>
                    Từ trang
                    <input
                      type="number"
                      min={1}
                      max={2000}
                      value={uploadTarget.start}
                      onChange={(e) =>
                        setUploadTarget((v) => ({ ...v, start: Number(e.target.value) }))
                      }
                    />
                  </label>
                  <label>
                    Đến trang · để trống dùng hết PDF
                    <input
                      type="number"
                      min={uploadTarget.start}
                      max={2000}
                      value={uploadTarget.end}
                      onChange={(e) => setUploadTarget((v) => ({ ...v, end: e.target.value }))}
                    />
                  </label>
                </div>
              )}
              <button className="button button-primary" disabled={!file}>
                {busy ? 'Đang upload…' : 'Lưu nháp và xem trước'}
              </button>
            </fieldset>
          </form>
        </>
      )}
      {teacher &&
        route.view === 'materials' &&
        heading(
          'Tài liệu',
          <button
            className="button button-primary"
            onClick={() => {
              setUploadTarget({ topicId: '', start: 1, end: '' })
              go('upload')
            }}
          >
            Thêm tài liệu
          </button>,
        )}
      {teacher &&
        (route.view === 'materials' || route.view === 'document') &&
        !loading &&
        !documents.length && (
          <p className="workspace-empty">
            Chưa có PDF. Thêm tài liệu để chuẩn bị nội dung học phần.
          </p>
        )}
      {teacher &&
        versions.map((version) => {
          const detail = route.view === 'document' && route.versionId === version.id
          const latest = version.document.versions[0]?.id === version.id
          return (
            <article
              key={version.id}
              hidden={!detail && !(route.view === 'materials' && latest)}
              className={detail ? 'workspace-document-detail' : 'document-card'}
            >
              <div className="section-heading">
                <div>
                  <h3>{version.document.title}</h3>
                  <p className="muted">
                    {version.document.code} · Bản {version.version} · {version.page_count} trang ·{' '}
                    {version.document.status === 'published'
                      ? 'Đã công bố'
                      : version.document.status === 'draft'
                        ? 'Bản nháp'
                        : 'Đã lưu trữ'}
                  </p>
                </div>
                {detail && (
                  <button className="button button-secondary" onClick={() => go('materials')}>
                    Về danh sách
                  </button>
                )}
              </div>
              {detail && (
                <>
                  <label>
                    Phiên bản PDF
                    <select
                      className="document-version-picker"
                      value={version.id}
                      onChange={(e) => go('document', { versionId: e.target.value })}
                    >
                      {version.document.versions.map((v) => (
                        <option key={v.id} value={v.id}>
                          Bản {v.version} · {v.page_count} trang
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="workspace-actions">
                    <button
                      className="button button-secondary"
                      onClick={() => readPdf(version.id, 1)}
                    >
                      Xem PDF
                    </button>
                    <button
                      className="button button-secondary"
                      disabled={busy}
                      onClick={() => void setDocumentStatus(version.document, version.id)}
                    >
                      {' '}
                      {version.document.status === 'published' ? 'Lưu trữ PDF' : 'Chỉ công bố PDF'}
                    </button>
                  </div>
                  <details>
                    <summary>Thêm phiên bản PDF</summary>
                    <label>
                      Tệp PDF mới
                      <input
                        type="file"
                        accept="application/pdf,.pdf"
                        disabled={busy}
                        onChange={(e) => {
                          void addVersion(version.document, e.target.files?.[0])
                          e.target.value = ''
                        }}
                      />
                    </label>
                  </details>
                  {pendingLink?.versionId === version.id && (
                    <p className="notice">
                      Sau khi công bố và dùng cho trợ giảng, tài liệu sẽ được gắn vào chủ đề đã
                      chọn, trang {pendingLink.start}–{pendingLink.end}.
                    </p>
                  )}
                </>
              )}
              <DocumentActions
                document={version.document}
                csrfToken={csrfToken}
                onFailure={fail}
                onSaved={(updated, replaced) => {
                  setDocuments((all) =>
                    all.map((item) => (item.id === updated.id ? updated : item)),
                  )
                  setError('')
                  setMessage(
                    replaced
                      ? 'Đã thay PDF và xóa file cũ. Kiểm tra, gắn vào chủ đề và công bố lại tài liệu.'
                      : 'Đã cập nhật thông tin tài liệu.',
                  )
                  if (replaced) {
                    setPendingLink((old) =>
                      version.document.versions.some((v) => v.id === old?.versionId) ? null : old,
                    )
                    go('document', { versionId: updated.versions[0]?.id })
                  }
                  changed()
                }}
                onDeleted={() => {
                  setDocuments((all) => all.filter((item) => item.id !== version.document.id))
                  setPendingLink((old) =>
                    version.document.versions.some((v) => v.id === old?.versionId) ? null : old,
                  )
                  setError('')
                  setMessage('Đã xóa vĩnh viễn tài liệu và các file PDF.')
                  changed()
                  go('materials', { versionId: undefined })
                }}
              />
              <RagDocumentPanel
                versionId={version.id}
                documentStatus={version.document.status}
                csrfToken={csrfToken}
                onExpired={onExpired}
                compact={!detail}
                onReview={() => go('document', { versionId: version.id })}
                onPublished={() => void afterPublished(version.id)}
              />
            </article>
          )
        })}
      {!teacher && run && route.view === 'results' && (
        <section className="learning-history">
          {heading('Kết quả và lịch sử bài làm')}
          {!history.length ? (
            <p className="muted">Chưa có bài làm.</p>
          ) : (
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
      {teacher && route.view === 'report' && (
        <section className="learning-report">
          {heading(run ? 'Kết quả lớp · ' + run.code : 'Kết quả lớp học')}
          {!run ? (
            <p className="muted">Chọn lớp để xem kết quả.</p>
          ) : !report.length && !loading ? (
            <p className="muted">Chưa có sinh viên hoặc kết quả trong lớp.</p>
          ) : (
            report.map((value) => (
              <article className="student-report" key={value.enrollment_id}>
                <strong>{value.display_name}</strong>
                <p>
                  {value.student_email} ·{' '}
                  {value.enrollment_status === 'active' ? 'Đang đăng ký' : 'Ngừng đăng ký'}
                </p>
                <p>
                  {value.page_views} lượt xem trang · {value.attempt_count} bài làm
                </p>
                <p>
                  Lộ trình {value.learning_path.revision} · {value.learning_path.steps.length} bước
                  học/ôn
                </p>
                <div className="path-states">
                  {value.learning_path.topic_states.map((item) => (
                    <span className={`path-state path-${item.state}`} key={item.topic_id}>
                      {item.topic_code}: {stateLabels[item.state]}
                      {item.score_percent !== null && ` ${item.score_percent.toFixed(1)}%`}
                    </span>
                  ))}
                </div>
                {value.latest_results.map((result) => (
                  <p key={result.id}>
                    {topics.find((t) => t.id === result.topic_id)?.code} ·{' '}
                    {result.score_percent?.toFixed(1)}% ·{' '}
                    {result.passed_for_attempt_version ? 'Đạt bản đã làm' : 'Chưa đạt'}
                    {!result.counts_for_current_mastery && ' · Có quiz mới'}
                  </p>
                ))}
              </article>
            ))
          )}
        </section>
      )}
    </section>
  )
}

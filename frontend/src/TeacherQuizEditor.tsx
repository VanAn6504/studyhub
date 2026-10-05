import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { listAll, request } from './api'
import type { QuizMetadata, Session, Topic } from './api'
import type { LearningDocument, QuestionContent, QuestionVersion } from './learningTypes'

const blank = () => ({
  code: '',
  stem: '',
  A: '',
  B: '',
  C: '',
  D: '',
  correct: 'A' as QuestionContent['correct_option'],
  explanation: '',
  source: '',
  page: 1,
})

export default function TeacherQuizEditor({
  topic,
  documents,
  session,
  onChanged,
  onFailure,
}: {
  topic: Topic
  documents: LearningDocument[]
  session: Session
  onChanged: () => void
  onFailure: (error: unknown) => void
}) {
  const [questions, setQuestions] = useState<QuestionVersion[]>([])
  const [quizzes, setQuizzes] = useState<QuizMetadata[]>([])
  const [chosen, setChosen] = useState<string[]>([])
  const [draftId, setDraftId] = useState('')
  const [preview, setPreview] = useState<(QuizMetadata & { items: QuestionVersion[] }) | null>(null)
  const [reviewed, setReviewed] = useState(false)
  const [form, setForm] = useState(blank)
  const [editingId, setEditingId] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [reload, setReload] = useState(0)
  const csrfToken = session.csrf_token
  useEffect(() => {
    let stopped = false
    setLoading(true)
    Promise.all([
      listAll<QuestionVersion>(`/topics/${topic.id}/question-versions`),
      listAll<QuizMetadata>(`/topics/${topic.id}/quiz-versions`),
    ])
      .then(([q, v]) => {
        if (!stopped) {
          setQuestions(q)
          setQuizzes(v)
          const newest = q.filter(
            (item, index) =>
              q.findIndex((value) => value.question_id === item.question_id) === index,
          )
          setChosen((previous) => previous.filter((id) => newest.some((item) => item.id === id)))
        }
      })
      .catch(onFailure)
      .finally(() => {
        if (!stopped) setLoading(false)
      })
    return () => {
      stopped = true
    }
  }, [topic.id, reload])
  useEffect(() => {
    let stopped = false
    setReviewed(false)
    setPreview(null)
    if (draftId)
      request<QuizMetadata & { items: QuestionVersion[] }>(`/quiz-versions/${draftId}`)
        .then((value) => {
          if (!stopped) setPreview(value)
        })
        .catch(onFailure)
    return () => {
      stopped = true
    }
  }, [draftId, reload])
  const versions = documents.flatMap((document) =>
    document.versions.map((version) => ({ ...version, document })),
  )
  const latest = questions.filter(
    (question, index, all) =>
      all.findIndex((value) => value.question_id === question.question_id) === index,
  )
  async function saveQuestion(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    const body: QuestionContent = {
      stem: form.stem,
      options: { A: form.A, B: form.B, C: form.C, D: form.D },
      correct_option: form.correct,
      explanation: form.explanation,
      sources: [{ document_version_id: form.source, pdf_page: form.page }],
    }
    try {
      await request(
        editingId ? `/questions/${editingId}/versions` : `/topics/${topic.id}/questions`,
        { method: 'POST', csrfToken, body: editingId ? body : { ...body, code: form.code } },
      )
      setForm(blank())
      setEditingId('')
      setReload((value) => value + 1)
      setMessage('Đã lưu bản câu hỏi. Quiz đã công bố vẫn giữ nội dung cũ.')
    } catch (failure) {
      onFailure(failure)
    } finally {
      setBusy(false)
    }
  }
  function edit(question: QuestionVersion) {
    setEditingId(question.question_id)
    setForm({
      code: question.code,
      stem: question.stem,
      ...question.options,
      correct: question.correct_option,
      explanation: question.explanation,
      source: question.sources[0].document_version_id,
      page: question.sources[0].pdf_page,
    })
  }
  async function importDraft(file?: File) {
    if (!file) return
    setBusy(true)
    setMessage('')
    let added = 0
    try {
      if (file.size > 1024 * 1024) throw new Error('Tệp câu hỏi tối đa 1 MiB.')
      const data = JSON.parse(await file.text())
      if (!Array.isArray(data.questions) || data.questions.length > 100)
        throw new Error('Tệp cần có danh sách questions, tối đa 100 câu.')
      const items = data.questions.filter(
        (item: { topic_id: string }) => item.topic_id === topic.code,
      )
      if (!items.length) throw new Error(`Không có câu hỏi cho ${topic.code} trong tệp này.`)
      // Validate all source references before importing this topic's drafts.
      const prepared = items
        .filter((item: { id: string }) => !questions.some((value) => value.code === item.id))
        .map(
          (item: {
            id: string
            stem: string
            options: QuestionContent['options']
            correct_option: QuestionContent['correct_option']
            explanation: string
            sources: { document_id: string; pdf_page: number }[]
          }) => ({
            code: item.id,
            stem: item.stem,
            options: item.options,
            correct_option: item.correct_option,
            explanation: item.explanation,
            sources: item.sources.map((source) => {
              const document = documents.find((value) => value.code === source.document_id)
              const version = document?.versions[0]
              if (!version || source.pdf_page < 1 || source.pdf_page > version.page_count)
                throw new Error(
                  `Hãy upload PDF ${source.document_id} và kiểm tra trang nguồn trước.`,
                )
              return { document_version_id: version.id, pdf_page: source.pdf_page }
            }),
          }),
        )
      for (const body of prepared) {
        await request(`/topics/${topic.id}/questions`, { method: 'POST', csrfToken, body })
        added++
      }
      setMessage(
        `Đã nhập ${added} câu nháp cho ${topic.code}; bỏ qua mã đã có. Hãy rà soát câu hỏi trước khi tạo và công bố quiz.`,
      )
    } catch (failure) {
      if (added) setMessage(`Đã nhập ${added} câu trước khi gặp lỗi; có thể nhập lại để tiếp tục.`)
      onFailure(failure)
    } finally {
      setBusy(false)
      setReload((value) => value + 1)
    }
  }
  async function createQuiz() {
    setBusy(true)
    setMessage('')
    try {
      const value = await request<QuizMetadata>(`/topics/${topic.id}/quiz-versions`, {
        method: 'POST',
        csrfToken,
        body: { question_version_ids: chosen },
      })
      setDraftId(value.id)
      setReload((value) => value + 1)
      setMessage('Đã tạo quiz nháp. Kiểm tra nội dung bên dưới trước khi công bố.')
    } catch (failure) {
      onFailure(failure)
    } finally {
      setBusy(false)
    }
  }
  async function publish() {
    if (!reviewed || !preview) return
    setBusy(true)
    try {
      await request(`/quiz-versions/${preview.id}/publish`, { method: 'POST', csrfToken })
      setReload((value) => value + 1)
      onChanged()
      setMessage('Đã công bố quiz cho sinh viên.')
    } catch (failure) {
      onFailure(failure)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="teacher-quiz-editor">
      <h3>Biên soạn quiz · {topic.code}</h3>
      {loading && <p role="status">Đang tải ngân hàng câu hỏi…</p>}
      <details open={editingId ? true : undefined}>
        <summary>{editingId ? 'Tạo phiên bản câu hỏi mới' : 'Thêm câu hỏi'}</summary>
        <form className="learning-form" onSubmit={saveQuestion}>
          <fieldset disabled={busy}>
            <label>
              Mã câu hỏi
              <input
                required
                value={form.code}
                disabled={!!editingId}
                maxLength={64}
                pattern="[A-Za-z0-9][A-Za-z0-9_-]*"
                onChange={(event) => setForm({ ...form, code: event.target.value })}
              />
            </label>
            <label>
              Câu hỏi
              <textarea
                aria-label="Câu hỏi"
                required
                maxLength={4000}
                value={form.stem}
                onChange={(event) => setForm({ ...form, stem: event.target.value })}
              />
            </label>
            <div className="learning-form-grid">
              {(['A', 'B', 'C', 'D'] as const).map((option) => (
                <label key={option}>
                  Lựa chọn {option}
                  <input
                    required
                    maxLength={200}
                    value={form[option]}
                    onChange={(event) => setForm({ ...form, [option]: event.target.value })}
                  />
                </label>
              ))}
            </div>
            <label>
              Đáp án đúng
              <select
                aria-label="Đáp án đúng"
                value={form.correct}
                onChange={(event) =>
                  setForm({
                    ...form,
                    correct: event.target.value as QuestionContent['correct_option'],
                  })
                }
              >
                {['A', 'B', 'C', 'D'].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Giải thích
              <textarea
                aria-label="Giải thích"
                required
                maxLength={4000}
                value={form.explanation}
                onChange={(event) => setForm({ ...form, explanation: event.target.value })}
              />
            </label>
            <div className="learning-form-grid">
              <label>
                PDF nguồn
                <select
                  aria-label="PDF nguồn"
                  required
                  value={form.source}
                  onChange={(event) => setForm({ ...form, source: event.target.value })}
                >
                  <option value="">Chọn phiên bản PDF</option>
                  {versions.map((version) => (
                    <option key={version.id} value={version.id}>
                      {version.document.code} · bản {version.version}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Trang nguồn
                <input
                  required
                  type="number"
                  min={1}
                  max={500}
                  value={form.page}
                  onChange={(event) => setForm({ ...form, page: Number(event.target.value) })}
                />
              </label>
            </div>
            <div className="form-actions">
              <button
                className="button button-secondary"
                type="button"
                onClick={() => {
                  setForm(blank())
                  setEditingId('')
                }}
              >
                Hủy biên soạn
              </button>
              <button className="button button-primary">
                {editingId ? 'Lưu phiên bản mới' : 'Lưu câu hỏi nháp'}
              </button>
            </div>
          </fieldset>
        </form>
      </details>
      <label className="draft-import">
        Nhập câu hỏi từ quiz_draft.json cho chủ đề đang chọn
        <input
          type="file"
          accept=".json,application/json"
          disabled={busy}
          onChange={(event) => {
            void importDraft(event.target.files?.[0])
            event.target.value = ''
          }}
        />
      </label>
      <p className="muted">
        Tối thiểu 3 câu/quiz; mỗi câu 1 điểm, ngưỡng đạt 70%. Chọn bản câu hỏi mới nhất đã rà soát.
      </p>
      {latest.map((question) => (
        <div className="question-select" key={question.id}>
          <label>
            <input
              type="checkbox"
              disabled={busy}
              checked={chosen.includes(question.id)}
              onChange={(event) =>
                setChosen((values) =>
                  event.target.checked
                    ? [...values, question.id]
                    : values.filter((id) => id !== question.id),
                )
              }
            />
            <span>
              <strong>
                {question.code} · bản {question.version}
              </strong>
              <br />
              {question.stem}
            </span>
          </label>
          <button className="text-button" disabled={busy} onClick={() => edit(question)}>
            Chỉnh bản mới
          </button>
          <details>
            <summary>Đáp án và nguồn</summary>
            <p>
              Đáp án {question.correct_option}: {question.explanation}
            </p>
            {question.sources.map((source) => (
              <p key={`${source.document_version_id}:${source.pdf_page}`}>
                Trang {source.pdf_page} ·{' '}
                {versions.find((v) => v.id === source.document_version_id)?.document.code || 'PDF'}
              </p>
            ))}
          </details>
        </div>
      ))}
      {!loading && !latest.length && (
        <p>Chưa có câu hỏi. Upload PDF nguồn rồi thêm hoặc nhập câu hỏi nháp.</p>
      )}
      <button
        className="button button-secondary"
        disabled={busy || chosen.length < 3}
        onClick={createQuiz}
      >
        Tạo quiz nháp ({chosen.length} câu)
      </button>
      <label className="quiz-version-select">
        Phiên bản quiz
        <select
          aria-label="Phiên bản quiz"
          value={draftId}
          disabled={busy}
          onChange={(event) => setDraftId(event.target.value)}
        >
          <option value="">Chọn để rà soát</option>
          {quizzes.map((value) => (
            <option key={value.id} value={value.id}>
              Bản {value.version} ·{' '}
              {value.status === 'draft'
                ? 'Nháp'
                : value.status === 'published'
                  ? 'Đã công bố'
                  : 'Đã nghỉ'}
            </option>
          ))}
        </select>
      </label>
      {preview && (
        <div className="quiz-review">
          <h4>Rà soát quiz bản {preview.version}</h4>
          {preview.items.map((question, index) => (
            <details key={question.id}>
              <summary>
                {index + 1}. {question.stem}
              </summary>
              {Object.entries(question.options).map(([key, value]) => (
                <p key={key}>
                  {key}. {value}
                </p>
              ))}
              <p>
                <strong>Đáp án {question.correct_option}</strong> · {question.explanation}
              </p>
              {question.sources.map((source) => (
                <p key={`${source.document_version_id}:${source.pdf_page}`}>
                  Nguồn:{' '}
                  {versions.find((value) => value.id === source.document_version_id)?.document
                    .code || 'PDF'}
                  {' · bản '}
                  {versions.find((value) => value.id === source.document_version_id)?.version}
                  {' · trang '}
                  {source.pdf_page}
                </p>
              ))}
            </details>
          ))}
          {preview.status === 'draft' && (
            <>
              <label className="review-confirm">
                <input
                  type="checkbox"
                  checked={reviewed}
                  disabled={busy}
                  onChange={(event) => setReviewed(event.target.checked)}
                />
                Tôi đã kiểm tra câu hỏi, đáp án và trang nguồn.
              </label>
              <button
                className="button button-primary"
                disabled={busy || !reviewed}
                onClick={publish}
              >
                Công bố quiz cho sinh viên
              </button>
            </>
          )}
        </div>
      )}
      {message && (
        <p className="notice notice-success" role="status">
          {message}
        </p>
      )}
    </section>
  )
}

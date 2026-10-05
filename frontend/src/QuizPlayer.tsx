import { useRef, useState } from 'react'
import { request } from './api'
import type { CourseRun, QuizMetadata } from './api'
import type { Attempt } from './learningTypes'

export default function QuizPlayer({
  run,
  topicId,
  quiz,
  csrfToken,
  attempt,
  onAttempt,
  onFailure,
  onCompleted,
}: {
  run: CourseRun
  topicId: string
  quiz: QuizMetadata | null
  csrfToken: string
  attempt: Attempt | null
  onAttempt: (attempt: Attempt | null) => void
  onFailure: (failure: unknown) => void
  onCompleted: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [answers, setAnswers] = useState<Record<string, string | null>>({})
  const [loadedAttempt, setLoadedAttempt] = useState<Attempt | null>(null)
  const key = useRef('')
  // An explicit reload/resume replaces the local answer buffer.
  if (attempt !== loadedAttempt) {
    setLoadedAttempt(attempt)
    setAnswers(
      Object.fromEntries(
        (attempt?.items || []).map((item) => [item.quiz_version_item_id, item.selected_option]),
      ),
    )
  }
  const canWrite = run.status === 'active' && run.data_origin === 'real'
  async function begin() {
    if (!quiz) return
    setBusy(true)
    setMessage('')
    if (!key.current) key.current = crypto.randomUUID()
    try {
      const value = await request<Attempt>(`/course-runs/${run.id}/topics/${topicId}/attempts`, {
        method: 'POST',
        csrfToken,
        body: { published_quiz_version_id: quiz.published_version_id, request_key: key.current },
      })
      onAttempt(value)
      key.current = ''
    } catch (failure) {
      onFailure(failure)
    } finally {
      setBusy(false)
    }
  }
  async function save(submit: boolean) {
    if (!attempt) return
    setBusy(true)
    setMessage('')
    try {
      const saved = await request<Attempt>(`/attempts/${attempt.id}/answers`, {
        method: 'PUT',
        csrfToken,
        body: {
          expected_revision: attempt.answer_revision,
          answers: Object.entries(answers).map(([id, option]) => ({
            quiz_version_item_id: id,
            selected_option: option,
          })),
        },
      })
      onAttempt(saved)
      if (submit) {
        const completed = await request<Attempt>(`/attempts/${attempt.id}/submit`, {
          method: 'POST',
          csrfToken,
          body: { expected_revision: saved.answer_revision },
        })
        onAttempt(completed)
        onCompleted()
      } else setMessage('Đã lưu bài làm. Bạn có thể quay lại làm tiếp.')
    } catch (failure) {
      onFailure(failure)
    } finally {
      setBusy(false)
    }
  }
  async function reload() {
    if (!attempt) return
    setBusy(true)
    try {
      onAttempt(await request<Attempt>(`/attempts/${attempt.id}`))
      setMessage('Đã tải bài làm được lưu ở server.')
    } catch (failure) {
      onFailure(failure)
    } finally {
      setBusy(false)
    }
  }
  if (!attempt)
    return (
      <div className="quiz-start">
        {quiz ? (
          <>
            <p>
              {quiz.question_count} câu hỏi · Ngưỡng đạt {quiz.pass_percent}% · Có thể làm lại
            </p>
            <button className="button button-primary" disabled={busy || !canWrite} onClick={begin}>
              {busy ? 'Đang mở…' : 'Bắt đầu / tiếp tục quiz'}
            </button>
          </>
        ) : (
          <p className="muted">Giảng viên chưa công bố quiz cho chủ đề này.</p>
        )}
        {!canWrite && <p className="muted">Lượt học này chỉ cho phép xem nội dung và lịch sử.</p>}
      </div>
    )
  const completed = attempt.status === 'completed'
  return (
    <div className="quiz-player">
      <div className="learning-heading">
        <h3>{completed ? 'Kết quả bài làm' : 'Bài làm của bạn'}</h3>
        <button
          className="button button-secondary"
          disabled={busy}
          onClick={() => {
            onAttempt(null)
            setMessage('')
          }}
        >
          Đóng bài làm
        </button>
      </div>
      {completed && (
        <div className="score-card">
          <strong>{attempt.score_percent?.toFixed(1)}%</strong>
          <span>
            {attempt.correct_count}/{attempt.total_questions} câu đúng ·{' '}
            {attempt.passed_for_attempt_version ? 'Đạt' : 'Chưa đạt'}
          </span>
          {!attempt.counts_for_current_mastery && (
            <p>Quiz đã có phiên bản mới. Kết quả này được giữ trong lịch sử.</p>
          )}
        </div>
      )}
      {attempt.items.map((item, index) => (
        <fieldset
          className="quiz-question"
          key={item.quiz_version_item_id}
          disabled={busy || completed || !canWrite}
        >
          <legend>
            Câu {index + 1}. {item.stem}
          </legend>
          {Object.entries(item.options).map(([option, label]) => (
            <label
              className={`quiz-option${completed && option === item.correct_option ? ' correct-option' : ''}`}
              key={option}
            >
              <input
                type="radio"
                name={item.quiz_version_item_id}
                checked={answers[item.quiz_version_item_id] === option}
                onChange={() =>
                  setAnswers((current) => ({ ...current, [item.quiz_version_item_id]: option }))
                }
              />{' '}
              <strong>{option}.</strong> {label}
            </label>
          ))}
          {!completed && (
            <button
              type="button"
              className="text-button"
              onClick={() =>
                setAnswers((current) => ({ ...current, [item.quiz_version_item_id]: null }))
              }
            >
              Bỏ lựa chọn
            </button>
          )}
          {completed && (
            <div className="answer-explanation">
              <strong>{item.is_correct ? 'Đúng' : `Đáp án: ${item.correct_option}`}</strong>
              <p>{item.explanation}</p>
              {item.sources?.map((source) => (
                <p className="muted" key={`${source.document_version_id}:${source.pdf_page}`}>
                  Nguồn PDF · trang {source.pdf_page}
                </p>
              ))}
            </div>
          )}
        </fieldset>
      ))}
      {message && (
        <p className="notice notice-success" role="status">
          {message}
        </p>
      )}
      {!completed && (
        <div className="form-actions">
          <button className="button button-secondary" disabled={busy} onClick={reload}>
            Tải bài đã lưu
          </button>
          <button
            className="button button-secondary"
            disabled={busy || !canWrite}
            onClick={() => save(false)}
          >
            Lưu bài làm
          </button>
          <button
            className="button button-primary"
            disabled={busy || !canWrite}
            onClick={() => save(true)}
          >
            {busy ? 'Đang xử lý…' : 'Nộp và xem kết quả'}
          </button>
        </div>
      )}
    </div>
  )
}

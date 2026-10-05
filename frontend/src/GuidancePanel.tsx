import { useEffect, useState } from 'react'
import { ApiError, errorMessage, request } from './api'
import type { CourseRun, Topic } from './api'
import type { LearningPath, PredictionResult } from './learningTypes'

export const stateLabels: Record<string, string> = {
  weak: 'Cần ôn tập', mastered: 'Đã đạt', not_assessed: 'Chưa đánh giá', not_available: 'Chưa có quiz',
}
const reasons: Record<string, string> = {
  low_quiz_score: 'Điểm quiz chưa đạt ngưỡng.', no_current_assessment: 'Bạn chưa làm quiz hiện tại.',
  content_changed: 'Có quiz mới; cần đánh giá lại.', unassessed_prerequisite: 'Học chủ đề tiên quyết trước.',
}
const featureLabels: Record<string, string> = {
  active_days: 'Số ngày có xem trang', material_interactions: 'Số lượt xem trang',
  days_since_last_activity: 'Số ngày từ hoạt động cuối', assessment_count: 'Số quiz đã đánh giá',
  mean_assessment_score: 'Điểm trung bình lần đầu', has_assessment: 'Có kết quả quiz',
}

export default function GuidancePanel({ run, csrfToken, refresh, topics, onTopic, onRead, onExpired }: {
  run: CourseRun; csrfToken: string; refresh: number; topics: Topic[];
  onTopic: (id: string) => void;
  onRead: (material: { document_version_id: string; title: string; page_start: number }) => void;
  onExpired: () => void;
}) {
  const [path, setPath] = useState<LearningPath | null>(null)
  const [prediction, setPrediction] = useState<PredictionResult | null>(null)
  const [pathError, setPathError] = useState('')
  const [predictionError, setPredictionError] = useState('')
  const [loading, setLoading] = useState(true)
  const [computing, setComputing] = useState(false)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let stopped = false
    setLoading(true)
    setPathError('')
    setPredictionError('')
    const fail = (error: unknown, setter: (value: string) => void) => {
      if (stopped) return
      setter(errorMessage(error))
      if (error instanceof ApiError && error.status === 401) onExpired()
    }
    Promise.allSettled([
      request<LearningPath>(`/course-runs/${run.id}/learning-path`)
        .then(value => { if (!stopped) setPath(value) }).catch(error => fail(error, setPathError)),
      request<PredictionResult>(`/course-runs/${run.id}/prediction`)
        .then(value => { if (!stopped) setPrediction(value) }).catch(error => fail(error, setPredictionError)),
    ]).finally(() => { if (!stopped) setLoading(false) })
    return () => { stopped = true }
  }, [run.id, refresh, reload, topics])
  async function compute() {
    setComputing(true)
    setPredictionError('')
    try {
      setPrediction(await request<PredictionResult>(`/course-runs/${run.id}/predictions`, {
        method: 'POST', csrfToken, body: {},
      }))
    } catch (error) {
      setPredictionError(errorMessage(error))
      if (error instanceof ApiError && error.code === 'MODEL_UNAVAILABLE')
        setPrediction(current => current ? { ...current, status: 'model_unavailable', risk_score: null } : null)
      if (error instanceof ApiError && error.status === 401) onExpired()
    } finally { setComputing(false) }
  }
  const warnings = path?.warnings.map(warning => topics.find(topic => topic.id === warning.topic_id)?.code).join(', ')
  return <section className="guidance-panel" aria-labelledby="guidance-title">
    <div className="section-heading">
      <div><span className="eyebrow">LỘ TRÌNH CỦA BẠN</span><h2 id="guidance-title">Bước học tiếp theo</h2></div>
      <button className="button button-secondary" disabled={loading} onClick={() => setReload(value => value + 1)}>Cập nhật lộ trình</button>
    </div>
    {run.data_origin === 'synthetic' && <p className="notice">Dữ liệu mô phỏng · chỉ xem và thử dự báo.</p>}
    <p className="muted">Ưu tiên chủ đề cần ôn và kiến thức tiên quyết. Chủ đề chưa làm quiz được ghi là chưa đánh giá.</p>
    {loading && <p role="status">Đang cập nhật lộ trình…</p>}
    {pathError && <p role="alert" className="notice notice-error">{pathError}</p>}
    {!loading && !pathError && path && <>
      <p className="muted">Phiên bản lộ trình {path.revision} · {new Date(path.generated_at).toLocaleString('vi-VN')}</p>
      {warnings && <p className="notice">Chủ đề tiên quyết {warnings} chưa có quiz; bạn vẫn có thể học và làm bài tiếp.</p>}
      <div className="path-states">{path.topic_states.map(item => <span key={item.topic_id} className={`path-state path-${item.state}`}>
        {item.topic_code} · {stateLabels[item.state]}{item.score_percent !== null && ` ${item.score_percent.toFixed(1)}%`}
      </span>)}</div>
      {path.steps.length ? <ol className="path-steps">{path.steps.map(step => <li key={step.topic_id}>
        <h3>{step.topic_code} · {step.title}</h3>
        <p>{reasons[step.reason] || step.reason}</p>
        {step.materials.map(material => <button className="text-button" key={`${material.document_version_id}:${material.page_start}`} onClick={() => onRead(material)}>
          Đọc {material.document_code} · trang {material.page_start}–{material.page_end}
        </button>)}
        <button className="button button-secondary" onClick={() => onTopic(step.topic_id)}>Mở quiz {step.topic_code}</button>
      </li>)}</ol> : <p className="notice">{!path.topic_states.length ? 'Học phần chưa có chủ đề.' : path.unavailable_topics.length ? 'Các quiz đã có đều đạt hoặc chưa có quiz để đánh giá thêm; hãy đọc tài liệu và chờ giảng viên công bố.' : 'Bạn đã đạt tất cả quiz hiện tại.'}</p>}
      {!!path.unavailable_topics.length && <p className="muted">Chưa có quiz: {path.unavailable_topics.map(item => item.topic_code).join(', ')}.</p>}
    </>}
    <div className="risk-panel">
      <h3>Điểm rủi ro thử nghiệm</h3>
      <p className="muted">Mô hình học từ OULAD, chưa xác nhận trên sinh viên StudyHub. Điểm chưa hiệu chỉnh xác suất, không quyết định việc đạt từng chủ đề.</p>
      {predictionError && <p className="notice notice-error" role="alert">{predictionError}</p>}
      {prediction?.status === 'not_ready' && <p>Chưa đủ thời gian: cần dữ liệu ngày 0–42. Có thể dự báo từ {new Date(prediction.cutoff_end_at).toLocaleString('vi-VN')}.</p>}
      {prediction?.status === 'not_computed' && <p>Chưa tính dự báo cho lượt học này.</p>}
      {prediction?.status === 'model_unavailable' && <p>Mô hình chưa sẵn sàng. Bạn vẫn có thể đọc tài liệu và làm quiz.</p>}
      {prediction?.status === 'insufficient_data' && <p>Chưa đủ dữ liệu: không có lượt xem trang hợp lệ trong cửa sổ dự báo.</p>}
      {prediction?.status === 'ok' && <>
        <p className="risk-score">{(prediction.risk_score! * 100).toFixed(1)}/100 <span>{prediction.threshold_exceeded ? 'Vượt ngưỡng thử nghiệm' : 'Dưới ngưỡng thử nghiệm'}</span></p>
        <p className="muted">Ngưỡng {(prediction.threshold! * 100).toFixed(1)}/100 · mô hình {prediction.model_code} · {prediction.data_origin === 'synthetic' ? 'Mô phỏng' : 'Dữ liệu thật'}</p>
        <details><summary>Đặc trưng và giải thích điểm</summary>
          <p>SHAP biểu diễn đóng góp vào điểm mô hình; không chứng minh nguyên nhân. Mốc nền: {(prediction.explanation!.base_value * 100).toFixed(1)} điểm.</p>
          {prediction.explanation?.contributions.map(item => <p key={item.feature}>{featureLabels[item.feature]}: {item.value === null ? 'Thiếu dữ liệu' : item.value.toFixed(1)} · đóng góp {item.contribution >= 0 ? '+' : ''}{(item.contribution * 100).toFixed(2)} điểm</p>)}
        </details>
      </>}
      {!loading && prediction?.status !== 'not_ready' && <button className="button button-secondary" disabled={computing} onClick={() => void compute()}>{computing ? 'Đang tính dự báo…' : 'Tính dự báo'}</button>}
    </div>
  </section>
}

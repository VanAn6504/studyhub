import { useEffect, useState } from 'react'
import { ApiError, errorMessage, request } from './api'
import type { CourseRun, Topic } from './api'
import type { LearningActivity, LearningPath, PredictionResult } from './learningTypes'

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

export default function GuidancePanel({ run, csrfToken, refresh, activityRefresh, topics, onTopic, onRead, onLibrary, onSwitchRun, onExpired }: {
  run: CourseRun; csrfToken: string; refresh: number; activityRefresh: number; topics: Topic[];
  onTopic: (id: string) => void;
  onRead: (material: { document_version_id: string; title: string; page_start: number }) => void;
  onLibrary: () => void;
  onSwitchRun: (target: NonNullable<LearningActivity['linked_run']>) => void;
  onExpired: () => void;
}) {
  const [path, setPath] = useState<LearningPath | null>(null)
  const [activity, setActivity] = useState<LearningActivity | null>(null)
  const [activityError, setActivityError] = useState('')
  const [prediction, setPrediction] = useState<PredictionResult | null>(null)
  const [pathError, setPathError] = useState('')
  const [predictionError, setPredictionError] = useState('')
  const [loading, setLoading] = useState(true)
  const [predictionLoading, setPredictionLoading] = useState(true)
  const [computing, setComputing] = useState(false)
  const [reload, setReload] = useState(0)
  useEffect(() => {
    let stopped = false
    setLoading(true)
    setPathError('')
    request<LearningPath>(`/course-runs/${run.id}/learning-path`)
      .then(value => { if (!stopped) setPath(value) })
      .catch(error => {
        if (stopped) return
        setPathError(errorMessage(error))
        if (error instanceof ApiError && error.status === 401) onExpired()
      })
      .finally(() => { if (!stopped) setLoading(false) })
    return () => { stopped = true }
  }, [run.id, refresh, reload, topics])
  useEffect(() => {
    let stopped = false
    setActivityError('')
    request<LearningActivity>(`/course-runs/${run.id}/learning-activity`)
      .then(value => { if (!stopped) setActivity(value) })
      .catch(error => {
        if (stopped) return
        setActivity(null)
        setActivityError(errorMessage(error))
        if (error instanceof ApiError && error.status === 401) onExpired()
      })
    return () => { stopped = true }
  }, [run.id, refresh, reload, activityRefresh])
  useEffect(() => {
    let stopped = false
    setPredictionLoading(true)
    setPredictionError('')
    request<PredictionResult>(`/course-runs/${run.id}/prediction`)
      .then(value => { if (!stopped) setPrediction(value) })
      .catch(error => {
        if (stopped) return
        setPrediction(null)
        setPredictionError(errorMessage(error))
        if (error instanceof ApiError && error.status === 401) onExpired()
      })
      .finally(() => { if (!stopped) setPredictionLoading(false) })
    return () => { stopped = true }
  }, [run.id, refresh, reload, activityRefresh])
  async function compute() {
    setComputing(true)
    setPredictionError('')
    try {
      setPrediction(await request<PredictionResult>(`/course-runs/${run.id}/predictions`, {
        method: 'POST', csrfToken, body: {},
      }))
    } catch (error) {
      if (error instanceof ApiError && error.code === 'MODEL_UNAVAILABLE')
        setPrediction(current => current ? { ...current, status: 'model_unavailable', risk_score: null } : null)
      else setPredictionError(errorMessage(error))
      if (error instanceof ApiError && error.status === 401) onExpired()
    } finally { setComputing(false) }
  }
  const synthetic = run.data_origin === 'synthetic'
  const mastered = path?.topic_states.filter(item => item.state === 'mastered').length ?? 0
  const assessed = mastered + (path?.topic_states.filter(item => item.state === 'weak').length ?? 0)
  const dateTime = (value: string) => new Date(value).toLocaleString('vi-VN', { timeZone: run.timezone })
  const warnings = path?.warnings.map(warning => topics.find(topic => topic.id === warning.topic_id)?.code).join(', ')
  return <section className="guidance-panel" aria-labelledby="guidance-title">
    <div className="section-heading">
      <div><span className="eyebrow">LỘ TRÌNH CỦA BẠN</span><h2 id="guidance-title">Tình hình học tập hiện tại</h2></div>
      <button className="button button-secondary" disabled={loading} onClick={() => setReload(value => value + 1)}>Cập nhật lộ trình</button>
    </div>
    {synthetic && <p className="notice"><strong>Dữ liệu mô phỏng</strong> · Lớp {run.code} · chỉ xem và thử dự báo.</p>}
    {activityError && <p role="alert" className="notice notice-error">{activityError}</p>}
    {!activity && !activityError && <p role="status">Đang tải thống kê học tập…</p>}
    {activity && <>
      {(!activity.started || synthetic) && <p>Lớp {activity.started ? 'bắt đầu' : 'chưa bắt đầu. Ngày bắt đầu'} {dateTime(activity.starts_at)} ({activity.timezone}).</p>}
      <dl className="guidance-stats">
        <div><dt>Ngày có xem trang</dt><dd>{activity.active_days}</dd></div>
        <div><dt>Lượt xem trang hợp lệ</dt><dd>{activity.page_views}</dd></div>
        {!loading && !pathError && path && <>
          <div><dt>Chủ đề đã đánh giá</dt><dd>{assessed}</dd></div>
          <div><dt>Chủ đề đã đạt</dt><dd>{mastered}</dd></div>
        </>}
      </dl>
      {activity.started && !activity.page_views && !synthetic && <p>Chưa ghi nhận lượt xem trang. Bạn có thể bắt đầu bằng một tài liệu của học phần.</p>}
    </>}
    {!loading && !pathError && path && <p className="muted">{assessed ? 'Kết quả dùng bài làm mới nhất của phiên bản quiz hiện hành.' : 'Chưa có kết quả để đánh giá theo quiz hiện hành.'}</p>}
    {!synthetic && <button className="text-button" onClick={onLibrary}>Xem tài liệu học phần</button>}
    <h3>Bước học tiếp theo</h3>
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
        {!synthetic && <button className="button button-secondary" onClick={() => onTopic(step.topic_id)}>Mở quiz {step.topic_code}</button>}
      </li>)}</ol> : <p className="notice">{!path.topic_states.length ? 'Học phần chưa có chủ đề.' : path.unavailable_topics.length ? 'Các quiz đã có đều đạt hoặc chưa có quiz để đánh giá thêm; hãy đọc tài liệu và chờ giảng viên công bố.' : 'Bạn đã đạt tất cả quiz hiện tại.'}</p>}
      {!!path.unavailable_topics.length && <p className="muted">Chưa có quiz: {path.unavailable_topics.map(item => item.topic_code).join(', ')}.</p>}
    </>}
    <div className="risk-panel">
      <h3>Dự báo rủi ro thử nghiệm</h3>
      <p className="muted">Mô hình học từ OULAD, chưa xác nhận trên sinh viên StudyHub. Điểm chưa hiệu chỉnh xác suất, không quyết định việc đạt từng chủ đề.</p>
      {predictionLoading && <p role="status">Đang tải trạng thái dự báo…</p>}
      {predictionError && <p className="notice notice-error" role="alert">{predictionError}</p>}
      {prediction?.status === 'not_ready' && <>
        <p><strong>Đang thu thập dữ liệu</strong> · Chưa có điểm dự báo.</p>
        {activity && <p>Đã hoàn tất {activity.completed_days}/{activity.window_days} ngày lịch trong cửa sổ dự báo.</p>}
        <p>Có thể tính sớm nhất từ {dateTime(prediction.cutoff_end_at)} ({run.timezone}).</p>
      </>}
      {prediction?.status === 'not_computed' && <p>Đã qua mốc thời gian. Chưa tính dự báo cho lớp học này.</p>}
      {prediction?.status === 'model_unavailable' && <p>Mô hình chưa sẵn sàng. Bạn có thể thử lại hoặc liên hệ người vận hành.</p>}
      {prediction?.status === 'insufficient_data' && <p>Chưa đủ dữ liệu: không có lượt xem trang hợp lệ trong cửa sổ dự báo.</p>}
      {synthetic && activity && <p className="muted">Hết cửa sổ dự báo lúc {dateTime(activity.cutoff_end_at)} ({activity.timezone}).</p>}
      {prediction?.status === 'ok' && prediction.risk_score !== null && <>
        <p className="risk-score">{(prediction.risk_score * 100).toFixed(1)}/100 <span>{synthetic ? 'Dữ liệu mô phỏng' : 'Dữ liệu thật'} · {prediction.threshold_exceeded ? 'Đạt hoặc vượt ngưỡng thử nghiệm' : 'Dưới ngưỡng thử nghiệm'}</span></p>
        {synthetic && <p>Mô hình chạy thật trên dữ liệu mô phỏng.</p>}
        {prediction.threshold !== undefined && <p className="muted">Ngưỡng {(prediction.threshold * 100).toFixed(1)}/100 · mô hình {prediction.model_code}</p>}
        {prediction.computed_at && <p className="muted">Tính lúc {dateTime(prediction.computed_at)} ({run.timezone}).</p>}
        {prediction.explanation && <details><summary>Đặc trưng và giải thích điểm</summary>
          <p>SHAP mô tả đóng góp của các đặc trưng vào điểm. Mốc nền {(prediction.explanation.base_value * 100).toFixed(1)} điểm.</p>
          {prediction.explanation.contributions.map(item => <p key={item.feature}>{featureLabels[item.feature]}: {item.value === null ? 'Thiếu dữ liệu' : item.value.toFixed(1)} · đóng góp {item.contribution >= 0 ? '+' : ''}{(item.contribution * 100).toFixed(2)} điểm</p>)}
        </details>}
      </>}
      <div className="guidance-actions">
        {!predictionLoading && prediction && prediction.status !== 'not_ready' && <button className="button button-secondary" disabled={computing} onClick={() => void compute()}>{computing ? 'Đang tính dự báo…' : 'Tính dự báo'}</button>}
        {activity?.linked_run && <button className="button button-secondary" onClick={() => onSwitchRun(activity.linked_run!)}>
          {synthetic ? 'Quay lại lớp thật' : 'Xem bản demo dự báo'} · {activity.linked_run.code}
        </button>}
      </div>
    </div>
  </section>
}

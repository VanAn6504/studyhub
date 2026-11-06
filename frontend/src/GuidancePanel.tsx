import { useEffect, useRef, useState } from 'react'
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
  elapsed_days: 'Ngày lịch đã hoàn tất', active_days_7: 'Ngày có xem trong 7 ngày',
  distinct_resources: 'Tài liệu khác nhau đã xem',
}
const deadlineLabels = {
  upcoming: 'Chưa đến hạn', due_soon: 'Sắp đến hạn', overdue: 'Quá hạn chưa nộp', archived: 'Phiên bản cũ',
  submitted_on_time: 'Đã nộp đúng hạn', submitted_late: 'Đã nộp muộn',
}

export default function GuidancePanel({ run, csrfToken, refresh, activityRefresh, topics, firstMaterial, onTopic, onRead, onLibrary, onSwitchRun, onExpired }: {
  run: CourseRun; csrfToken: string; refresh: number; activityRefresh: number; topics: Topic[];
  onTopic: (id: string) => void;
  onRead: (material: { document_version_id: string; title: string; page_start: number }) => void;
  firstMaterial?: { document_version_id: string; title: string; page_start: number };
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
  const forecastSequence = useRef(0)
  const forecastBusy = useRef(false)
  const synthetic = run.data_origin === 'synthetic'
  const forecastUrl = `/course-runs/${run.id}/${synthetic ? 'prediction' : 'engagement-forecast'}`
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
    if (forecastBusy.current) return
    let stopped = false
    const sequence = ++forecastSequence.current
    setPredictionLoading(true)
    setPredictionError('')
    request<PredictionResult>(forecastUrl)
      .then(value => { if (!stopped && sequence === forecastSequence.current) setPrediction(value) })
      .catch(error => {
        if (stopped || sequence !== forecastSequence.current) return
        setPrediction(null)
        setPredictionError(errorMessage(error))
        if (error instanceof ApiError && error.status === 401) onExpired()
      })
      .finally(() => { if (!stopped && sequence === forecastSequence.current) setPredictionLoading(false) })
    return () => { stopped = true }
  }, [forecastUrl, refresh, activityRefresh])
  async function compute() {
    if (forecastBusy.current) return
    forecastBusy.current = true
    ++forecastSequence.current
    setComputing(true)
    setPredictionLoading(false)
    setPredictionError('')
    if (!synthetic) setReload(value => value + 1)
    try {
      setPrediction(await request<PredictionResult>(synthetic ? forecastUrl + 's' : forecastUrl, {
        method: 'POST', csrfToken, body: {},
      }))
    } catch (error) {
      if (error instanceof ApiError && error.code === 'MODEL_UNAVAILABLE')
        setPrediction(current => current ? { ...current, status: 'model_unavailable', risk_score: null } : null)
      else setPredictionError(errorMessage(error))
      if (error instanceof ApiError && error.status === 401) onExpired()
    } finally { forecastBusy.current = false; setComputing(false) }
  }
  const mastered = path?.topic_states.filter(item => item.state === 'mastered').length ?? 0
  const weak = path?.topic_states.filter(item => item.state === 'weak').length ?? 0
  const unassessed = path?.topic_states.filter(item => item.state === 'not_assessed').length ?? 0
  const assessed = mastered + weak
  const dateTime = (value: string) => new Date(value).toLocaleString('vi-VN', { timeZone: run.timezone })
  const warnings = path?.warnings.map(warning => topics.find(topic => topic.id === warning.topic_id)?.code).join(', ')
  const overdue = activity?.schedule.find(item => item.status === 'overdue')
  const lastRead = activity?.last_read
  const firstStep = path?.steps[0]
  const viewedStep = lastRead && path?.steps.find(step => step.state === 'not_assessed' &&
    step.prerequisite_topic_ids?.every(id => path.topic_states.some(state =>
      state.topic_id === id && ['mastered', 'not_available'].includes(state.state))) &&
    step.materials.some(material => material.document_version_id === lastRead.document_version_id &&
      material.page_start <= lastRead.page && material.page_end >= lastRead.page))
  const next = firstStep?.reason === 'no_current_assessment' && viewedStep ? viewedStep : firstStep
  const readNext = next?.materials[0]
  const seenNext = lastRead && next?.materials.some(material => material.document_version_id === lastRead.document_version_id &&
    material.page_start <= lastRead.page && material.page_end >= lastRead.page)
  const nextAction = overdue ? {
    title: `Làm quiz ${overdue.topic_code}`, reason: `Hạn nộp ${dateTime(overdue.due_at)} đã qua. Bạn vẫn có thể nộp bài.`,
    action: () => onTopic(overdue.topic_id),
  } : activity && activity.page_views === 0 && assessed === 0 && (firstMaterial || readNext) ? {
    title: 'Mở tài liệu đầu tiên', reason: 'Chưa ghi nhận hoạt động học trong lớp này.',
    action: () => onRead((readNext || firstMaterial)!),
  } : next && next.reason === 'low_quiz_score' && readNext ? {
    title: `Ôn ${next.topic_code}`, reason: reasons[next.reason], action: () => onRead(readNext),
  } : next ? {
    title: `Làm quiz ${next.topic_code}`,
    reason: seenNext ? 'Bạn đã xem tài liệu của chủ đề này. Hãy kiểm tra mức độ hiểu bằng quiz.' : reasons[next.reason],
    action: () => onTopic(next.topic_id),
  } : lastRead ? {
    title: 'Tiếp tục đọc', reason: `${lastRead.title} · trang ${lastRead.page}`,
    action: () => onRead({ ...lastRead, page_start: lastRead.page }),
  } : {
    title: 'Xem tài liệu học phần', reason: 'Xem tài liệu đã công bố để chọn nội dung học tiếp.', action: onLibrary,
  }
  return <section className="guidance-panel" aria-labelledby="guidance-title">
    <div className="section-heading">
      <div><span className="eyebrow">LỘ TRÌNH CỦA BẠN</span><h2 id="guidance-title">{synthetic ? 'Tình hình học tập hiện tại' : 'Việc nên làm tiếp'}</h2></div>
      <button className="button button-secondary" disabled={loading || computing}
        onClick={() => synthetic ? setReload(value => value + 1) : void compute()}>
        {synthetic ? 'Cập nhật lộ trình' : computing ? 'Đang cập nhật đánh giá…' : 'Cập nhật đánh giá'}
      </button>
    </div>
    {!synthetic && <>
      {activity && !loading && !pathError && <div className="notice">
        <p>{nextAction.reason}</p>
        <button className="button button-primary" onClick={nextAction.action}>{nextAction.title}</button>
      </div>}
      <h3>Tình hình học tập hiện tại</h3>
    </>}
    {synthetic && <p className="notice"><strong>Dữ liệu mô phỏng</strong> · Lớp {run.code} · chỉ xem và thử dự báo.</p>}
    {activityError && <p role="alert" className="notice notice-error">{activityError}</p>}
    {!activity && !activityError && <p role="status">Đang tải thống kê học tập…</p>}
    {activity && <>
      {(!activity.started || synthetic) && <p>Lớp {activity.started ? 'bắt đầu' : 'chưa bắt đầu. Ngày bắt đầu'} {dateTime(activity.starts_at)} ({activity.timezone}).</p>}
      <dl className="guidance-stats">
        <div><dt>Ngày có xem trang · {synthetic ? 'từ đầu lớp' : '7 ngày'}</dt><dd>{synthetic ? activity.active_days : activity.active_days_7}</dd></div>
        <div><dt>Lượt xem trang hợp lệ · {synthetic ? 'từ đầu lớp' : '7 ngày'}</dt><dd>{synthetic ? activity.page_views : activity.page_views_7}</dd></div>
        {!synthetic && <div><dt>Tài liệu khác nhau đã xem · 7 ngày</dt><dd>{activity.documents_7}</dd></div>}
        {!loading && !pathError && path && <>
          <div><dt>Chủ đề đã đánh giá</dt><dd>{assessed}</dd></div>
          <div><dt>Chủ đề đã đạt</dt><dd>{mastered}</dd></div>
          {!synthetic && <>
            <div><dt>Chủ đề cần ôn</dt><dd>{weak}</dd></div>
            <div><dt>Chủ đề chưa đánh giá</dt><dd>{unassessed}</dd></div>
            <div><dt>Chủ đề chưa có quiz</dt><dd>{path.unavailable_topics.length}</dd></div>
          </>}
        </>}
      </dl>
      {!synthetic && <>
        {activity.last_activity_at
          ? <p>Lần xem trang gần nhất {dateTime(activity.last_activity_at)} ({run.timezone}).</p>
          : activity.started && <p>{assessed ? 'Chưa ghi nhận lượt xem trang.' : 'Chưa bắt đầu học trên StudyHub.'}</p>}
        {lastRead && nextAction.title !== 'Tiếp tục đọc' && <button className="text-button"
          onClick={() => onRead({ ...lastRead, page_start: lastRead.page })}>Đọc tiếp {lastRead.title} · trang {lastRead.page}</button>}
        <h4>Lịch quiz của lớp</h4>
        {activity.schedule.length ? <ul className="path-steps">{activity.schedule.map(item => <li key={item.quiz_version_id}>
          <strong>{item.topic_code} · {item.title} · v{item.version}</strong>
          <p>Hạn {dateTime(item.due_at)} ({run.timezone}) · {deadlineLabels[item.status]}
            {item.graded && ' · Đã chấm'}{!item.current && item.status !== 'archived' && ' · Phiên bản cũ'}</p>
          {item.current && !item.submitted_at && <button className="text-button" onClick={() => onTopic(item.topic_id)}>Mở quiz {item.topic_code}</button>}
        </li>)}</ul> : <p className="muted">Lớp chưa có quiz được đặt hạn nộp.</p>}
      </>}
    </>}
    {!loading && !pathError && path && <p className="muted">{assessed ? 'Kết quả dùng bài làm mới nhất của phiên bản quiz hiện hành.' : 'Chưa có kết quả để đánh giá theo quiz hiện hành.'}</p>}
    <details open={synthetic || undefined}><summary>Bước học tiếp theo theo từng chủ đề</summary>
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
    </details>
    <div className="risk-panel">
      <h3>Dự báo rủi ro thử nghiệm</h3>
      <p className="muted">Mô hình học từ OULAD, chưa xác nhận trên sinh viên StudyHub. Điểm chưa hiệu chỉnh xác suất, không quyết định việc đạt từng chủ đề.</p>
      {predictionLoading && <p role="status">Đang tải trạng thái dự báo…</p>}
      {predictionError && <p className="notice notice-error" role="alert">{predictionError}</p>}
      {synthetic && prediction?.status === 'not_ready' && <>
        <p><strong>Đang thu thập dữ liệu</strong> · Chưa có điểm dự báo.</p>
        {activity && <p>Đã hoàn tất {activity.completed_days}/{activity.window_days} ngày lịch trong cửa sổ dự báo.</p>}
        {prediction.cutoff_end_at && <p>Có thể tính sớm nhất từ {dateTime(prediction.cutoff_end_at)} ({run.timezone}).</p>}
      </>}
      {!synthetic && prediction?.status === 'not_ready' && <p>Chưa hoàn tất ngày học đầu tiên. Bạn vẫn có thể cập nhật tình hình học tập.</p>}
      {!synthetic && prediction?.cutoff_end_at && <p>Dữ liệu dự báo chốt trước {dateTime(prediction.cutoff_end_at)} ({run.timezone}).</p>}
      {prediction?.status === 'outside_range' && <p>Thời điểm này nằm ngoài dải ngày đã kiểm thử của mô hình.</p>}
      {prediction?.status === 'not_computed' && <p>{synthetic ? 'Đã qua mốc thời gian. Chưa tính dự báo cho lớp học này.' : 'Chưa có điểm cho mốc dữ liệu này. Bấm Cập nhật đánh giá để tính.'}</p>}
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
        {synthetic && !predictionLoading && prediction && prediction.status !== 'not_ready' && <button className="button button-secondary" disabled={computing} onClick={() => void compute()}>{computing ? 'Đang tính dự báo…' : 'Tính dự báo'}</button>}
        {activity?.linked_run && <button className="button button-secondary" onClick={() => onSwitchRun(activity.linked_run!)}>
          {synthetic ? 'Quay lại lớp thật' : 'Xem bản demo dự báo'} · {activity.linked_run.code}
        </button>}
      </div>
    </div>
  </section>
}

import type { PredictionResult } from './learningTypes'

const scoreFormat = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 1 })
type Contribution = NonNullable<PredictionResult['explanation']>['contributions'][number]

function describe({ feature, value }: Contribution, activeDays: number | null | undefined) {
  if (value === null || !Number.isFinite(value)) return null
  const count = scoreFormat.format(value)
  switch (feature) {
    case 'active_days': return value ? `Có lượt xem tài liệu vào ${count} ngày kể từ đầu lớp.` : 'Chưa có lượt xem tài liệu kể từ đầu lớp.'
    case 'active_days_7': return value ? `Có lượt xem tài liệu vào ${count} ngày trong 7 ngày gần mốc tính.` : 'Chưa có lượt xem tài liệu trong 7 ngày gần mốc tính.'
    case 'days_since_last_activity':
      if (!activeDays) return null
      return value ? `Lần xem gần nhất cách ngày cuối được tính ${count} ngày.` : 'Có xem tài liệu vào ngày cuối được tính.'
    case 'distinct_resources': return value ? `Đã xem ${count} tài liệu khác nhau.` : 'Chưa có tài liệu nào được ghi nhận là đã xem.'
    case 'material_interactions': return `Có ${count} lượt xem trang tài liệu.`
    case 'assessment_count': return value ? `Có bài quiz đã chấm ở ${count} chủ đề.` : 'Chưa có bài quiz nào được chấm.'
    case 'mean_assessment_score': return `Điểm trung bình của các lần làm quiz đầu tiên là ${count} trên 100.`
    case 'elapsed_days': return `Đã qua ${count} ngày kể từ đầu lớp.`
    default: return null
  }
}

export default function ForecastSummary({ prediction, synthetic }: {
  prediction: PredictionResult
  synthetic: boolean
}) {
  const score = prediction.risk_score
  if (prediction.status !== 'ok' || score === null || !Number.isFinite(score)) return null
  const attention = prediction.threshold_exceeded
  const contributions = prediction.explanation?.contributions ?? []
  const activeDays = contributions.find(item => item.feature === 'active_days')?.value
  const factors = contributions.flatMap(item => {
    const description = describe(item, activeDays)
    return description && Number.isFinite(item.contribution) && item.contribution !== 0
      ? [{ feature: item.feature, description, raisesRisk: item.contribution > 0 }]
      : []
  })
  const missingQuiz = contributions.some(item => item.feature === 'mean_assessment_score' && item.value === null)
  return <>
    <p className="risk-score">
      {attention === true ? 'Nên chú ý việc học' : attention === false ? 'Ít dấu hiệu cần chú ý' : 'Đã có dự báo tham khảo'}
      <span>{synthetic ? 'Dữ liệu mô phỏng' : 'Dữ liệu học tập của bạn'}</span>
    </p>
    <p>Điểm cảnh báo tham khảo <strong>{scoreFormat.format(score * 100)} trên 100</strong>. Điểm càng cao, việc xem lại tiến độ càng đáng ưu tiên.</p>
    {synthetic && <p>Ví dụ này dùng hoạt động mô phỏng để minh họa cách hệ thống đưa ra dự báo.</p>}
    {(factors.length > 0 || missingQuiz) && <details>
      <summary>Vì sao có dự báo này?</summary>
      {[true, false].map(raisesRisk => {
        const group = factors.filter(factor => factor.raisesRisk === raisesRisk)
        return group.length > 0 && <div key={String(raisesRisk)}>
          <p><strong>{raisesRisk ? 'Điều làm điểm cảnh báo tăng' : 'Điều làm điểm cảnh báo giảm'}</strong></p>
          <ul>{group.map(factor => <li key={factor.feature}>{factor.description}</li>)}</ul>
        </div>
      })}
      {missingQuiz && <p>Chưa có điểm quiz để tham khảo.</p>}
    </details>}
  </>
}

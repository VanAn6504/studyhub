export type DocumentVersion = {
  id: string
  version: number
  page_count: number
  original_filename: string
  byte_size: number
  sha256: string
  status: string
}
export type LearningDocument = {
  document_type: 'textbook' | 'lecture' | 'supplement'
  show_in_learning: boolean
  id: string
  code: string
  title: string
  status: 'draft' | 'published' | 'archived'
  versions: DocumentVersion[]
}
export type QuestionContent = {
  stem: string
  options: Record<'A' | 'B' | 'C' | 'D', string>
  correct_option: 'A' | 'B' | 'C' | 'D'
  explanation: string
  sources: { document_version_id: string; pdf_page: number }[]
}
export type QuestionVersion = QuestionContent & {
  id: string
  question_id: string
  code: string
  version: number
}
export type AttemptItem = {
  quiz_version_item_id: string
  stem: string
  options: Record<string, string>
  selected_option: string | null
  correct_option?: string
  is_correct?: boolean
  explanation?: string
  sources?: { document_version_id: string; pdf_page: number }[]
}
export type Attempt = {
  id: string
  topic_id: string
  quiz_version_id: string
  status: 'in_progress' | 'completed'
  answer_revision: number
  items: AttemptItem[]
  score_percent?: number
  correct_count?: number
  total_questions?: number
  passed_for_attempt_version?: boolean
  counts_for_current_mastery?: boolean
  started_at: string
  graded_at?: string
}
export type LearningEventInput = {
  client_event_id: string
  viewer_session_id: string
  type: 'document_open' | 'page_view'
  document_version_id: string
  pdf_page?: number
}
export type ActivityEvent = LearningEventInput & {
  id: string
  occurred_at: string
  received_at: string
  data_origin: string
}
export type StudentReport = {
  enrollment_id: string
  student_email: string
  display_name: string
  enrollment_status: string
  page_views: number
  attempt_count: number
  latest_results: Attempt[]
  learning_path: LearningPath
}

export type TopicState = {
  topic_id: string
  topic_code: string
  title: string
  state: string
  score_percent: number | null
  reason: string
  quiz_version_id: string | null
}
export type LearningPath = {
  revision: number
  generated_at: string
  data_origin: string
  topic_states: TopicState[]
  unavailable_topics: TopicState[]
  warnings: { topic_id: string; reason: string }[]
  steps: (TopicState & {
    position: number
    prerequisite_topic_ids?: string[]
    materials: {
      document_version_id: string
      title: string
      document_code: string
      page_start: number
      page_end: number
    }[]
  })[]
}
export type QuizDeadline = {
  quiz_version_id: string
  version: number
  topic_id: string
  topic_code: string
  title: string
  current: boolean
  due_at: string | null
  due_local: string | null
}
export type LearnerDeadline = QuizDeadline & {
  due_at: string
  status: 'submitted_on_time' | 'submitted_late' | 'archived' | 'overdue' | 'upcoming' | 'due_soon'
  submitted_at: string | null
  graded: boolean
}
export type LearningActivity = {
  active_days: number
  page_views: number
  active_days_7: number
  page_views_7: number
  documents_7: number
  last_activity_at: string | null
  last_read: { document_version_id: string; page: number; title: string } | null
  schedule: LearnerDeadline[]
  starts_at: string
  started: boolean
  timezone: string
  completed_days: number
  window_days: number
  cutoff_end_at: string
  linked_run: { id: string; course_id: string; code: string } | null
}
export type PredictionResult = {
  status: 'not_ready' | 'not_computed' | 'insufficient_data' | 'model_unavailable' | 'outside_range' | 'ok'
  risk_score: number | null
  cutoff_end_at: string | null
  data_origin: string
  model_code?: string
  computed_at?: string
  threshold?: number
  threshold_exceeded?: boolean
  explanation?: {
    base_value: number
    contributions: { feature: string; value: number | null; contribution: number }[]
  }
}

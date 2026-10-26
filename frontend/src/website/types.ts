export type Category = { code: string; name: string; course_count: number }
export type Metadata = {
  title: string
  summary: string
  description: string
  category_code: string | null
  level: 'unspecified' | 'beginner' | 'intermediate' | 'advanced'
  objectives: string[]
  prerequisites: string[]
  outline: string[]
  material_titles: string[]
}
export type PublicRun = {
  id: string
  code: string
  instructor_name: string
  start_date: string
  timezone: string
  status: 'active' | 'closed'
  enrollment_mode: 'invite_only' | 'approval' | 'open'
  opens_at: string | null
  closes_at: string | null
  capacity: number | null
  seats_remaining: number | null
  availability: 'accepting' | 'full' | 'closed' | 'not_started' | 'invite_only'
  admissions_revision: number
}
export type PublicCourse = Metadata & {
  slug: string
  code: string
  instructor_name: string
  category_name: string | null
  published_at: string
  runs: PublicRun[]
}
export type Page<T> = { items: T[]; total: number; limit: number; offset: number }
export type Publication = {
  course_id: string
  slug: string
  status: 'hidden' | 'published'
  draft: Metadata
  published: Metadata | null
  published_at: string | null
}
export type AdmissionSettings = {
  run_id: string
  course_id: string
  course_title: string
  code: string
  status: string
  data_origin: string
  timezone: string
  enrollment_mode: PublicRun['enrollment_mode']
  listed: boolean
  opens_at: string | null
  closes_at: string | null
  capacity: number | null
  active_students: number
  admissions_revision: number
}
export type JoinRequest = {
  id: string
  run_id: string
  run_code: string
  course_id: string
  course_title: string
  slug: string | null
  status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  requested_at: string
  decided_at: string | null
  reason: string
  student_name?: string
  student_email?: string
  admissions_revision: number
}
export type Resume = {
  run_id: string
  course_id: string
  course_title: string
  run_code: string
  topic_id: string | null
  document_version_id: string | null
  view: 'topic' | 'pdf' | 'quiz' | 'progress' | 'results'
  page: number
  updated_at: string | null
  notice: string | null
}
export type MyCourse = {
  course_id: string
  course_title: string
  course_code: string
  run_id: string
  run_code: string
  run_status: 'draft' | 'active' | 'closed'
  data_origin: 'real' | 'synthetic'
  enrollment_status: 'active' | 'inactive'
  progress: { mastered: number; available: number; percent: number | null } | null
  slug: string | null
  resume: Resume | null
}
export type Overview = {
  resume: Resume | null
  courses: MyCourse[]
  review_topics: {
    topic_id: string
    code: string
    title: string
    run_id: string
    course_id: string
  }[]
  pending_requests: JoinRequest[]
  total_classes: number
}
export type TeachingOverview = {
  courses: { id: string; code: string; title: string; publication_status: 'hidden' | 'published' }[]
  runs: { id: string; code: string; course_id: string; status: string; pending_requests: number }[]
  pending_requests: number
}
export type Profile = {
  id: string
  display_name: string
  bio: string
  email: string
  role: 'student' | 'teacher'
}
export const levels: Record<Metadata['level'], string> = {
  unspecified: 'Chưa phân loại',
  beginner: 'Cơ bản',
  intermediate: 'Trung cấp',
  advanced: 'Nâng cao',
}
export const requestLabels = {
  pending: 'Chờ duyệt',
  approved: 'Đã duyệt',
  rejected: 'Từ chối',
  cancelled: 'Đã hủy',
}
export const modeLabels = {
  invite_only: 'Chỉ nhận lời mời',
  approval: 'Giảng viên xét duyệt',
  open: 'Tham gia trực tiếp',
}

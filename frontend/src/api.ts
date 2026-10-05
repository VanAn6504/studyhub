export type User = { id: string; email: string; display_name: string; role: 'student' | 'teacher' }
export type Session = { user: User; csrf_token: string }
export type Course = { id: string; code: string; title: string }
export type CourseRun = {
  id: string
  code: string
  course_id: string
  course_title: string
  course_run_start_date: string
  timezone: string
  status: 'draft' | 'active' | 'closed'
  data_origin: 'real' | 'synthetic'
  student_count?: number
}
export type Topic = {
  id: string
  code: string
  title: string
  order_index: number
  objectives: string[]
  prerequisite_topic_ids: string[]
  materials: Material[]
  quiz: QuizMetadata | null
}
export type Material = {
  document_version_id: string
  document_code: string
  title: string
  version: number
  page_start: number
  page_end: number
  page_count: number
  order_index: number
}
export type QuizMetadata = {
  id: string
  published_version_id: string
  version: number
  status: 'draft' | 'published' | 'retired'
  question_count: number
  pass_percent: number
  min_questions: number
}
type Page<T> = { items: T[]; total: number; limit: number; offset: number }

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message)
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT'
  body?: unknown
  csrfToken?: string
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const multipart = options.body instanceof FormData
  if (options.body !== undefined && !multipart) headers['Content-Type'] = 'application/json'
  if (options.csrfToken) headers['X-CSRF-Token'] = options.csrfToken
  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, {
      method: options.method || 'GET',
      credentials: 'same-origin',
      headers,
      body: multipart
        ? (options.body as FormData)
        : options.body !== undefined
          ? JSON.stringify(options.body)
          : undefined,
    })
  } catch {
    throw new ApiError(
      0,
      'NETWORK_ERROR',
      'Không thể kết nối máy chủ. Kiểm tra kết nối rồi thử lại.',
    )
  }
  if (response.status === 204) return undefined as T
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error?.code || 'REQUEST_FAILED',
      payload?.error?.message ||
        (response.status === 502 || response.status === 503
          ? 'Dịch vụ chưa sẵn sàng. Vui lòng thử lại sau.'
          : 'Không thể hoàn tất yêu cầu. Vui lòng thử lại.'),
      payload?.request_id,
    )
  }
  if (payload === null)
    throw new ApiError(response.status, 'INVALID_RESPONSE', 'Máy chủ trả về dữ liệu không hợp lệ.')
  return payload as T
}

export async function listAll<T>(path: string): Promise<T[]> {
  const result: T[] = []
  let offset = 0
  while (true) {
    const page = await request<Page<T>>(`${path}?limit=100&offset=${offset}`)
    result.push(...page.items)
    offset += page.items.length
    if (offset >= page.total || page.items.length === 0) return result
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError && error.status === 401)
    return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  return error instanceof Error ? error.message : 'Đã có lỗi xảy ra. Vui lòng thử lại.'
}

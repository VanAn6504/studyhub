export type Chunk = {
  id: string
  document_version_id: string
  pdf_page: number
  chunk_index: number
  text: string
  flags: string[]
  extraction_method: 'pypdf' | 'manual'
  kind: 'content' | 'cover' | 'toc' | 'image'
  review_status: 'pending' | 'reviewed' | 'rejected'
  revision: number
  embedding_code: string | null
  auto_eligible: boolean
}
export type RagStatus = {
  enabled: boolean
  legacy: boolean
  status:
    | 'unprepared'
    | 'queued'
    | 'processing'
    | 'ready'
    | 'needs_review'
    | 'failed'
    | 'disabled'
    | 'cancelled'
  generation_id: string | null
  scope_ranges: RagRange[]
  progress?: {
    stage: string
    extracted_pages: number
    chunked_pages: number
    selected_pages: number
    eligible_chunks: number
    embedded_chunks: number
    attempts: number
  }
  error_code: string | null
  document_status: string
  usable_pages: number
  total_pages: number
  counts: Record<'automatic' | 'checked' | 'needs_review' | 'excluded', number>
}
export type RagRange = {
  page_start: number
  page_end: number
  topic_id?: string | null
  label?: string
}
export type RagPage = {
  pdf_page: number
  revision: string
  state: 'automatic' | 'checked' | 'needs_review' | 'excluded'
  issues: string[]
  usable_segments: number
  text: string
  has_transcription: boolean
  text_only: boolean
}
export type Citation = {
  chunk_id: string
  document_version_id: string
  document_code: string
  title: string
  version: number
  pdf_page: number
  excerpt: string
}
export type ChatSession = { id: string; created_at: string }
export type ChatTurn = {
  topic_id?: string | null
  id: string
  request_key: string
  question: string
  answer: string | null
  status: 'pending' | 'answered' | 'insufficient_sources' | 'provider_error' | 'source_unavailable'
  citations: Citation[]
  model_code: string | null
}

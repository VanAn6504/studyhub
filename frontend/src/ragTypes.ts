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
  id: string
  request_key: string
  question: string
  answer: string | null
  status: 'pending' | 'answered' | 'insufficient_sources' | 'provider_error' | 'source_unavailable'
  citations: Citation[]
  model_code: string | null
}

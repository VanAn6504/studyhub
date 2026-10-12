export type WorkspaceView =
  | 'topics'
  | 'topic'
  | 'pdf'
  | 'quiz'
  | 'quiz-editor'
  | 'upload'
  | 'document'
  | 'topic-editor'
  | 'progress'
  | 'results'
  | 'materials'
export type WorkspaceRoute = {
  view: WorkspaceView | 'home' | 'new-course' | 'classes' | 'new-class' | 'report'
  courseId: string
  runId: string
  topicId?: string
  versionId?: string
  page?: number
}
export type NavigationGuard = (next: WorkspaceRoute | null) => Promise<boolean>
const views = new Set([
  'topics',
  'topic',
  'pdf',
  'quiz',
  'quiz-editor',
  'upload',
  'document',
  'topic-editor',
  'progress',
  'results',
  'materials',
  'home',
  'new-course',
  'classes',
  'new-class',
  'report',
])
export function readWorkspaceRoute(): WorkspaceRoute {
  const params = new URLSearchParams(location.hash.slice(1))
  const view = params.get('view') || 'home'
  return {
    view: (views.has(view) ? view : 'home') as WorkspaceRoute['view'],
    courseId: params.get('course') || '',
    runId: params.get('class') || '',
    topicId: params.get('topic') || undefined,
    versionId: params.get('document') || undefined,
    page: Math.max(1, Number(params.get('page')) || 1),
  }
}
export function routeHash(route: WorkspaceRoute) {
  const params = new URLSearchParams({ view: route.view })
  if (route.courseId) params.set('course', route.courseId)
  if (route.runId) params.set('class', route.runId)
  if (route.topicId) params.set('topic', route.topicId)
  if (route.versionId) params.set('document', route.versionId)
  if (route.page) params.set('page', String(route.page))
  return '#' + params.toString()
}

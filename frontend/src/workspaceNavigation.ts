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
  actor?: 'teacher' | 'student'
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
export function isWorkspaceUrl(value: string) {
  const url = new URL(value, location.origin)
  if (url.searchParams.has('view') && !views.has(url.searchParams.get('view')!)) return false
  return (
    url.hash.startsWith('#view=') ||
    url.pathname === '/workspace' ||
    /^\/learn\/[^/]+$/.test(url.pathname) ||
    /^\/teaching\/workspace\/[^/]+$/.test(url.pathname) ||
    url.pathname === '/teaching/new-course'
  )
}
export function readWorkspaceRoute(value = location.href): WorkspaceRoute {
  const url = new URL(value, location.origin)
  const params = new URLSearchParams(url.hash.startsWith('#view=') ? url.hash.slice(1) : url.search)
  const view =
    params.get('view') ||
    (url.pathname === '/teaching/new-course'
      ? 'new-course'
      : url.pathname.startsWith('/learn/') || url.pathname.startsWith('/teaching/workspace/')
        ? 'topics'
        : 'home')
  return {
    actor: url.pathname.startsWith('/teaching')
      ? 'teacher'
      : url.pathname.startsWith('/learn/')
        ? 'student'
        : undefined,
    view: (views.has(view) ? view : 'home') as WorkspaceRoute['view'],
    courseId:
      params.get('course') ||
      (url.pathname.startsWith('/teaching/workspace/') ? url.pathname.split('/')[3] : ''),
    runId:
      params.get('class') || (url.pathname.startsWith('/learn/') ? url.pathname.split('/')[2] : ''),
    topicId: params.get('topic') || undefined,
    versionId: params.get('document') || undefined,
    page: Math.min(2000, Math.max(1, Math.floor(Number(params.get('page')) || 1))),
  }
}
export function routeHash(route: WorkspaceRoute) {
  const params = new URLSearchParams({ view: route.view })
  if (route.courseId) params.set('course', route.courseId)
  if (route.runId) params.set('class', route.runId)
  if (route.topicId) params.set('topic', route.topicId)
  if (route.versionId) params.set('document', route.versionId)
  if (route.page) params.set('page', String(route.page))
  const path =
    route.view === 'new-course'
      ? '/teaching/new-course'
      : route.actor === 'teacher' && route.courseId
        ? '/teaching/workspace/' + route.courseId
        : route.actor === 'student' && route.runId
          ? '/learn/' + route.runId
          : '/workspace'
  return path + '?' + params.toString()
}

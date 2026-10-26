import { useSyncExternalStore } from 'react'

type Guard = (next: string) => boolean | Promise<boolean>
const guards = new Set<Guard>()
const listeners = new Set<() => void>()
let current = location.pathname + location.search + location.hash
let index = Number(history.state?.studyhubIndex) || 0
let busy = false,
  repairing = false
history.replaceState({ ...history.state, studyhubIndex: index }, '', current)

function publish(url: string) {
  current = url
  listeners.forEach((listener) => listener())
}
export function registerNavigationGuard(guard: Guard) {
  guards.add(guard)
  return () => {
    guards.delete(guard)
  }
}
export async function canLeave(next: string) {
  for (const guard of guards) if (!(await guard(next))) return false
  return true
}
export function safeReturn(value: string | null, fallback = '/dashboard') {
  if (
    !value ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    /[\\\u0000-\u0020]/.test(value) ||
    /%5c/i.test(value)
  )
    return fallback
  try {
    const url = new URL(value, location.origin)
    if (
      url.origin !== location.origin ||
      !/^\/(?:$|courses(?:\/[^/]+)?$|dashboard$|my-courses$|profile$|enrollments$|settings\/security$|learn\/[^/]+$|workspace$|teaching(?:\/.*)?$|help$|about$|privacy$)/.test(
        url.pathname,
      )
    )
      return fallback
    return url.pathname + url.search + url.hash
  } catch {
    return fallback
  }
}
export async function navigate(
  to: string,
  options: { replace?: boolean; force?: boolean; scroll?: boolean } = {},
) {
  const url = new URL(to, location.origin)
  if (url.origin !== location.origin || busy) return false
  const next = url.pathname + url.search + url.hash
  if (next === current) return true
  busy = true
  try {
    if (!options.force && !(await canLeave(next))) return false
    if (!options.replace) index++
    history[options.replace ? 'replaceState' : 'pushState']({ studyhubIndex: index }, '', next)
    publish(next)
    if (options.scroll !== false) window.scrollTo({ top: 0 })
    return true
  } finally {
    busy = false
  }
}
// Only for a canonical URL or the current PDF page; never use to leave a form.
export function replacePosition(to: string) {
  const url = new URL(to, location.origin)
  if (url.origin !== location.origin) return
  const next = url.pathname + url.search + url.hash
  history.replaceState({ studyhubIndex: index }, '', next)
  publish(next)
}
window.addEventListener('popstate', async () => {
  const next = location.pathname + location.search + location.hash
  if (repairing) {
    repairing = false
    return
  }
  const nextIndex = Number(history.state?.studyhubIndex)
  if (await canLeave(next)) {
    if (Number.isFinite(nextIndex)) index = nextIndex
    publish(next)
  } else if (Number.isFinite(nextIndex) && nextIndex !== index) {
    repairing = true
    history.go(index - nextIndex)
  } else {
    history.replaceState({ studyhubIndex: index }, '', current)
  }
})
export const getLocation = () => current
export function subscribeLocation(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}
export function useLocation() {
  return useSyncExternalStore(subscribeLocation, getLocation)
}

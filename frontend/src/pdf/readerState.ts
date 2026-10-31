export type ReadingPosition = { page: number; fraction: number }
export type ReadingMode = 'continuous' | 'single'
export type ReadingSession = { id: string; opened: boolean; lastPage: number }
export const foldText = (text: string) =>
  text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
export function savedPosition(scope: string, version: string): ReadingPosition | null {
  try {
    const v = JSON.parse(localStorage.getItem(`studyhub:reader:${scope}:${version}`) || 'null')
    return v && Number.isInteger(v.page) && v.page >= 1 && v.page <= 2000
      ? { page: v.page, fraction: Math.max(0, Math.min(0.95, Number(v.fraction) || 0)) }
      : null
  } catch {
    return null
  }
}
export function storePosition(scope: string, version: string, value: ReadingPosition) {
  try {
    localStorage.setItem(`studyhub:reader:${scope}:${version}`, JSON.stringify(value))
  } catch {
    /* Server resume remains available when storage is disabled. */
  }
}
export function preferredMode(scope: string, fallback: ReadingMode): ReadingMode {
  try {
    const v = localStorage.getItem(`studyhub:reader-mode:${scope}`)
    return v === 'continuous' || v === 'single' ? v : fallback
  } catch {
    return fallback
  }
}
export function storeMode(scope: string, value: ReadingMode) {
  try {
    localStorage.setItem(`studyhub:reader-mode:${scope}`, value)
  } catch {
    /* Optional preference. */
  }
}

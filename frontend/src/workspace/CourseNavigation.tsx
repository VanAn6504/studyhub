import { useEffect, useRef, useState } from 'react'
import type { WorkspaceRoute } from '../workspaceNavigation'

export function useNarrowReader() {
  const [narrow, setNarrow] = useState(() => matchMedia('(max-width: 1000px)').matches)
  useEffect(() => {
    const media = matchMedia('(max-width: 1000px)'),
      update = () => setNarrow(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return narrow
}
export default function CourseNavigation({
  title,
  classCode,
  items,
  active,
  collapsed,
  drawer,
  onClose,
  onNavigate,
}: {
  title: string
  classCode?: string
  items: [WorkspaceRoute['view'], string][]
  active: string
  collapsed: boolean
  drawer: boolean
  onClose: () => void
  onNavigate: (view: WorkspaceRoute['view']) => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const narrow = useNarrowReader()
  useEffect(() => {
    const el = dialog.current
    if (narrow && drawer && !el?.open) el?.showModal()
    else if ((!narrow || !drawer) && el?.open) el.close()
  }, [drawer, narrow])
  function content() {
    return (
      <>
        <p className="course-nav-title">{title}</p>
        {classCode && <p className="muted">Lớp {classCode}</p>}
        <nav aria-label="Điều hướng học phần">
          {items.map(([view, text]) => (
            <button
              className={`nav-item ${active === view ? 'nav-active' : ''}`}
              aria-current={active === view ? 'page' : undefined}
              key={view}
              onClick={() => {
                onNavigate(view)
                onClose()
              }}
            >
              {text}
            </button>
          ))}
        </nav>
      </>
    )
  }
  return (
    <>
      <aside className="course-navigation" id="learning-navigation" hidden={collapsed || narrow}>
        {content()}
      </aside>
      <dialog
        id="learning-drawer"
        aria-label="Điều hướng học phần"
        className="course-drawer"
        ref={dialog}
        onCancel={onClose}
        onClose={onClose}
      >
        <button className="button button-secondary" onClick={onClose}>
          Đóng điều hướng
        </button>
        {content()}
      </dialog>
    </>
  )
}

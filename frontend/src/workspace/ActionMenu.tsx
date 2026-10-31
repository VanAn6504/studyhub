import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

export default function ActionMenu({ label, children }: { label: string; children: ReactNode }) {
  const ref = useRef<HTMLDetailsElement>(null)
  useEffect(() => {
    function outside(e: PointerEvent) {
      if (!ref.current?.contains(e.target as Node)) ref.current?.removeAttribute('open')
    }
    function escape(e: KeyboardEvent) {
      if (e.key === 'Escape' && ref.current?.open) {
        ref.current.open = false
        ref.current.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [])
  return (
    <details ref={ref} className="action-menu">
      <summary>{label}</summary>
      <div
        className="action-menu-items"
        onClick={(e) => {
          if ((e.target as HTMLElement).closest('a,button')) ref.current!.open = false
        }}
      >
        {children}
      </div>
    </details>
  )
}

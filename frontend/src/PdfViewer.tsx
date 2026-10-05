import { useEffect, useRef, useState } from 'react'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import type { LearningEventInput } from './learningTypes'

GlobalWorkerOptions.workerSrc = workerUrl

export default function PdfViewer({
  runId,
  versionId,
  title,
  initialPage = 1,
  onEvent,
  onClose,
}: {
  runId: string
  versionId: string
  title: string
  initialPage?: number
  onEvent?: (event: LearningEventInput) => void
  onClose: () => void
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [page, setPage] = useState(initialPage)
  const [rendered, setRendered] = useState(0)
  const [width, setWidth] = useState(600)
  const [error, setError] = useState('')
  const [text, setText] = useState('')
  const canvas = useRef<HTMLCanvasElement>(null)
  const container = useRef<HTMLDivElement>(null)
  const session = useRef(crypto.randomUUID())
  const opened = useRef(false)
  const lastPage = useRef(0)
  const eventCallback = useRef(onEvent)
  eventCallback.current = onEvent

  useEffect(() => {
    const task = getDocument({
      url: `/api/v1/course-runs/${runId}/document-versions/${versionId}/content`,
      withCredentials: true,
    })
    let stopped = false
    task.promise
      .then((value) => {
        if (!stopped) setPdf(value)
      })
      .catch(() => {
        if (!stopped)
          setError('Không thể tải PDF. Thử mở lại tài liệu hoặc kiểm tra phiên đăng nhập.')
      })
    return () => {
      stopped = true
      void task.destroy()
    }
  }, [runId, versionId])

  useEffect(() => {
    if (!container.current) return
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(180, Math.min(1000, entries[0].contentRect.width))),
    )
    observer.observe(container.current)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!pdf || !canvas.current) return
    let stopped = false
    let render: RenderTask | undefined
    setRendered(0)
    setError('')
    pdf
      .getPage(page)
      .then(async (value) => {
        if (stopped || !canvas.current) return
        const base = value.getViewport({ scale: 1 })
        const viewport = value.getViewport({ scale: width / base.width })
        const ratio = Math.min(window.devicePixelRatio || 1, 2)
        const target = canvas.current
        target.width = Math.floor(viewport.width * ratio)
        target.height = Math.floor(viewport.height * ratio)
        target.style.width = `${viewport.width}px`
        target.style.height = `${viewport.height}px`
        render = value.render({ canvas: target, viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
        await render.promise
        if (stopped) return
        setRendered(page)
        const content = await value.getTextContent()
        if (!stopped)
          setText(content.items.map((item) => ('str' in item ? item.str : '')).join(' '))
      })
      .catch((failure) => {
        if (!stopped && failure?.name !== 'RenderingCancelledException')
          setError('Không thể hiển thị trang PDF này.')
      })
    return () => {
      stopped = true
      render?.cancel()
    }
  }, [pdf, page, width])

  useEffect(() => {
    const target = canvas.current
    if (!target || rendered !== page) return
    let visible = false
    let timer: ReturnType<typeof setTimeout> | undefined
    function schedule() {
      clearTimeout(timer)
      if (!visible || document.visibilityState !== 'visible') return
      timer = setTimeout(() => {
        const callback = eventCallback.current
        if (!callback) return
        const base = { viewer_session_id: session.current, document_version_id: versionId }
        if (!opened.current) {
          opened.current = true
          callback({ ...base, client_event_id: crypto.randomUUID(), type: 'document_open' })
        }
        if (lastPage.current !== page) {
          lastPage.current = page
          callback({
            ...base,
            client_event_id: crypto.randomUUID(),
            type: 'page_view',
            pdf_page: page,
          })
        }
      }, 500)
    }
    const observer = new IntersectionObserver((entries) => {
      visible = entries[0].isIntersecting
      schedule()
    })
    observer.observe(target)
    document.addEventListener('visibilitychange', schedule)
    return () => {
      clearTimeout(timer)
      observer.disconnect()
      document.removeEventListener('visibilitychange', schedule)
    }
  }, [page, rendered, versionId])

  return (
    <section className="pdf-viewer" aria-label={`Trình xem ${title}`}>
      <div className="learning-heading">
        <h3>{title}</h3>
        <button className="button button-secondary" onClick={onClose}>
          Đóng tài liệu
        </button>
      </div>
      <div className="pdf-toolbar">
        <button
          className="button button-secondary"
          disabled={!pdf || page <= 1}
          onClick={() => setPage((value) => value - 1)}
        >
          Trang trước
        </button>
        <label>
          Trang{' '}
          <input
            aria-label="Trang PDF"
            type="number"
            min={1}
            max={pdf?.numPages || 1}
            value={page}
            onChange={(event) => {
              const value = Number(event.target.value)
              if (Number.isInteger(value) && value >= 1 && value <= (pdf?.numPages || 1))
                setPage(value)
            }}
          />{' '}
          / {pdf?.numPages || '…'}
        </label>
        <button
          className="button button-secondary"
          disabled={!pdf || page >= pdf.numPages}
          onClick={() => setPage((value) => value + 1)}
        >
          Trang sau
        </button>
      </div>
      {error && (
        <p className="notice notice-error" role="alert">
          {error}
        </p>
      )}
      {!pdf && !error && <p role="status">Đang tải PDF…</p>}
      <div className="pdf-canvas-container" ref={container}>
        <canvas ref={canvas} aria-label={`Trang ${page} của ${title}`} />
      </div>
      {rendered > 0 && (
        <details className="pdf-text">
          <summary>Đọc văn bản của trang</summary>
          <p>{text || 'Trang này không có lớp văn bản.'}</p>
        </details>
      )}
    </section>
  )
}

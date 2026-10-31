import { useEffect, useRef, useState } from 'react'
import { TextLayer } from 'pdfjs-dist'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
import { foldText } from './readerState'

export default function PdfPage({
  pdf,
  number,
  width,
  height,
  query,
  selectedMatch,
  onReady,
}: {
  pdf: PDFDocumentProxy
  number: number
  width: number
  height: number
  query: string
  selectedMatch?: number
  onReady: () => void
}) {
  const canvas = useRef<HTMLCanvasElement>(null),
    layer = useRef<HTMLDivElement>(null),
    textLayer = useRef<TextLayer | null>(null)
  const [ready, setReady] = useState(false),
    [error, setError] = useState(''),
    [text, setText] = useState('')
  const callback = useRef(onReady)
  callback.current = onReady
  function highlight() {
    const target = textLayer.current
    if (!target) return
    const needle = foldText(query.trim()),
      strings = target.textContentItemsStr.map(foldText),
      full = strings.join(' '),
      matches: number[] = []
    if (needle)
      for (
        let at = full.indexOf(needle);
        at >= 0;
        at = full.indexOf(needle, at + Math.max(1, needle.length))
      )
        matches.push(at)
    let offset = 0
    target.textDivs.forEach((span, i) => {
      const end = offset + strings[i].length
      span.classList.toggle(
        'pdf-match',
        matches.some((at) => at < end && at + needle.length > offset),
      )
      span.classList.toggle(
        'pdf-match-current',
        selectedMatch !== undefined &&
          matches[selectedMatch] !== undefined &&
          matches[selectedMatch] < end &&
          matches[selectedMatch] + needle.length > offset,
      )
      offset = end + 1
    })
  }
  const highlighter = useRef(highlight)
  highlighter.current = highlight
  useEffect(() => {
    highlight()
  }, [query, selectedMatch, ready])
  useEffect(() => {
    let stopped = false,
      render: RenderTask | undefined,
      page: Awaited<ReturnType<PDFDocumentProxy['getPage']>> | undefined
    setReady(false)
    setError('')
    setText('')
    const work = (async () => {
      page = await pdf.getPage(number)
      if (stopped || !canvas.current || !layer.current) return
      const viewport = page.getViewport({ scale: width / page.getViewport({ scale: 1 }).width })
      const ratio = Math.min(
        devicePixelRatio || 1,
        2,
        Math.sqrt(8_000_000 / (viewport.width * viewport.height)),
      )
      const target = canvas.current
      target.width = Math.ceil(viewport.width * ratio)
      target.height = Math.ceil(viewport.height * ratio)
      render = page.render({ canvas: target, viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
      await render.promise
      if (stopped) return
      const content = await page.getTextContent()
      if (stopped || !layer.current) return
      layer.current.replaceChildren()
      layer.current.style.setProperty('--total-scale-factor', String(viewport.scale))
      textLayer.current = new TextLayer({
        textContentSource: content,
        viewport,
        container: layer.current,
      })
      await textLayer.current.render()
      if (stopped) return
      setText(content.items.map((item) => ('str' in item ? item.str : '')).join(' '))
      highlighter.current()
      setReady(true)
      callback.current()
    })().catch((failure) => {
      if (
        !stopped &&
        failure?.name !== 'RenderingCancelledException' &&
        failure?.name !== 'AbortException'
      )
        setError('Không thể hiển thị trang này. Chọn trang khác hoặc mở lại tài liệu.')
    })
    return () => {
      stopped = true
      render?.cancel()
      textLayer.current?.cancel()
      textLayer.current = null
      if (canvas.current) {
        canvas.current.width = 0
        canvas.current.height = 0
      }
      void work.finally(() => page?.cleanup())
    }
  }, [pdf, number, width])
  return (
    <article
      className="pdf-page"
      data-page={number}
      data-ready={ready}
      aria-label={`Trang PDF ${number}`}
      style={{ width, minHeight: height }}
    >
      {!ready && !error && <span className="pdf-page-loading">Đang hiển thị trang {number}…</span>}
      {error && <p role="alert">{error}</p>}
      <div className="pdf-page-surface" style={{ width, height }}>
        <canvas ref={canvas} aria-label={`Trang ${number}`} />
        <div ref={layer} className="textLayer" />
      </div>
      {ready && (
        <details className="pdf-text">
          <summary>Đọc văn bản của trang</summary>
          <p>
            {text || 'Trang này không có lớp văn bản. Có thể là ảnh/scan; StudyHub chưa có OCR.'}
          </p>
        </details>
      )}
    </article>
  )
}

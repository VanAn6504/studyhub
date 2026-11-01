import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import type { LearningEventInput } from './learningTypes'
import PdfPage from './pdf/PdfPage'
import { foldText, preferredMode, savedPosition, storeMode, storePosition } from './pdf/readerState'
import type { ReadingMode, ReadingPosition, ReadingSession } from './pdf/readerState'
import './pdf/reader.css'

GlobalWorkerOptions.workerSrc = workerUrl
type Size = { width: number; height: number }
type Outline = Awaited<ReturnType<PDFDocumentProxy['getOutline']>>
type Hit = { page: number; snippet: string; ordinal: number }
const GAP = 34

export default function PdfViewer({
  runId,
  versionId,
  title,
  initialPage = 1,
  teacherPreview = false,
  onEvent,
  onPosition,
  onClose,
  userId = 'preview',
  documentType = 'lecture',
  readingSession,
  backLabel = 'Đóng tài liệu',
  suspended = false,
}: {
  runId?: string
  versionId: string
  title: string
  initialPage?: number
  teacherPreview?: boolean
  onEvent?: (event: LearningEventInput) => void
  onPosition?: (page: number) => void
  onClose: () => void
  userId?: string
  documentType?: string
  readingSession?: ReadingSession
  backLabel?: string
  suspended?: boolean
}) {
  const scope = `${userId}:${teacherPreview ? 'preview' : runId}`
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null),
    [sizes, setSizes] = useState<Size[]>([])
  const [page, setPage] = useState(initialPage),
    [pageInput, setPageInput] = useState(String(initialPage))
  const [mode, setMode] = useState<ReadingMode>(() =>
    preferredMode(`${scope}:${documentType}`, documentType === 'lecture' ? 'single' : 'continuous'),
  )
  const [zoom, setZoom] = useState<'width' | 'page' | number>(mode === 'single' ? 'page' : 'width'),
    [focus, setFocus] = useState(false)
  const [box, setBox] = useState({ width: 700, height: 650, top: 0 }),
    [outline, setOutline] = useState<Outline>([])
  const [navigation, setNavigation] = useState(false),
    [pageList, setPageList] = useState(0),
    [error, setError] = useState('')
  const [searchOpen, setSearchOpen] = useState(false),
    [query, setQuery] = useState(''),
    [searched, setSearched] = useState('')
  const [hits, setHits] = useState<Hit[]>([]),
    [hit, setHit] = useState(0),
    [searching, setSearching] = useState(0)
  const [searchDone, setSearchDone] = useState(false),
    [searchError, setSearchError] = useState('')
  const root = useRef<HTMLElement>(null),
    scroll = useRef<HTMLDivElement>(null)
  const pageNow = useRef(initialPage),
    incomingPage = useRef(initialPage),
    anchor = useRef<ReadingPosition>({ page: initialPage, fraction: 0 })
  const localSession = useRef<ReadingSession>({
    id: crypto.randomUUID(),
    opened: false,
    lastPage: 0,
  })
  const session = readingSession || localSession.current
  const callbacks = useRef({ onEvent, onPosition, teacherPreview, suspended })
  callbacks.current = { onEvent, onPosition, teacherPreview, suspended }
  const searchToken = useRef(0),
    searchCache = useRef(new Map<number, string>()),
    loaded = useRef(false),
    saveTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [readyTick, setReadyTick] = useState(0)
  const reportedPositions = useRef(new Set<number>())
  const focusedHit = useRef('')
  useEffect(() => {
    if (!hits.length || searching || !scroll.current) return
    const key = `${searched}:${hit}:${hits[hit].page}`
    if (focusedHit.current === key) return
    const match = scroll.current.querySelector<HTMLElement>(
      `.pdf-page[data-page="${hits[hit].page}"] .pdf-match-current`,
    )
    if (!match) return
    focusedHit.current = key
    const rect = match.getBoundingClientRect(),
      viewport = scroll.current.getBoundingClientRect()
    scroll.current.scrollTop += rect.top - viewport.top - viewport.height * 0.3
  }, [hits, hit, searched, searching, readyTick])
  const ready = useCallback(() => setReadyTick((value) => value + 1), [])

  useEffect(() => {
    let stopped = false
    const task = getDocument({
      url: teacherPreview
        ? `/api/v1/document-versions/${versionId}/content`
        : `/api/v1/course-runs/${runId}/document-versions/${versionId}/content`,
      withCredentials: true,
    })
    task.promise
      .then(async (value) => {
        if (stopped) return
        const first = (await value.getPage(1)).getViewport({ scale: 1 })
        if (stopped) return
        const saved = savedPosition(scope, versionId),
          url = new URL(location.href)
        const explicit =
          url.searchParams.has('page') || new URLSearchParams(url.hash.slice(1)).has('page')
        const initial = Math.max(
          1,
          Math.min(
            value.numPages,
            !explicit && initialPage === 1 && saved ? saved.page : initialPage,
          ),
        )
        anchor.current = { page: initial, fraction: saved?.page === initial ? saved.fraction : 0 }
        pageNow.current = initial
        setPage(initial)
        setPageInput(String(initial))
        setSizes(
          Array.from({ length: value.numPages }, () => ({
            width: first.width,
            height: first.height,
          })),
        )
        setPdf(value)
        loaded.current = true
        void value
          .getOutline()
          .then((items) => {
            if (!stopped) setOutline(items || [])
          })
          .catch(() => {})
        // Metadata only, in bounded batches. Never draw offscreen pages.
        for (let start = 0; start < value.numPages && !stopped; start += 16) {
          const entries = await Promise.all(
            Array.from({ length: Math.min(16, value.numPages - start) }, async (_, i) => {
              try {
                const p = await value.getPage(start + i + 1),
                  v = p.getViewport({ scale: 1 })
                return { width: v.width, height: v.height }
              } catch {
                return { width: first.width, height: first.height }
              }
            }),
          )
          if (!stopped)
            setSizes((old) => {
              const next = [...old]
              entries.forEach((size, i) => (next[start + i] = size))
              return next
            })
          await new Promise((resolve) => setTimeout(resolve, 0))
        }
      })
      .catch(() => {
        if (!stopped)
          setError(
            'Không thể tải PDF: tài liệu có thể đã bị thay, xóa hoặc bạn không còn quyền đọc. Quay về để chọn tài liệu hợp lệ.',
          )
      })
    return () => {
      stopped = true
      searchToken.current++
      void task.destroy()
    }
  }, [runId, versionId, teacherPreview])
  useEffect(() => {
    const target = scroll.current
    if (!target) return
    const observer = new ResizeObserver(() =>
      setBox((old) => ({ ...old, width: target.clientWidth, height: target.clientHeight })),
    )
    observer.observe(target)
    return () => observer.disconnect()
  }, [])
  const layout = useMemo(() => {
    let top = 12
    const entries = sizes.map((size) => {
      const available = Math.max(160, box.width - 28)
      const scale =
        zoom === 'width'
          ? available / size.width
          : zoom === 'page'
            ? Math.min(available / size.width, Math.max(100, box.height - 60) / size.height)
            : zoom
      const item = {
        top,
        width: Math.round(size.width * scale),
        height: Math.round(size.height * scale),
      }
      top += item.height + GAP
      return item
    })
    return { entries, height: top }
  }, [sizes, box.width, box.height, zoom])
  const layoutNow = useRef(layout)
  layoutNow.current = layout
  function locate(top: number) {
    const entries = layoutNow.current.entries
    let low = 0,
      high = entries.length - 1
    while (low < high) {
      const mid = Math.ceil((low + high) / 2)
      if (entries[mid].top <= top) low = mid
      else high = mid - 1
    }
    return low
  }
  function remember(persist = true) {
    if (!loaded.current || !scroll.current) return
    if (mode === 'continuous') {
      const index = locate(scroll.current.scrollTop + 2),
        item = layoutNow.current.entries[index]
      if (item)
        anchor.current = {
          page: index + 1,
          fraction: Math.max(
            0,
            Math.min(0.95, (scroll.current.scrollTop - item.top) / item.height),
          ),
        }
    } else anchor.current = { page: pageNow.current, fraction: 0 }
    if (persist) storePosition(scope, versionId, anchor.current)
  }
  const rememberNow = useRef(remember)
  rememberNow.current = remember
  useLayoutEffect(() => {
    if (!scroll.current || !layout.entries.length) return
    const item = layout.entries[Math.min(anchor.current.page, layout.entries.length) - 1]
    scroll.current.scrollTop =
      mode === 'continuous' ? item.top + item.height * anchor.current.fraction : 0
    setBox((old) => ({ ...old, top: scroll.current!.scrollTop }))
  }, [layout, mode])
  useEffect(
    () => () => {
      clearTimeout(saveTimer.current)
      rememberNow.current()
    },
    [],
  )
  const jump = useCallback(
    (number: number) => {
      const count = layoutNow.current.entries.length
      if (!count) return
      number = Math.max(1, Math.min(count, Math.floor(number)))
      pageNow.current = number
      setPage(number)
      setPageInput(String(number))
      anchor.current = { page: number, fraction: 0 }
      const target = scroll.current
      if (target) {
        target.scrollTop = mode === 'continuous' ? layoutNow.current.entries[number - 1].top : 0
        setBox((old) => ({ ...old, top: target.scrollTop }))
      }
    },
    [mode],
  )
  useEffect(() => {
    if (pdf && initialPage !== incomingPage.current) {
      incomingPage.current = initialPage
      if (!reportedPositions.current.delete(initialPage) && initialPage !== pageNow.current)
        jump(initialPage)
    }
  }, [initialPage, pdf, jump])
  const visible = useMemo(
    () =>
      mode === 'single'
        ? [page - 1]
        : layout.entries.flatMap((item, i) =>
            item.top + item.height >= box.top - box.height && item.top <= box.top + box.height * 2
              ? [i]
              : [],
          ),
    [layout, box.top, box.height, mode, page],
  )

  // Half of the smaller of page/reader viewport must remain visible500ms.
  // Preload and rerender never count; no new event until active page changes.
  useEffect(() => {
    const target = scroll.current
    if (!target || !pdf || suspended) return
    let candidate = 0,
      timer: ReturnType<typeof setTimeout> | undefined,
      frame = 0
    function choose() {
      frame = 0
      const viewport = target!.getBoundingClientRect(),
        upper = Math.max(viewport.top, 0),
        lower = Math.min(viewport.bottom, innerHeight)
      let best = 0,
        bestScore = 0
      if (document.visibilityState === 'visible' && lower > upper)
        target!.querySelectorAll<HTMLElement>('.pdf-page[data-ready="true"]').forEach((node) => {
          const rect = node.querySelector('.pdf-page-surface')!.getBoundingClientRect()
          const shown = Math.max(0, Math.min(rect.bottom, lower) - Math.max(rect.top, upper))
          const horizontal = Math.max(
            0,
            Math.min(rect.right, viewport.right, innerWidth) -
              Math.max(rect.left, viewport.left, 0),
          )
          if (
            shown < Math.min(rect.height, lower - upper) * 0.5 ||
            !horizontal ||
            !node.getClientRects().length
          )
            return
          const score =
            shown -
            Math.abs(
              (Math.max(rect.top, upper) + Math.min(rect.bottom, lower)) / 2 - (upper + lower) / 2,
            ) *
              0.01
          if (score > bestScore) {
            bestScore = score
            best = Number(node.dataset.page)
          }
        })
      if (best === candidate) return
      candidate = best
      clearTimeout(timer)
      if (!best) return
      pageNow.current = best
      setPage(best)
      setPageInput(String(best))
      timer = setTimeout(() => {
        if (
          candidate !== best ||
          document.visibilityState !== 'visible' ||
          callbacks.current.suspended ||
          pageNow.current !== best
        )
          return
        if (callbacks.current.onPosition && incomingPage.current !== best) {
          reportedPositions.current.add(best)
          if (reportedPositions.current.size > 16)
            reportedPositions.current.delete(reportedPositions.current.values().next().value!)
        }
        callbacks.current.onPosition?.(best)
        const { onEvent, teacherPreview } = callbacks.current
        if (!onEvent || teacherPreview) return
        const base = { viewer_session_id: session.id, document_version_id: versionId }
        if (!session.opened) {
          session.opened = true
          onEvent({ ...base, client_event_id: crypto.randomUUID(), type: 'document_open' })
        }
        if (session.lastPage !== best) {
          session.lastPage = best
          onEvent({
            ...base,
            client_event_id: crypto.randomUUID(),
            type: 'page_view',
            pdf_page: best,
          })
        }
      }, 500)
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(choose)
    }
    const observer = new IntersectionObserver(schedule, { threshold: [0, 0.1, 0.5, 1] })
    observer.observe(target)
    target.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    document.addEventListener('visibilitychange', schedule)
    schedule()
    return () => {
      clearTimeout(timer)
      cancelAnimationFrame(frame)
      observer.disconnect()
      target.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      document.removeEventListener('visibilitychange', schedule)
    }
  }, [pdf, readyTick, mode, suspended, versionId, visible.join(',')])
  function switchMode(next: ReadingMode) {
    remember()
    anchor.current = {
      page: pageNow.current,
      fraction: mode === 'continuous' ? anchor.current.fraction : 0,
    }
    setMode(next)
    storeMode(`${scope}:${documentType}`, next)
  }
  function resize(next: typeof zoom) {
    remember()
    setZoom(next)
  }
  function magnify(step: number) {
    const item = layout.entries[pageNow.current - 1],
      size = sizes[pageNow.current - 1]
    resize(
      Math.max(
        0.25,
        Math.min(
          3,
          Number(
            (
              (typeof zoom === 'number' ? zoom : (item?.width || 1) / (size?.width || 1)) + step
            ).toFixed(2),
          ),
        ),
      ),
    )
  }
  async function destination(dest: Outline[number]['dest']) {
    if (!pdf || !dest) return
    try {
      const value = typeof dest === 'string' ? await pdf.getDestination(dest) : dest
      if (!value) return
      jump((typeof value[0] === 'number' ? value[0] : await pdf.getPageIndex(value[0])) + 1)
    } catch {
      setError('Không mở được mục lục này. Hãy nhập số trang PDF.')
    }
  }
  function outlineItems(items: Outline, depth = 0): ReactNode {
    return (
      <ol>
        {items.map((item, i) => (
          <li key={`${depth}:${i}`}>
            {item.dest ? (
              <button className="text-button" onClick={() => void destination(item.dest)}>
                {item.title || 'Mục không tên'}
              </button>
            ) : (
              <span>{item.title}</span>
            )}
            {!!item.items?.length && depth < 12 && outlineItems(item.items, depth + 1)}
          </li>
        ))}
      </ol>
    )
  }
  async function search(event: FormEvent) {
    event.preventDefault()
    if (!pdf || !query.trim()) return
    const token = ++searchToken.current,
      needle = foldText(query.trim()),
      result: Hit[] = []
    setSearched(query.trim())
    focusedHit.current = ''
    setHits([])
    setHit(0)
    setSearchDone(false)
    setSearchError('')
    setSearching(1)
    try {
      for (let n = 1; n <= pdf.numPages; n++) {
        if (token !== searchToken.current) return
        let text = searchCache.current.get(n)
        if (text === undefined) {
          const p = await pdf.getPage(n),
            content = await p.getTextContent()
          text = content.items
            .map((item) => ('str' in item ? item.str : ''))
            .join(' ')
            .slice(0, 100000)
          searchCache.current.set(n, text)
          while (
            [...searchCache.current.values()].reduce((sum, value) => sum + value.length, 0) >
            4_000_000
          )
            searchCache.current.delete(searchCache.current.keys().next().value!)
        }
        const value = foldText(text)
        let ordinal = 0
        for (
          let at = value.indexOf(needle);
          at >= 0 && result.length < 10000;
          at = value.indexOf(needle, at + needle.length)
        )
          result.push({
            page: n,
            ordinal: ordinal++,
            snippet: text.slice(Math.max(0, at - 35), at + needle.length + 70),
          })
        if (token !== searchToken.current) return
        if (n % 4 === 0) {
          setSearching(n)
          await new Promise((resolve) => setTimeout(resolve, 0))
        }
      }
      setHits(result)
      setSearchDone(true)
      if (result.length) jump(result[0].page)
    } catch {
      if (token === searchToken.current)
        setSearchError('Không tìm được toàn bộ tài liệu. Thử lại hoặc kiểm tra quyền đọc.')
    } finally {
      if (token === searchToken.current) setSearching(0)
    }
  }
  function nextHit(step: number) {
    if (hits.length) {
      const index = (hit + step + hits.length) % hits.length
      setHit(index)
      jump(hits[index].page)
    }
  }
  useEffect(() => {
    function escape(event: KeyboardEvent) {
      if (
        event.key === 'Escape' &&
        !(
          event.target instanceof HTMLElement &&
          event.target.closest('input,textarea,select,[contenteditable]')
        )
      ) {
        setFocus(false)
        setNavigation(false)
      }
    }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [])
  return (
    <section
      ref={root}
      className={`pdf-viewer reader-v2 ${focus ? 'is-focused' : ''}`}
      aria-label={`Trình xem ${title}`}
    >
      <div className="pdf-document-heading">
        <strong>{title}</strong>
        <button
          className="text-button"
          onClick={() => {
            remember()
            onClose()
          }}
        >
          {backLabel}
        </button>
      </div>
      <div className="pdf-toolbar" aria-label="Thao tác đọc PDF">
        <button
          className="button button-secondary"
          aria-expanded={navigation}
          onClick={() => {
            setNavigation((v) => !v)
            setPageList(Math.floor((page - 1) / 40))
          }}
        >
          Mục lục
        </button>
        <button
          className="button button-secondary"
          disabled={!pdf || page <= 1}
          onClick={() => jump(page - 1)}
        >
          Trang trước
        </button>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (
              /^\d+$/.test(pageInput) &&
              Number(pageInput) >= 1 &&
              Number(pageInput) <= (pdf?.numPages || 0)
            )
              jump(Number(pageInput))
            else setPageInput(String(page))
          }}
        >
          <label>
            Trang{' '}
            <input
              aria-label="Trang PDF"
              inputMode="numeric"
              type="text"
              value={pageInput}
              onChange={(e) => setPageInput(e.target.value)}
              onBlur={() => setPageInput(String(pageNow.current))}
            />{' '}
            / {pdf?.numPages || '…'}
          </label>
        </form>
        <button
          className="button button-secondary"
          disabled={!pdf || page >= pdf.numPages}
          onClick={() => jump(page + 1)}
        >
          Trang sau
        </button>
        <label>
          <span className="sr-only">Chế độ đọc</span>
          <select
            aria-label="Chế độ đọc"
            value={mode}
            onChange={(e) => switchMode(e.target.value as ReadingMode)}
          >
            <option value="continuous">Cuộn liên tục</option>
            <option value="single">Từng trang</option>
          </select>
        </label>
        <button
          className="button button-secondary"
          aria-label="Thu nhỏ"
          onClick={() => magnify(-0.15)}
        >
          −
        </button>
        <button
          className="button button-secondary"
          aria-label="Phóng to"
          onClick={() => magnify(0.15)}
        >
          +
        </button>
        <label>
          <span className="sr-only">Độ phóng PDF</span>
          <select
            aria-label="Độ phóng PDF"
            value={typeof zoom === 'number' ? 'custom' : zoom}
            onChange={(e) => resize(e.target.value as 'width' | 'page')}
          >
            <option value="width">Vừa chiều rộng</option>
            <option value="page">Vừa trang</option>
            {typeof zoom === 'number' && <option value="custom">{Math.round(zoom * 100)}%</option>}
          </select>
        </label>
        <button
          className="button button-secondary"
          aria-expanded={searchOpen}
          onClick={() => setSearchOpen((v) => !v)}
        >
          Tìm trong PDF
        </button>
        <button
          className="button button-secondary"
          aria-pressed={focus}
          onClick={() => {
            remember()
            setFocus((v) => !v)
          }}
        >
          {focus ? 'Thoát tập trung' : 'Tập trung'}
        </button>
        {document.fullscreenEnabled && (
          <button
            className="text-button"
            onClick={() => {
              if (document.fullscreenElement) void document.exitFullscreen()
              else
                void root.current
                  ?.requestFullscreen()
                  .catch(() =>
                    setError('Trình duyệt chưa cho phép toàn màn hình. Hãy dùng chế độ tập trung.'),
                  )
            }}
          >
            Toàn màn hình
          </button>
        )}
      </div>
      {searchOpen && (
        <div className="pdf-search">
          <form onSubmit={search}>
            <label>
              Tìm văn bản
              <input
                aria-label="Tìm văn bản trong PDF"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                maxLength={200}
              />
            </label>
            <button className="button button-primary" disabled={!pdf || !query.trim()}>
              Tìm
            </button>
            {!!searching && (
              <button
                type="button"
                className="text-button"
                onClick={() => {
                  searchToken.current++
                  setSearching(0)
                  setSearchDone(false)
                }}
              >
                Dừng tìm
              </button>
            )}
          </form>
          <div role="status">
            {searching
              ? `Đang tìm: ${searching}/${pdf?.numPages} trang…`
              : searchDone
                ? hits.length
                  ? `${hit + 1}/${hits.length} kết quả${hits.length === 10000 ? ' (tối đa 10.000)' : ''} · trang PDF ${hits[hit].page}`
                  : 'Không tìm thấy văn bản. Trang scan/ảnh chưa được OCR.'
                : 'Nhập cụm từ và nhấn Enter hoặc Tìm.'}
          </div>
          {searchError && <p role="alert">{searchError}</p>}
          {!!hits.length && (
            <div className="pdf-search-results">
              <button className="text-button" onClick={() => nextHit(-1)}>
                Kết quả trước
              </button>
              <button className="text-button" onClick={() => nextHit(1)}>
                Kết quả sau
              </button>
              <span>{hits[hit]?.snippet}</span>
            </div>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="notice notice-error">
          {error}
        </p>
      )}
      {!pdf && !error && <p role="status">Đang tải PDF…</p>}
      <div className={`pdf-reader-body ${navigation ? 'has-outline' : ''}`}>
        {navigation && (
          <nav className="pdf-outline" aria-label="Mục lục PDF">
            <p className="muted">Trang PDF từ 1; có thể khác số in trên sách.</p>
            {outline.length ? (
              outlineItems(outline)
            ) : (
              <>
                <p>PDF không có mục lục. Chọn trang:</p>
                <div className="pdf-page-list">
                  {Array.from(
                    { length: Math.min(40, (pdf?.numPages || 0) - pageList * 40) },
                    (_, i) => pageList * 40 + i + 1,
                  ).map((n) => (
                    <button
                      key={n}
                      className="button button-secondary"
                      aria-current={n === page ? 'page' : undefined}
                      onClick={() => jump(n)}
                    >
                      {n}
                    </button>
                  ))}
                </div>
                <div className="workspace-actions">
                  <button
                    className="text-button"
                    disabled={!pageList}
                    onClick={() => setPageList((v) => v - 1)}
                  >
                    Nhóm trước
                  </button>
                  <button
                    className="text-button"
                    disabled={(pageList + 1) * 40 >= (pdf?.numPages || 0)}
                    onClick={() => setPageList((v) => v + 1)}
                  >
                    Nhóm sau
                  </button>
                </div>
              </>
            )}
          </nav>
        )}
        <div
          className="pdf-scroll"
          ref={scroll}
          tabIndex={0}
          aria-label="Vùng đọc PDF"
          onScroll={() => {
            remember(false)
            clearTimeout(saveTimer.current)
            saveTimer.current = setTimeout(() => rememberNow.current(), 300)
            const top = scroll.current!.scrollTop
            setBox((old) => ({ ...old, top }))
          }}
        >
          {pdf && (
            <div
              className={`pdf-track ${mode}`}
              style={{ height: mode === 'continuous' ? layout.height : undefined }}
            >
              {visible.map((index) => {
                const item = layout.entries[index]
                return (
                  item && (
                    <div
                      key={index}
                      className="pdf-page-slot"
                      style={
                        mode === 'continuous'
                          ? { top: item.top, position: 'absolute', minWidth: item.width + 20 }
                          : undefined
                      }
                    >
                      <PdfPage
                        pdf={pdf}
                        number={index + 1}
                        width={item.width}
                        height={item.height}
                        query={searched}
                        selectedMatch={
                          hits[hit]?.page === index + 1 ? hits[hit].ordinal : undefined
                        }
                        onReady={ready}
                      />
                    </div>
                  )
                )
              })}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

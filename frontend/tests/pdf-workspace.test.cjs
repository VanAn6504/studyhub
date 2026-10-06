const assert = require('node:assert/strict')
const { test, before, after } = require('node:test')
const { chromium } = require('playwright')
const fs = require('node:fs/promises')
const path = require('node:path')

const origin = process.env.FRONTEND_URL || 'http://localhost:5173'
let browser
before(async () => {
  browser = await chromium.launch({ headless: true, ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}) })
})
after(async () => { await browser?.close() })

// A generated two-page PDF exercises the real PDF.js viewer and worker.
function fixturePdf() {
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>',
    null,
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>',
    null,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ]
  for (const [index, text] of [[3, 'Row arranges children horizontally.'], [5, 'Column arranges children vertically.']]) {
    const stream = `BT /F1 12 Tf 20 260 Td (${text}) Tj ET\n`
    objects[index] = `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}endstream`
  }
  let pdf = '%PDF-1.4\n'
  const offsets = [0]
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(pdf))
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`
  })
  const xref = Buffer.byteLength(pdf)
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  pdf += offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(pdf)
}

async function workspace(role = 'student', failFirstEvent = false) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await context.newPage()
  const errors = [], requests = [], batches = [], events = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
  const run = { id: 'run-fixture', course_id: 'course-fixture', course_title: 'PDF regression fixture', code: 'RUN_PDF', status: 'active', data_origin: 'real', course_run_start_date: '2026-10-06', timezone: 'Asia/Bangkok' }
  const material = { document_version_id: 'version-fixture', title: 'PDF regression fixture', document_code: 'PDF', version: 1, page_start: 2, page_end: 2, order_index: 1 }
  const topic = { id: 'topic-fixture', code: 'FL01', title: 'Layout', order_index: 1, objectives: ['Read PDF'], prerequisite_topic_ids: [], materials: [material], quiz: { published_version_id: 'quiz-fixture', question_count: 1, pass_percent: 70, min_questions: 1 } }
  const document = { id: 'document-fixture', code: 'PDF', title: 'PDF regression fixture', status: 'published', versions: [{ id: 'version-fixture', version: 1, page_count: 2, status: 'ready' }] }
  const item = { quiz_version_item_id: 'item-fixture', stem: 'Row direction?', options: { A: 'Horizontal', B: 'Vertical' }, selected_option: null }
  let attempt = null, completed = false, eventFailed = false
  const list = items => ({ items, total: items.length, limit: 100, offset: 0 })
  await context.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace('/api/v1', ''), method = request.method()
    requests.push({ path, method })
    let payload
    if (path === '/auth/me') payload = { user: { id: 'user-fixture', role, email: 'fixture@example.com', display_name: 'PDF fixture' }, csrf_token: 'fixture-csrf' }
    else if (path === '/course-runs') payload = list([run])
    else if (path === '/courses') payload = list([{ id: run.course_id, code: 'PDF_FIXTURE', title: run.course_title }])
    else if (path.endsWith('/topics')) payload = list([topic])
    else if (path.endsWith('/question-versions') || path.endsWith('/quiz-versions')) payload = list([])
    else if (path.endsWith('/documents')) payload = list([document])
    else if (path.endsWith('/results')) payload = list(attempt?.status === 'completed' ? [attempt] : [])
    else if (path.endsWith('/report')) payload = list([])
    else if (path.endsWith('/events') && method === 'POST') {
      const batch = request.postDataJSON().events
      batches.push(batch)
      if (failFirstEvent && !eventFailed) {
        eventFailed = true
        await route.fulfill({ status: 503, json: { error: { code: 'FIXTURE_UNAVAILABLE', message: 'Retry fixture' } } })
        return
      }
      for (const event of batch) if (!events.some(old => old.client_event_id === event.client_event_id)) events.push({ ...event, id: event.client_event_id, occurred_at: '2026-10-06T10:00:00Z', data_origin: 'real' })
      payload = { accepted: batch.length }
    } else if (path.endsWith('/events')) payload = { ...list(events.slice(-10)), total: events.length }
    else if (path.endsWith('/learning-path')) {
      const state = { topic_id: topic.id, topic_code: topic.code, title: topic.title, state: completed ? 'mastered' : 'not_assessed', score_percent: completed ? 100 : null, reason: 'no_current_assessment', quiz_version_id: 'quiz-fixture' }
      payload = { revision: completed ? 2 : 1, generated_at: '2026-10-06T10:00:00Z', data_origin: 'real', topic_states: [state], unavailable_topics: [], warnings: [], steps: completed ? [] : [{ ...state, position: 1, materials: [material] }] }
    } else if (path.endsWith('/prediction')) payload = { status: 'not_ready', risk_score: null, cutoff_end_at: '2026-11-16T00:00:00Z', data_origin: 'real' }
    else if (path.endsWith('/chat-sessions')) payload = list([{ id: 'chat-fixture', created_at: '2026-10-06T10:00:00Z' }])
    else if (path.endsWith('/messages')) payload = list([{ id: 'turn-fixture', question: 'Column?', answer: 'Column arranges children vertically.', status: 'answered', created_at: '2026-10-06T10:00:00Z', citations: [{ ...material, chunk_id: 'chunk-fixture', pdf_page: 2, excerpt: 'Column arranges children vertically.' }] }])
    else if (path.endsWith('/content')) {
      await route.fulfill({ contentType: 'application/pdf', body: fixturePdf() })
      return
    } else if (path.endsWith('/attempts') && method === 'POST') {
      attempt = { id: 'attempt-fixture', topic_id: topic.id, quiz_version_id: 'quiz-fixture', status: 'in_progress', answer_revision: 1, started_at: '2026-10-06T10:00:00Z', items: [item] }
      payload = attempt
    } else if (path.endsWith('/answers')) {
      attempt = { ...attempt, answer_revision: 2, items: [{ ...item, selected_option: request.postDataJSON().answers[0]?.selected_option }] }
      payload = attempt
    } else if (path.endsWith('/submit')) {
      completed = true
      attempt = { ...attempt, status: 'completed', score_percent: 100, correct_count: 1, total_questions: 1, passed_for_attempt_version: true, counts_for_current_mastery: true }
      payload = attempt
    } else if (path.endsWith('/rag')) payload = { enabled: false, legacy: false, status: 'unprepared', document_status: 'published', usable_pages: 0, total_pages: 2, counts: { automatic: 0, checked: 0, needs_review: 0, excluded: 0 } }
    else {
      errors.push(`Unexpected API: ${method} ${path}`)
      await route.fulfill({ status: 404, json: { error: { code: 'FIXTURE_NOT_FOUND', message: 'Unexpected fixture request' } } })
      return
    }
    await route.fulfill({ json: payload })
  })
  await page.goto(origin, { waitUntil: 'networkidle' })
  if (role === 'teacher') await page.locator('.run-card').filter({ hasText: 'RUN_PDF' }).click()
  await page.getByRole('button', { name: 'Xem PDF', exact: true }).waitFor()
  await page.waitForLoadState('networkidle')
  return { context, page, errors, requests, batches, events }
}

function countRequests(fixture, suffix) {
  return fixture.requests.filter(request => request.method === 'GET' && request.path.endsWith(suffix)).length
}
async function singlePanels(page, viewer = 0) {
  assert.equal(await page.locator('.guidance-panel').count(), 1, 'Only one learning path panel')
  assert.equal(await page.locator('.chat-panel').count(), 1, 'Only one chatbot panel')
  assert.equal(await page.locator('.pdf-viewer').count(), viewer, 'Only one PDF viewer')
}
async function openPdf(page, button, expectedPage) {
  await button.click()
  const viewer = page.locator('.pdf-viewer')
  await viewer.locator('.pdf-text').waitFor()
  assert.equal(await viewer.getByLabel('Trang PDF', { exact: true }).inputValue(), String(expectedPage))
  await viewer.scrollIntoViewIfNeeded()
  return viewer
}
async function screenshot(page, name) {
  if (!process.env.UI_SCREENSHOT_DIR) return
  const directory = path.resolve(process.env.UI_SCREENSHOT_DIR)
  await fs.mkdir(directory, { recursive: true })
  await page.screenshot({ path: path.join(directory, name), fullPage: true })
}

test('repeated PDF opens and page logs keep a single path/chat and do not reload guidance', { timeout: 120000 }, async () => {
  const f = await workspace()
  try {
    await singlePanels(f.page)
    const beforePath = countRequests(f, '/learning-path'), beforePrediction = countRequests(f, '/prediction')
    const beforeDocs = countRequests(f, '/documents'), beforeResults = countRequests(f, '/results')
    for (let index = 0; index < 8; index++) {
      const eventStart = f.events.length
      const viewer = await openPdf(f.page, f.page.getByRole('button', { name: 'Xem PDF', exact: true }), 1)
      await f.page.waitForFunction(() => !document.querySelector('.pdf-viewer [role="alert"]'))
      await new Promise(resolve => setTimeout(resolve, 750))
      await f.page.waitForLoadState('networkidle')
      await singlePanels(f.page, 1)
      assert.equal(f.events.length - eventStart, 2, 'One open and one first page event per viewer session')
      await viewer.getByRole('button', { name: 'Trang sau', exact: true }).click()
      await viewer.getByText('Column arranges children vertically.', { exact: true }).waitFor({ state: 'attached' })
      await new Promise(resolve => setTimeout(resolve, 750))
      await f.page.waitForLoadState('networkidle')
      assert.equal(f.events.length - eventStart, 3, 'One event for the next visible page')
      await f.page.getByRole('button', { name: 'Đóng tài liệu', exact: true }).click()
      await singlePanels(f.page)
    }
    for (const suffix of ['/learning-path', '/documents', '/results']) {
      const expected = { '/learning-path': beforePath, '/documents': beforeDocs, '/results': beforeResults }[suffix]
      assert.equal(countRequests(f, suffix), expected, `PDF logs must not reload ${suffix}`)
    }
    const eventGets = countRequests(f, '/events')
    assert.ok(eventGets > 1, 'Log list still updates')
    assert.ok(countRequests(f, '/prediction') > beforePrediction, 'Activity still invalidates risk data independently of the path')
    await f.page.getByText(`Log học tập của tôi (${f.events.length} sự kiện)`, { exact: true }).waitFor()
    await openPdf(f.page, f.page.locator('.guidance-panel').getByRole('button', { name: 'Đọc PDF · trang 2–2', exact: true }), 2)
    await singlePanels(f.page, 1)
    await f.page.getByRole('button', { name: 'Đóng tài liệu', exact: true }).click()
    await openPdf(f.page, f.page.locator('.chat-panel').getByRole('button', { name: 'PDF · bản 1 · trang 2', exact: true }), 2)
    await singlePanels(f.page, 1)
    await screenshot(f.page, 'pdf-workspace-desktop.png')
    await f.page.setViewportSize({ width: 390, height: 844 })
    assert.ok(await f.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No mobile overflow')
    await screenshot(f.page, 'pdf-workspace-mobile.png')
    assert.deepEqual(f.errors, [])
  } finally { await f.context.close() }
})

test('event retry preserves IDs; explicit refresh and quiz submission still update the path', { timeout: 60000 }, async () => {
  const f = await workspace('student', true)
  try {
    const pathBefore = countRequests(f, '/learning-path')
    await openPdf(f.page, f.page.getByRole('button', { name: 'Xem PDF', exact: true }), 1)
    await f.page.getByRole('button', { name: 'Gửi lại log', exact: true }).waitFor()
    await f.page.getByRole('button', { name: 'Gửi lại log', exact: true }).click()
    await f.page.waitForLoadState('networkidle')
    assert.equal(f.batches[1][0].client_event_id, f.batches[0][0].client_event_id)
    assert.equal(f.events.length, 2)
    assert.equal(countRequests(f, '/learning-path'), pathBefore)
    await f.page.getByRole('button', { name: 'Đóng tài liệu', exact: true }).click()
    await f.page.getByRole('button', { name: 'Cập nhật lộ trình', exact: true }).click()
    await f.page.waitForLoadState('networkidle')
    assert.equal(countRequests(f, '/learning-path'), pathBefore + 1)
    await f.page.getByRole('button', { name: 'Bắt đầu / tiếp tục quiz', exact: true }).click()
    await f.page.getByRole('radio').first().check()
    await f.page.getByRole('button', { name: 'Nộp và xem kết quả', exact: true }).click()
    await f.page.locator('.guidance-panel').getByText('FL01 · Đã đạt 100.0%', { exact: true }).waitFor()
    await singlePanels(f.page)
    assert.ok(countRequests(f, '/learning-path') > pathBefore + 1)
    // The deliberately failed HTTP request may emit one resource error; React errors remain forbidden.
    assert.deepEqual(f.errors.filter(error => !error.includes('503 (Service Unavailable)')), [])
  } finally { await f.context.close() }
})

test('teacher PDF viewing keeps RAG controls and does not write student events', { timeout: 60000 }, async () => {
  const f = await workspace('teacher')
  try {
    for (let index = 0; index < 3; index++) {
      await openPdf(f.page, f.page.getByRole('button', { name: 'Xem PDF', exact: true }), 1)
      assert.equal(await f.page.locator('.guidance-panel').count(), 0)
      assert.equal(await f.page.locator('.rag-document').count(), 1)
      await f.page.getByRole('button', { name: 'Đóng tài liệu', exact: true }).click()
    }
    assert.equal(f.batches.length, 0)
    assert.deepEqual(f.errors, [])
  } finally { await f.context.close() }
})

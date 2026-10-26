const assert = require('node:assert/strict')
const { test, before, after } = require('node:test')
const { chromium } = require('playwright')
const fs = require('node:fs/promises')
const path = require('node:path')

const origin = process.env.FRONTEND_URL || 'http://localhost:5173'
let browser
before(async () => {
  browser = await chromium.launch({
    headless: true,
    ...(process.env.PLAYWRIGHT_CHANNEL ? { channel: process.env.PLAYWRIGHT_CHANNEL } : {}),
  })
})
after(async () => {
  await browser?.close()
})

const { fixturePdf } = require('./fixtures.cjs')

async function workspace(role = 'student', failFirstEvent = false) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await context.newPage()
  const errors = [],
    requests = [],
    batches = [],
    events = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  const run = {
    id: 'run-fixture',
    course_id: 'course-fixture',
    course_title: 'PDF regression fixture',
    code: 'RUN_PDF',
    status: 'active',
    data_origin: 'real',
    course_run_start_date: '2026-10-06',
    timezone: 'Asia/Bangkok',
  }
  const material = {
    document_version_id: 'version-fixture',
    title: 'PDF regression fixture',
    document_code: 'PDF',
    version: 1,
    page_start: 2,
    page_end: 2,
    order_index: 1,
  }
  const topic = {
    id: 'topic-fixture',
    code: 'FL01',
    title: 'Layout',
    order_index: 1,
    objectives: ['Read PDF'],
    prerequisite_topic_ids: [],
    materials: [material],
    quiz: {
      published_version_id: 'quiz-fixture',
      question_count: 1,
      pass_percent: 70,
      min_questions: 1,
    },
  }
  const document = {
    id: 'document-fixture',
    code: 'PDF',
    title: 'PDF regression fixture',
    status: 'published',
    versions: [{ id: 'version-fixture', version: 1, page_count: 2, status: 'ready' }],
  }
  const item = {
    quiz_version_item_id: 'item-fixture',
    stem: 'Row direction?',
    options: { A: 'Horizontal', B: 'Vertical' },
    selected_option: null,
  }
  let attempt = null,
    completed = false,
    eventFailed = false
  let deleted = false
  const questions = [],
    quizzes = []
  const list = (items) => ({ items, total: items.length, limit: 100, offset: 0 })
  await context.route('**/api/**', async (route) => {
    const request = route.request(),
      url = new URL(request.url()),
      path = url.pathname.replace('/api/v1', ''),
      method = request.method()
    requests.push({ path, method })
    let payload
    if (path === '/auth/me')
      payload = {
        user: {
          id: 'user-fixture',
          role,
          email: 'fixture@example.com',
          display_name: 'PDF fixture',
        },
        csrf_token: 'fixture-csrf',
      }
    else if (path === '/me/resume' && method === 'PUT') {
      payload = {
        ...request.postDataJSON(),
        course_id: run.course_id,
        course_title: run.course_title,
        run_code: run.code,
        updated_at: '2026-10-26T10:00:00Z',
        notice: null,
      }
    } else if (path === '/auth/logout') {
      await route.fulfill({ status: 204 })
      return
    } else if (path === '/course-runs') payload = list([run])
    else if (path === '/courses')
      payload = list([{ id: run.course_id, code: 'PDF_FIXTURE', title: run.course_title }])
    else if (path.endsWith('/topics')) payload = list([topic])
    else if (path === '/documents/document-fixture' && method === 'PATCH') {
      const patch = request.postDataJSON()
      if (patch.code === 'DUPLICATE') {
        await route.fulfill({
          status: 409,
          json: { error: { code: 'DOCUMENT_CODE_EXISTS', message: 'Mã tài liệu đã tồn tại.' } },
        })
        return
      }
      Object.assign(document, patch)
      payload = document
    } else if (path === '/documents/document-fixture' && method === 'DELETE') {
      deleted = true
      await route.fulfill({ status: 204 })
      return
    } else if (path === '/documents/document-fixture/file' && method === 'PUT') {
      const multipart = request.postDataBuffer().toString('latin1')
      if (!multipart.includes('%PDF-')) {
        await route.fulfill({
          status: 415,
          json: { error: { code: 'PDF_REQUIRED', message: 'Tệp tải lên phải là PDF.' } },
        })
        return
      }
      document.status = 'draft'
      document.versions = [
        {
          id: 'version-replacement',
          version: 2,
          page_count: 2,
          status: 'ready',
          original_filename: 'replacement.pdf',
        },
      ]
      payload = document
    } else if (path.endsWith('/questions') && method === 'POST') {
      const body = request.postDataJSON()
      payload = { ...body, id: `qv-${body.code}`, question_id: `q-${body.code}`, version: 1 }
      questions.push(payload)
    } else if (path.endsWith('/question-versions')) payload = list(questions)
    else if (path.endsWith('/quiz-versions') && method === 'POST') {
      const ids = request.postDataJSON().question_version_ids
      payload = {
        id: `quiz-${quizzes.length + 1}`,
        version: quizzes.length + 1,
        status: 'draft',
        question_count: ids.length,
        items: questions.filter((q) => ids.includes(q.id)),
      }
      quizzes.push(payload)
    } else if (path.endsWith('/quiz-versions')) payload = list(quizzes)
    else if (path.startsWith('/quiz-versions/')) payload = quizzes.find((q) => path.endsWith(q.id))
    else if (path.endsWith('/documents')) payload = list(deleted ? [] : [document])
    else if (path.endsWith('/results'))
      payload = list(attempt?.status === 'completed' ? [attempt] : [])
    else if (path.endsWith('/report'))
      payload = list([
        {
          enrollment_id: 'enrollment-fixture',
          display_name: 'Report student',
          student_email: 'report@example.com',
          enrollment_status: 'active',
          page_views: requests.filter((r) => r.path.endsWith('/report')).length,
          attempt_count: 0,
          learning_path: { revision: 1, steps: [], topic_states: [] },
          latest_results: [],
        },
      ])
    else if (path.endsWith('/events') && method === 'POST') {
      const batch = request.postDataJSON().events
      batches.push(batch)
      if (failFirstEvent && !eventFailed) {
        eventFailed = true
        await route.fulfill({
          status: 503,
          json: { error: { code: 'FIXTURE_UNAVAILABLE', message: 'Retry fixture' } },
        })
        return
      }
      for (const event of batch)
        if (!events.some((old) => old.client_event_id === event.client_event_id))
          events.push({
            ...event,
            id: event.client_event_id,
            occurred_at: '2026-10-06T10:00:00Z',
            data_origin: 'real',
          })
      payload = { accepted: batch.length }
    } else if (path.endsWith('/events'))
      payload = { ...list(events.slice(-10)), total: events.length }
    else if (path.endsWith('/learning-path')) {
      const state = {
        topic_id: topic.id,
        topic_code: topic.code,
        title: topic.title,
        state: completed ? 'mastered' : 'not_assessed',
        score_percent: completed ? 100 : null,
        reason: 'no_current_assessment',
        quiz_version_id: 'quiz-fixture',
      }
      payload = {
        revision: completed ? 2 : 1,
        generated_at: '2026-10-06T10:00:00Z',
        data_origin: 'real',
        topic_states: [state],
        unavailable_topics: [],
        warnings: [],
        steps: completed ? [] : [{ ...state, position: 1, materials: [material] }],
      }
    } else if (path.endsWith('/prediction'))
      payload = {
        status: 'not_ready',
        risk_score: null,
        cutoff_end_at: '2026-11-16T00:00:00Z',
        data_origin: 'real',
      }
    else if (path.endsWith('/chat-sessions'))
      payload = list([{ id: 'chat-fixture', created_at: '2026-10-06T10:00:00Z' }])
    else if (path.endsWith('/messages'))
      payload = list([
        {
          id: 'turn-fixture',
          question: 'Column?',
          answer: 'Column arranges children vertically.',
          status: 'answered',
          created_at: '2026-10-06T10:00:00Z',
          citations: [
            {
              ...material,
              chunk_id: 'chunk-fixture',
              pdf_page: 2,
              excerpt: 'Column arranges children vertically.',
            },
          ],
        },
      ])
    else if (path.endsWith('/content')) {
      await route.fulfill({ contentType: 'application/pdf', body: fixturePdf() })
      return
    } else if (path.endsWith('/attempts') && method === 'POST') {
      attempt = {
        id: 'attempt-fixture',
        topic_id: topic.id,
        quiz_version_id: 'quiz-fixture',
        status: 'in_progress',
        answer_revision: 1,
        started_at: '2026-10-06T10:00:00Z',
        items: [item],
      }
      payload = attempt
    } else if (path.endsWith('/answers')) {
      attempt = {
        ...attempt,
        answer_revision: 2,
        items: [{ ...item, selected_option: request.postDataJSON().answers[0]?.selected_option }],
      }
      payload = attempt
    } else if (path.endsWith('/submit')) {
      completed = true
      attempt = {
        ...attempt,
        status: 'completed',
        score_percent: 100,
        correct_count: 1,
        total_questions: 1,
        passed_for_attempt_version: true,
        counts_for_current_mastery: true,
      }
      payload = attempt
    } else if (path.endsWith('/rag'))
      payload = {
        enabled: false,
        legacy: false,
        status: 'unprepared',
        document_status: 'published',
        usable_pages: 0,
        total_pages: 2,
        counts: { automatic: 0, checked: 0, needs_review: 0, excluded: 0 },
      }
    else {
      errors.push(`Unexpected API: ${method} ${path}`)
      await route.fulfill({
        status: 404,
        json: { error: { code: 'FIXTURE_NOT_FOUND', message: 'Unexpected fixture request' } },
      })
      return
    }
    await route.fulfill({ json: payload })
  })
  await page.goto(origin + '/workspace?view=home', { waitUntil: 'networkidle' })
  await page
    .getByRole('button', {
      name: role === 'teacher' ? 'Quản lý học phần' : 'Vào học phần',
      exact: true,
    })
    .click()
  if (role === 'teacher') {
    await page.getByRole('button', { name: 'Tài liệu', exact: true }).click()
    await page.getByRole('button', { name: 'Mở tài liệu', exact: true }).click()
  } else {
    assert.equal(
      await page
        .locator('.workspace-card.topic-card')
        .evaluate((el) => getComputedStyle(el).display),
      'block',
      'Topic contents are stacked, not squeezed into one row',
    )
    assert.ok(
      await page
        .getByRole('button', { name: 'Vào học', exact: true })
        .evaluate((el) => el.getBoundingClientRect().height < 70),
      'Topic action remains readable',
    )
    await page.getByRole('button', { name: 'Lộ trình & tiến độ', exact: true }).click()
    await page.locator('.guidance-panel').waitFor()
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: 'Nội dung học phần', exact: true }).click()
    await page.getByRole('button', { name: 'Hỏi trợ giảng', exact: true }).click()
    await page.locator('.chat-panel').waitFor()
    await page.getByRole('button', { name: 'Đóng trợ giảng', exact: true }).click()
    await page.getByRole('button', { name: 'Vào học', exact: true }).click()
  }
  await page.waitForLoadState('networkidle')
  return { context, page, errors, requests, batches, events, questions, quizzes }
}

function countRequests(fixture, suffix) {
  return fixture.requests.filter(
    (request) => request.method === 'GET' && request.path.endsWith(suffix),
  ).length
}

test(
  'teacher edits metadata, replaces a PDF after validation and permanently deletes with cancellation',
  { timeout: 60000 },
  async () => {
    const f = await workspace('teacher'),
      p = f.page
    try {
      await p.getByRole('button', { name: 'Chỉnh sửa thông tin', exact: true }).click()
      await p.getByLabel('Mã tài liệu', { exact: true }).fill('DUPLICATE')
      await p.getByLabel('Tên tài liệu', { exact: true }).fill('Updated PDF title')
      await p.getByRole('button', { name: 'Lưu thông tin', exact: true }).click()
      await p.getByText('Mã tài liệu đã tồn tại.', { exact: true }).waitFor()
      assert.equal(
        await p.getByLabel('Tên tài liệu', { exact: true }).inputValue(),
        'Updated PDF title',
      )
      await p.getByLabel('Mã tài liệu', { exact: true }).fill('UPDATED')
      await p.getByRole('button', { name: 'Lưu thông tin', exact: true }).click()
      await p.getByRole('heading', { name: 'Updated PDF title', exact: true }).waitFor()
      await p.getByRole('button', { name: 'Chỉnh sửa thông tin', exact: true }).click()
      await p.getByLabel('Thay file PDF — xóa file cũ', { exact: true }).check()
      await p.getByLabel('PDF thay thế', { exact: true }).setInputFiles({
        name: 'bad.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('invalid PDF'),
      })
      await p.getByRole('button', { name: 'Lưu thông tin', exact: true }).click()
      await p.getByText('Tệp tải lên phải là PDF.', { exact: true }).waitFor()
      assert.equal(
        await p.getByLabel('Tên tài liệu', { exact: true }).inputValue(),
        'Updated PDF title',
      )
      await p.getByLabel('PDF thay thế', { exact: true }).setInputFiles({
        name: 'replacement.pdf',
        mimeType: 'application/pdf',
        buffer: fixturePdf(),
      })
      await p.getByRole('button', { name: 'Lưu thông tin', exact: true }).click()
      await p
        .getByText(
          'Đã thay PDF và xóa file cũ. Kiểm tra, gắn vào chủ đề và công bố lại tài liệu.',
          { exact: true },
        )
        .waitFor()
      assert.equal(
        await p.getByRole('button', { name: 'Thùng rác tài liệu', exact: true }).count(),
        0,
      )
      await screenshot(p, 'document-replaced-desktop.png')
      await p.setViewportSize({ width: 390, height: 844 })
      assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await screenshot(p, 'document-replaced-mobile.png')
      p.once('dialog', (d) => d.dismiss())
      await p.getByRole('button', { name: 'Xóa tài liệu', exact: true }).click()
      assert.equal(f.requests.filter((r) => r.method === 'DELETE').length, 0)
      p.once('dialog', (d) => {
        assert.match(d.message(), /Xóa vĩnh viễn/)
        return d.accept()
      })
      await p.getByRole('button', { name: 'Xóa tài liệu', exact: true }).click()
      await p.getByText('Đã xóa vĩnh viễn tài liệu và các file PDF.', { exact: true }).waitFor()
      assert.equal(await p.getByRole('button', { name: 'Mở tài liệu', exact: true }).count(), 0)
      assert.equal(
        await p.getByRole('button', { name: 'Khôi phục tài liệu', exact: true }).count(),
        0,
      )
      assert.deepEqual(
        f.errors.filter(
          (e) => !e.includes('409 (Conflict)') && !e.includes('415 (Unsupported Media Type)'),
        ),
        [],
      )
    } finally {
      await f.context.close()
    }
  },
)

test(
  'JSON import selects 20 topic questions, supports 10/20 quiz creation and skips existing codes',
  { timeout: 60000 },
  async () => {
    const f = await workspace('teacher'),
      p = f.page
    try {
      await p.getByRole('button', { name: 'Chủ đề', exact: true }).click()
      await p.getByRole('button', { name: 'Quản lý chủ đề', exact: true }).click()
      await p.getByRole('button', { name: 'Biên soạn quiz', exact: true }).click()
      assert.ok(await p.getByRole('button', { name: 'Chọn 10 câu', exact: true }).isDisabled())
      const items = Array.from({ length: 20 }, (_, i) => ({
        id: `Q${i}`,
        topic_id: 'FL01',
        stem: `Question ${i}`,
        options: { A: 'a', B: 'b', C: 'c', D: 'd' },
        correct_option: 'A',
        explanation: 'Fixture explanation',
        sources: [{ document_id: 'PDF', pdf_page: 1 }],
      }))
      const input = p.getByLabel('Nhập câu hỏi từ quiz_draft.json cho chủ đề đang chọn', {
        exact: true,
      })
      const upload = (questions) =>
        input.setInputFiles({
          name: 'quiz_draft.json',
          mimeType: 'application/json',
          buffer: Buffer.from(JSON.stringify({ questions })),
        })
      await upload([{ ...items[0], sources: [{ document_id: 'MISSING', pdf_page: 1 }] }])
      await p
        .getByText('Hãy upload PDF MISSING và kiểm tra trang nguồn trước.', { exact: true })
        .waitFor()
      assert.equal(f.questions.length, 0)
      // A whole-course file can exceed 100 entries; only this topic is imported.
      const courseFile = [
        ...items,
        ...Array.from({ length: 90 }, (_, i) => ({
          ...items[0],
          id: `OTHER${i}`,
          topic_id: 'OTHER',
        })),
      ]
      await upload(courseFile)
      await p.getByText('Đã chọn 20/20 câu', { exact: true }).waitFor()
      assert.equal(
        await p
          .getByText('Hãy upload PDF MISSING và kiểm tra trang nguồn trước.', { exact: true })
          .count(),
        0,
      )
      assert.equal(f.questions.length, 20)
      await p.getByRole('button', { name: 'Chọn 10 câu', exact: true }).click()
      await p.getByRole('button', { name: 'Tạo quiz nháp (10 câu)', exact: true }).click()
      await p.getByRole('heading', { name: 'Rà soát quiz bản 1', exact: true }).waitFor()
      assert.equal(f.quizzes[0].items.length, 10)
      await p.getByRole('button', { name: 'Chọn 20 câu', exact: true }).click()
      await p.getByRole('button', { name: 'Tạo quiz nháp (20 câu)', exact: true }).click()
      await p.getByRole('heading', { name: 'Rà soát quiz bản 2', exact: true }).waitFor()
      assert.equal(f.quizzes[1].items.length, 20)
      await p.getByRole('button', { name: 'Bỏ chọn tất cả', exact: true }).click()
      assert.ok(
        await p.getByRole('button', { name: 'Tạo quiz nháp (0 câu)', exact: true }).isDisabled(),
      )
      await upload(courseFile)
      await p.getByText('Đã chọn 20/20 câu', { exact: true }).waitFor()
      assert.equal(f.questions.length, 20, 'Re-import must not duplicate questions')
      await screenshot(p, 'quiz-selection-desktop.png')
      assert.deepEqual(f.errors, [])
    } finally {
      await f.context.close()
    }
  },
)
async function singlePanels(page, viewer = 0) {
  assert.equal(await page.locator('.guidance-panel').count(), 1, 'Only one learning path panel')
  assert.equal(await page.locator('.chat-panel').count(), 1, 'Only one chatbot panel')
  assert.equal(await page.locator('.pdf-viewer').count(), viewer, 'Only one PDF viewer')
}
async function openPdf(page, button, expectedPage) {
  await button.click()
  const viewer = page.locator('.pdf-viewer')
  await viewer.locator('.pdf-text').waitFor()
  assert.equal(
    await viewer.getByLabel('Trang PDF', { exact: true }).inputValue(),
    String(expectedPage),
  )
  await viewer.scrollIntoViewIfNeeded()
  return viewer
}
async function screenshot(page, name) {
  if (!process.env.UI_SCREENSHOT_DIR) return
  const directory = path.resolve(process.env.UI_SCREENSHOT_DIR)
  await fs.mkdir(directory, { recursive: true })
  await page.screenshot({ path: path.join(directory, name), fullPage: true })
}

test(
  'repeated PDF opens and page logs keep a single path/chat and do not reload guidance',
  { timeout: 120000 },
  async () => {
    const f = await workspace()
    try {
      await singlePanels(f.page)
      const beforePath = countRequests(f, '/learning-path'),
        beforePrediction = countRequests(f, '/prediction')
      const beforeDocs = countRequests(f, '/documents'),
        beforeResults = countRequests(f, '/results')
      for (let index = 0; index < 8; index++) {
        const eventStart = f.events.length
        const viewer = await openPdf(
          f.page,
          f.page.getByRole('button', { name: 'Đọc tài liệu', exact: true }),
          2,
        )
        await f.page.waitForFunction(() => !document.querySelector('.pdf-viewer [role="alert"]'))
        await new Promise((resolve) => setTimeout(resolve, 750))
        await f.page.waitForLoadState('networkidle')
        await singlePanels(f.page, 1)
        assert.equal(
          f.events.length - eventStart,
          2,
          'One open and one first page event per viewer session',
        )
        await viewer.getByRole('button', { name: 'Trang trước', exact: true }).click()
        await viewer
          .getByText('Row arranges children horizontally.', { exact: true })
          .waitFor({ state: 'attached' })
        await new Promise((resolve) => setTimeout(resolve, 750))
        await f.page.waitForLoadState('networkidle')
        assert.equal(f.events.length - eventStart, 3, 'One event for the next visible page')
        await f.page.getByRole('button', { name: 'Đóng tài liệu', exact: true }).click()
        await singlePanels(f.page)
      }
      for (const suffix of ['/learning-path', '/documents', '/results']) {
        const expected = {
          '/learning-path': beforePath,
          '/documents': beforeDocs,
          '/results': beforeResults,
        }[suffix]
        assert.equal(countRequests(f, suffix), expected, `PDF logs must not reload ${suffix}`)
      }
      const eventGets = countRequests(f, '/events')
      assert.ok(eventGets > 1, 'Log list still updates')
      assert.ok(
        countRequests(f, '/prediction') > beforePrediction,
        'Activity still invalidates risk data independently of the path',
      )
      await f.page.getByRole('button', { name: 'Kết quả', exact: true }).click()
      await f.page
        .getByText(`Log học tập của tôi (${f.events.length} sự kiện)`, { exact: true })
        .waitFor()
      await f.page.getByRole('button', { name: 'Lộ trình & tiến độ', exact: true }).click()
      await openPdf(
        f.page,
        f.page
          .locator('.guidance-panel')
          .getByRole('button', { name: 'Đọc PDF · trang 2–2', exact: true }),
        2,
      )
      await singlePanels(f.page, 1)
      await f.page.getByRole('button', { name: 'Đóng tài liệu', exact: true }).click()
      await f.page.getByRole('button', { name: 'Hỏi trợ giảng', exact: true }).click()
      await openPdf(
        f.page,
        f.page
          .locator('.chat-panel')
          .getByRole('button', { name: 'PDF · bản 1 · trang 2', exact: true }),
        2,
      )
      await singlePanels(f.page, 1)
      await screenshot(f.page, 'pdf-workspace-desktop.png')
      await f.page.setViewportSize({ width: 390, height: 844 })
      assert.ok(
        await f.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        'No mobile overflow',
      )
      await screenshot(f.page, 'pdf-workspace-mobile.png')
      assert.deepEqual(f.errors, [])
    } finally {
      await f.context.close()
    }
  },
)

test(
  'event retry preserves IDs; explicit refresh and quiz submission still update the path',
  { timeout: 60000 },
  async () => {
    const f = await workspace('student', true)
    try {
      const pathBefore = countRequests(f, '/learning-path')
      await openPdf(f.page, f.page.getByRole('button', { name: 'Đọc tài liệu', exact: true }), 2)
      await f.page.getByRole('button', { name: 'Gửi lại log', exact: true }).waitFor()
      await f.page.getByRole('button', { name: 'Gửi lại log', exact: true }).click()
      await f.page.waitForLoadState('networkidle')
      assert.equal(f.batches[1][0].client_event_id, f.batches[0][0].client_event_id)
      assert.equal(f.events.length, 2)
      assert.equal(countRequests(f, '/learning-path'), pathBefore)
      await f.page.getByRole('button', { name: 'Đóng tài liệu', exact: true }).click()
      await f.page.getByRole('button', { name: 'Lộ trình & tiến độ', exact: true }).click()
      await f.page.getByRole('button', { name: 'Cập nhật lộ trình', exact: true }).click()
      await f.page.waitForLoadState('networkidle')
      assert.equal(countRequests(f, '/learning-path'), pathBefore + 1)
      await f.page.getByRole('button', { name: 'Nội dung học phần', exact: true }).click()
      await f.page.getByRole('button', { name: 'Vào học', exact: true }).click()
      await f.page.getByRole('button', { name: 'Làm quiz', exact: true }).click()
      await f.page.getByRole('button', { name: 'Bắt đầu / tiếp tục quiz', exact: true }).click()
      await f.page.getByRole('radio').first().check()
      await f.page.getByRole('button', { name: 'Nộp và xem kết quả', exact: true }).click()
      await f.page.getByRole('button', { name: 'Lộ trình & tiến độ', exact: true }).click()
      await f.page
        .locator('.guidance-panel')
        .getByText('FL01 · Đã đạt 100.0%', { exact: true })
        .waitFor()
      await singlePanels(f.page)
      assert.ok(countRequests(f, '/learning-path') > pathBefore + 1)
      // The deliberately failed HTTP request may emit one resource error; React errors remain forbidden.
      assert.deepEqual(
        f.errors.filter((error) => !error.includes('503 (Service Unavailable)')),
        [],
      )
    } finally {
      await f.context.close()
    }
  },
)

test(
  'teacher PDF viewing keeps RAG controls and does not write student events',
  { timeout: 60000 },
  async () => {
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
    } finally {
      await f.context.close()
    }
  },
)

test(
  'quiz choices survive PDF navigation and browser Back; logout can be cancelled',
  { timeout: 60000 },
  async () => {
    const f = await workspace()
    try {
      await f.page.getByRole('button', { name: 'Làm quiz', exact: true }).click()
      await f.page.getByRole('button', { name: 'Bắt đầu / tiếp tục quiz', exact: true }).click()
      await f.page.getByRole('radio').first().check()
      const reject = (dialog) => dialog.dismiss()
      f.page.on('dialog', reject)
      await f.page.getByRole('button', { name: 'Đăng xuất', exact: true }).click()
      assert.equal(await f.page.getByRole('radio').first().isChecked(), true)
      assert.equal(f.requests.filter((r) => r.path === '/auth/logout').length, 0)
      f.page.off('dialog', reject)
      await f.page.getByRole('button', { name: 'Về chủ đề', exact: true }).click()
      await openPdf(f.page, f.page.getByRole('button', { name: 'Đọc tài liệu', exact: true }), 2)
      await f.page.goBack()
      await f.page.getByRole('button', { name: 'Làm quiz', exact: true }).click()
      assert.equal(
        await f.page.getByRole('radio').first().isChecked(),
        true,
        'Unsaved choice is retained within the course/topic',
      )
      await f.page.getByRole('button', { name: 'Lộ trình & tiến độ', exact: true }).click()
      await f.page.getByRole('button', { name: 'Nội dung học phần', exact: true }).click()
      await f.page.getByRole('button', { name: 'Vào học', exact: true }).click()
      await f.page.getByRole('button', { name: 'Làm quiz', exact: true }).click()
      assert.equal(await f.page.getByRole('radio').first().isChecked(), true)
      await f.page.getByRole('button', { name: 'Kết quả', exact: true }).click()
      await f.page.getByRole('button', { name: 'Làm tiếp', exact: true }).click()
      await f.page
        .getByText('Hãy lưu hoặc đóng bài đang làm trước khi mở bài khác từ lịch sử.', {
          exact: true,
        })
        .waitFor()
      await f.page.getByRole('button', { name: 'Nội dung học phần', exact: true }).click()
      await f.page.getByRole('button', { name: 'Vào học', exact: true }).click()
      await f.page.getByRole('button', { name: 'Làm quiz', exact: true }).click()
      assert.equal(await f.page.getByRole('radio').first().isChecked(), true)
      f.page.once('dialog', (dialog) => dialog.accept())
      await f.page.getByRole('button', { name: 'Đăng xuất', exact: true }).click()
      await f.page.getByRole('button', { name: 'Đăng nhập', exact: true }).waitFor()
      assert.ok(f.requests.some((r) => r.method === 'POST' && r.path === '/auth/logout'))
      assert.deepEqual(f.errors, [])
    } finally {
      await f.context.close()
    }
  },
)

test(
  'teacher question draft stays when leaving the quiz editor within a topic',
  { timeout: 60000 },
  async () => {
    const f = await workspace('teacher')
    try {
      await f.page.getByRole('button', { name: 'Chủ đề', exact: true }).click()
      await f.page.getByRole('button', { name: 'Quản lý chủ đề', exact: true }).click()
      await f.page.getByRole('button', { name: 'Biên soạn quiz', exact: true }).click()
      await f.page.getByText('Thêm câu hỏi', { exact: true }).click()
      await f.page.getByLabel('Câu hỏi', { exact: true }).fill('Câu hỏi đang biên soạn')
      await f.page.getByRole('button', { name: 'Về chủ đề', exact: true }).click()
      await f.page.getByRole('button', { name: 'Biên soạn quiz', exact: true }).click()
      assert.equal(
        await f.page.getByLabel('Câu hỏi', { exact: true }).inputValue(),
        'Câu hỏi đang biên soạn',
      )
      f.page.once('dialog', (dialog) => dialog.dismiss())
      await f.page.getByRole('button', { name: 'Đăng xuất', exact: true }).click()
      assert.equal(
        await f.page.getByLabel('Câu hỏi', { exact: true }).inputValue(),
        'Câu hỏi đang biên soạn',
      )
      assert.deepEqual(f.errors, [])
    } finally {
      await f.context.close()
    }
  },
)

test(
  'teacher report refreshes when reopened after learning activity',
  { timeout: 60000 },
  async () => {
    const f = await workspace('teacher')
    try {
      await f.page.getByRole('button', { name: 'Kết quả', exact: true }).click()
      await f.page.getByLabel('Lớp học', { exact: true }).selectOption('run-fixture')
      await f.page.getByText('1 lượt xem trang · 0 bài làm', { exact: true }).waitFor()
      await f.page.getByRole('button', { name: 'Chủ đề', exact: true }).click()
      await f.page.getByRole('button', { name: 'Kết quả', exact: true }).click()
      await f.page.getByText('2 lượt xem trang · 0 bài làm', { exact: true }).waitFor()
      assert.equal(countRequests(f, '/report'), 2)
      assert.deepEqual(f.errors, [])
    } finally {
      await f.context.close()
    }
  },
)

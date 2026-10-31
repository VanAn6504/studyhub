const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path')
const {test,before,after}=require('node:test'),{chromium}=require('playwright')
let browser,teacher,student,env,origin,course,run,topics,book,scan
const errors=[],output=process.env.UI_SCREENSHOT_DIR
before(async()=>{
  env=JSON.parse(await fs.readFile(process.env.STUDYHUB_WEBSITE_TEST_ENV,'utf8'))
  assert.ok(new URL(env.DATABASE_URL).pathname.endsWith('_test'))
  origin=process.env.FRONTEND_URL;assert.equal(origin,env.ALLOWED_ORIGINS)
  browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{})})
  teacher=await actor();student=await actor()
})
after(async()=>{
  if(browser){let i=0;for(const context of browser.contexts())for(const p of context.pages())await p.screenshot({path:path.join(output,`final-${i++}.png`),fullPage:true}).catch(()=>{})}
  await browser?.close()
})
async function actor(){const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));return{context,page}}
async function api(actor,method,url,body,expected=200){
  const headers={Origin:origin}
  if(method!=='GET'){const me=await actor.context.request.get(origin+'/api/v1/auth/me');assert.equal(me.status(),200);headers['X-CSRF-Token']=(await me.json()).csrf_token}
  const r=await actor.context.request.fetch(origin+'/api/v1'+url,{method,headers,data:body});assert.equal(r.status(),expected,`${method} ${url}`);return r.status()===204?null:r.json()
}
async function login(actor,email,password,next){const p=actor.page;await p.goto(origin+'/login?next='+encodeURIComponent(next),{waitUntil:'networkidle'});await p.getByLabel('Email',{exact:true}).fill(email);await p.getByLabel('Mật khẩu',{exact:true}).fill(password);await p.getByRole('button',{name:'Đăng nhập',exact:true}).click();await p.locator('.site-header').getByRole('button',{name:'Đăng xuất',exact:true}).waitFor()}
async function shot(p,name){await fs.mkdir(output,{recursive:true});await p.screenshot({path:path.join(output,name),fullPage:true})}
async function state(version,terminal=true){const deadline=Date.now()+120000;let s;do{s=await api(teacher,'GET',`/document-versions/${version}/rag`);if(!terminal||!['unprepared','queued','processing'].includes(s.status))return s;await new Promise(resolve=>setTimeout(resolve,200))}while(Date.now()<deadline);throw Error('Worker did not finish: '+s.status)}
function detail(p){return p.locator('article.workspace-document-detail:not([hidden])')}
async function mutate(p,action,method,url){await Promise.all([p.waitForResponse(r=>r.request().method()===method&&r.url().endsWith(url)&&r.ok()),action()])}
async function upload(code,title,kind,file){
 const p=teacher.page
 await p.goto(origin+`/teaching/workspace/${course.id}?view=upload`,{waitUntil:'networkidle'})
 const form=p.locator('form.workspace-form')
 await form.getByLabel('Mã tài liệu (ví dụ CH01)',{exact:true}).fill(code)
 await form.getByLabel('Tên tài liệu',{exact:true}).fill(title)
 await form.getByLabel('Loại tài liệu',{exact:true}).selectOption(kind)
 await form.getByLabel('Tệp PDF · tối đa 100 MiB, 2.000 trang',{exact:true}).setInputFiles(path.join(process.env.RAG_FIXTURE_DIR,file))
 await form.getByRole('button',{name:'Lưu nháp và xem trước',exact:true}).click()
 await p.getByRole('heading',{name:title,exact:true}).waitFor()
 return(await api(teacher,'GET',`/courses/${course.id}/documents?limit=100`)).items.find(d=>d.code===code)
}

test('large textbook through actual Nginx: classify, select chapter range and prepare durable source',{timeout:180000},async()=>{
 await login(teacher,env.BOOTSTRAP_TEACHER_EMAIL,env.BOOTSTRAP_TEACHER_PASSWORD,'/teaching')
 course=(await api(teacher,'GET','/courses')).items[0];run=(await api(teacher,'GET','/course-runs')).items[0];topics=(await api(teacher,'GET',`/courses/${course.id}/topics`)).items
 book=await upload('TEXTBOOK','Giáo trình KNN','textbook','large-book.pdf')
 assert.ok(book.versions[0].byte_size>20*1024*1024&&book.versions[0].byte_size<=100*1024*1024)
 assert.equal(book.document_type,'textbook')
 const p=teacher.page,version=book.versions[0].id
 await p.getByRole('button',{name:'Chỉ công bố PDF',exact:true}).click()
 await p.getByRole('button',{name:'Lưu trữ PDF',exact:true}).waitFor()
 await p.getByText('Phạm vi nguồn và chương/chủ đề (tùy chọn)',{exact:true}).click()
 await p.getByLabel('Dùng toàn bộ tài liệu làm nguồn',{exact:true}).uncheck()
 await p.getByLabel('Từ trang PDF 1',{exact:true}).fill('2')
 await p.getByLabel('Đến trang PDF 1',{exact:true}).fill('12')
 await p.getByLabel('Tên chương 1',{exact:true}).fill('Chuẩn hóa dữ liệu')
 await p.getByLabel('Chủ đề ưu tiên 1',{exact:true}).selectOption(topics[1].id)
 await p.getByRole('button',{name:'Lưu phạm vi nguồn',exact:true}).click()
 await p.getByText('Đã lưu phạm vi. Nếu nguồn đang bật, hệ thống sẽ chuẩn bị lại trong nền.',{exact:true}).waitFor()
 await mutate(p,()=>detail(p).getByRole('button',{name:'Công bố và dùng cho trợ giảng',exact:true}).click(),'POST',`/document-versions/${version}/rag/enable`)
 const ready=await state(version)
 assert.equal(ready.status,'ready');assert.equal(ready.progress.extracted_pages,11);assert.equal(ready.progress.embedded_chunks,11)
 await p.locator('.rag-document > p').filter({hasText:/Trợ giảng:.*Sẵn sàng/}).waitFor()
 await p.getByText('Đã trích chữ: 11/11 trang đã chọn · Tổ chức nguồn: 11/11 trang.',{exact:true}).waitFor()
 await shot(p,'teacher-textbook-ready.png')
 // Slide describes KNN briefly; only the textbook contains normalization.
 const slide=await upload('SLIDE','Bài giảng KNN','lecture','slide.pdf')
 await mutate(p,()=>detail(p).getByRole('button',{name:'Công bố và dùng cho trợ giảng',exact:true}).click(),'POST',`/document-versions/${slide.versions[0].id}/rag/enable`);assert.equal((await state(slide.versions[0].id)).status,'needs_review')
 await api(teacher,'PUT',`/topics/${topics[0].id}/materials`,{items:[{document_version_id:slide.versions[0].id,page_start:2,page_end:2,order_index:1}]})
 assert.deepEqual(errors,[])
})

test('student library + cross-topic textbook citation, hidden library source and RAG withdrawal',{timeout:120000},async()=>{
 const p=student.page,version=book.versions[0].id
 await login(student,env.DEMO_STUDENT_EMAIL,env.DEMO_STUDENT_PASSWORD,`/learn/${run.id}?course=${course.id}&view=materials`)
 await p.getByRole('heading',{name:'Giáo trình chính',exact:true}).waitFor()
 await p.getByRole('button',{name:'Đọc Giáo trình KNN · bản 1',exact:true}).click();await p.locator('.pdf-page[data-page="1"] .pdf-text').waitFor()
 await p.getByRole('button',{name:'Về thư viện',exact:true}).click()
 await api(teacher,'PATCH',`/documents/${book.id}`,{show_in_learning:false})
 await p.goto(origin+`/learn/${run.id}?course=${course.id}&topic=${topics[0].id}&view=topic`,{waitUntil:'networkidle'})
 await p.getByRole('button',{name:'Hỏi trợ giảng',exact:true}).click()
 await p.getByLabel('Câu hỏi từ PDF · tối đa 2000 ký tự',{exact:true}).fill('Why is feature normalization needed before nearest neighbors distance comparisons?')
 await p.getByRole('button',{name:'Gửi câu hỏi',exact:true}).click()
 const citations=p.locator('.chat-citations')
 await citations.getByText('Giáo trình KNN',{exact:true}).waitFor()
 const sessions=await api(student,'GET',`/course-runs/${run.id}/chat-sessions`),turn=(await api(student,'GET',`/chat-sessions/${sessions.items[0].id}/messages`)).items[0]
 assert.equal(turn.status,'answered');assert.equal(turn.citations[0].document_version_id,version)
 const page=turn.citations[0].pdf_page;assert.ok(page>=2&&page<=12)
 await citations.getByRole('button').first().click();await p.locator(`.pdf-page[data-page="${page}"] .pdf-text`).waitFor()
 assert.equal(await p.getByLabel('Trang PDF',{exact:true}).inputValue(),String(page))
 await shot(p,'student-textbook-citation.png')
 await api(teacher,'POST',`/document-versions/${version}/rag/disable`)
 assert.equal((await api(student,'GET',`/chat-sessions/${sessions.items[0].id}/messages`)).items[0].status,'source_unavailable')
 assert.equal((await student.context.request.get(origin+`/api/v1/course-runs/${run.id}/document-versions/${version}/content`)).status(),200)
 assert.deepEqual(errors,[])
})

test('scan/partial state and transcription; genuine missing-model retry; responsive settings',{timeout:180000},async()=>{
 const p=teacher.page
 scan=await upload('SCAN','Nguồn cần đối chiếu','supplement','scan.pdf')
 const version=scan.versions[0].id
 await mutate(p,()=>detail(p).getByRole('button',{name:'Công bố và dùng cho trợ giảng',exact:true}).click(),'POST',`/document-versions/${version}/rag/enable`)
 assert.equal((await state(version)).status,'needs_review')
 await detail(p).getByText(/Nguồn sẵn sàng một phần:/).waitFor()
 await detail(p).getByRole('button',{name:'Kiểm tra nguồn',exact:true}).click()
 await detail(p).getByLabel('Trang cần đối chiếu',{exact:true}).selectOption('2')
 await detail(p).getByText('Ít hoặc không có chữ',{exact:true}).waitFor()
 await detail(p).getByText('Thêm bản phiên chép cho trang 2',{exact:true}).click()
 await detail(p).getByLabel('Văn bản đã đối chiếu (20–3500 ký tự)',{exact:true}).fill('Manually checked transcription of a scanned example from the source page.')
 await mutate(p,()=>detail(p).getByRole('button',{name:'Lưu phiên chép và cho phép trang',exact:true}).click(),'PATCH',`/document-versions/${version}/rag/pages/2`)
 const checked=await state(version);assert.equal(checked.counts.checked,1)
 await shot(p,'teacher-partial-transcription.png')
 const retryDoc=await upload('RETRY','Nguồn kiểm thử lại','supplement','slide.pdf')
 const manifest=path.join(process.env.RAG_MODEL_FIXTURE_DIR,'manifest.json'),off=manifest+'.off'
 await fs.rename(manifest,off)
 try{
   await mutate(p,()=>detail(p).getByRole('button',{name:'Công bố và dùng cho trợ giảng',exact:true}).click(),'POST',`/document-versions/${retryDoc.versions[0].id}/rag/enable`)
   const failed=await state(retryDoc.versions[0].id);assert.equal(failed.status,'failed');assert.equal(failed.error_code,'EMBEDDING_UNAVAILABLE')
   await detail(p).getByRole('button',{name:'Thử chuẩn bị lại',exact:true}).waitFor()
 }finally{await fs.rename(off,manifest)}
 await mutate(p,()=>detail(p).getByRole('button',{name:'Thử chuẩn bị lại',exact:true}).click(),'POST',`/document-versions/${retryDoc.versions[0].id}/rag/retry`)
 assert.equal((await state(retryDoc.versions[0].id)).status,'needs_review')
 await detail(p).getByText(/Nguồn sẵn sàng một phần:/).waitFor()
 for(const width of [360,390,768,1440]){
   await p.setViewportSize({width,height:900});await p.getByText('Phạm vi nguồn và chương/chủ đề (tùy chọn)',{exact:true}).click()
   assert.ok(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Settings fit ${width}`)
   const checkbox=p.getByLabel('Dùng toàn bộ tài liệu làm nguồn',{exact:true});await checkbox.focus();await p.keyboard.press('Space');assert.equal(await checkbox.isChecked(),false);await p.keyboard.press('Space')
   await shot(p,`teacher-settings-${width}.png`);await p.getByText('Phạm vi nguồn và chương/chủ đề (tùy chọn)',{exact:true}).click()
 }
 assert.deepEqual(errors,[])
})

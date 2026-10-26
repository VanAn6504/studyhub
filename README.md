# StudyHub

Đồ án: **Xây dựng nền tảng Web học tập trực tuyến tích hợp AI dự báo và cá nhân hóa lộ trình học tập**.

Học phần mẫu: **Phát triển ứng dụng di động đa nền tảng**, 5 PDF Flutter/Dart, 8 chủ đề. Mốc báo cáo: 13/12/2026 với giảng viên hướng dẫn và 31/12/2026 báo cáo tổng.

## Trạng thái

Đã có bản nền móng chạy được: FastAPI, React/TypeScript, PostgreSQL, migration, đăng ký/đăng nhập/logout, phân quyền teacher/student, học phần/lớp học, enrollment và 8 chủ đề mẫu. Giảng viên tạo học phần thuộc quyền quản lý, chuẩn bị nội dung dùng chung và mở các lớp học riêng; sinh viên xem học phần của lớp đã đăng ký.

Đã bổ sung upload/xem PDF có phiên bản, gắn khoảng trang vào chủ đề, biên soạn và công bố quiz, lưu/khôi phục/nộp bài và chấm điểm ở server. Trình xem PDF.js ghi log mở tài liệu và trang đang hiển thị; log gắn enrollment, thời gian server và provenance để chuẩn bị dữ liệu cho AI. Giảng viên xem kết quả và số lượt xem trang theo sinh viên.

Đã có lộ trình theo kết quả quiz hiện tại, snapshot có revision và báo cáo cho giảng viên; pipeline OULAD và API/giao diện điểm rủi ro thử nghiệm có cutoff, cache, đặc trưng và giải thích SHAP. Chatbot RAG dùng Gemini, embedding local và nguồn PDF được giảng viên cho phép; tự chuẩn bị nguồn và kiểm tra theo trang. Seed nền móng không tự upload/công bố PDF hoặc quiz nháp. Tài liệu trong `docs/` chỉ có trên máy local, không nằm trong bản clone Git.

## Chạy bằng Docker trên Windows

Yêu cầu: Docker Desktop đã mở và engine sẵn sàng. Tại thư mục repository:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Script tạo `.env` với bí mật ngẫu nhiên nếu chưa có, build các dịch vụ, chạy migration rồi seed dữ liệu mẫu. Chạy lại giữ nguyên `.env`, tài khoản và dữ liệu đã có. Các port mặc định chỉ lắng nghe trên máy local.

- Web: [http://localhost:5173](http://localhost:5173).
- API reference: [http://localhost:8000/api/docs](http://localhost:8000/api/docs).
- Database local: `127.0.0.1:5433`; database `studyhub`. Backend trong Docker kết nối qua tên service `postgres`.

Tài khoản mặc định sau seed:

| Vai trò | Email | Mật khẩu |
| --- | --- | --- |
| Giảng viên | teacher@example.com | Giá trị `BOOTSTRAP_TEACHER_PASSWORD` trong `.env` |
| Sinh viên | student@example.com | Giá trị `DEMO_STUDENT_PASSWORD` trong `.env` |

Email/tên có thể cấu hình bằng các biến cùng nhóm trong `.env` trước lần seed đầu tiên. Seed không đổi mật khẩu của user đã tồn tại. Run thật mặc định bắt đầu ngày seed theo Asia/Bangkok; có thể đặt `COURSE_RUN_START_DATE` trước lần seed đầu tiên.

Kiểm tra và dừng dịch vụ:

```powershell
docker compose ps
docker compose logs --tail 50 backend
docker compose stop
```

Mở lại với `docker compose up -d`. Dữ liệu Postgres và PDF riêng tư nằm trong hai volume `postgres_data`, `pdf_storage`, được giữ khi stop/up. Sau khi sửa mã, dùng script setup hoặc `docker compose up -d --build` để build lại. Migration `0003_guidance` bổ sung snapshot lộ trình, model, prediction và revision của bài làm; giữ dữ liệu hiện có. Sao lưu database và volume PDF cùng nhau; không dùng `docker compose down -v` nếu muốn giữ dữ liệu.

## Phát triển trên máy local

Yêu cầu Python 3.12 và Node 24 cho chế độ local. Chọn đúng Python 3.12 khi tạo virtualenv (ví dụ Windows launcher `py -3.12`); Python mặc định của máy này là 3.14, còn bản đã kiểm chứng dùng môi trường 3.12. Khởi tạo `.env` và PostgreSQL:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -EnvironmentOnly
docker compose up -d postgres
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-dev.txt
```

Terminal backend:

```powershell
Set-Location backend
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m app.seed
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal frontend:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Vite proxy `/api` tới backend 8000; cấu hình khác bằng `API_PROXY_TARGET`. Nếu các container backend/frontend đang dùng port 8000/5173, dừng chúng trước khi dùng hai terminal local. Không cần dừng Postgres.

## Kiểm thử

Từ thư mục repository, với Postgres đang chạy và môi trường Python đã cài requirements-dev:

```powershell
backend/.venv/Scripts/python.exe scripts/test_backend.py
```

Runner tự tạo database riêng `studyhub_test`, chạy migration và các ca tích hợp auth/course/PDF/quiz/log/path/prediction. Có thể đặt `TEST_DATABASE_URL` khác nhưng tên database bắt buộc kết thúc `_test`; fixture xóa dữ liệu trong database kiểm thử này trước mỗi ca. PDF và model kiểm thử nằm trong thư mục tạm riêng. Runner/fixture dùng `127.0.0.1` cho PostgreSQL local để tránh độ trễ IPv6 trên Windows.

Build frontend:

```powershell
Set-Location frontend
npm.cmd run build
```

Kiểm thử hồi quy giao diện PDF/lộ trình/chatbot (frontend đang chạy ở port 5173; các API và PDF dùng fixture tổng hợp trong trình duyệt, không ghi database hoặc gọi Gemini):

```powershell
Set-Location frontend
npm.cmd ci
npx.cmd playwright install chromium
npm.cmd run test:ui
```

Có thể chạy frontend bằng Docker hoặc `npm.cmd run dev`; kiểm thử dùng ứng dụng React và PDF.js thật. Đổi URL bằng `FRONTEND_URL`; dùng Edge đã cài trên Windows bằng `$env:PLAYWRIGHT_CHANNEL='msedge'`. Ca kiểm tra mở/đóng PDF nhiều lần, chuyển trang, nguồn từ lộ trình/chatbot, log và retry giữ ID, nộp quiz/cập nhật lộ trình, teacher không ghi log sinh viên, số lượng khối và lỗi console. Gửi log PDF chỉ cập nhật danh sách log và trạng thái dự báo liên quan hoạt động; không tải lại lộ trình, danh sách PDF hoặc kết quả quiz.

Kiểm tra hợp đồng đặc trưng OULAD và split (fixture nhỏ, không cần dataset thật):

```powershell
backend/.venv/Scripts/python.exe -m pip install -r ml/requirements-dev.txt
backend/.venv/Scripts/python.exe -m pytest ml/tests -q
```

GitHub Actions có cấu hình test backend với PostgreSQL, build frontend và test hợp đồng ML. Trạng thái chạy CI thực tế xem trong repository GitHub.

## Không gian học phần

### Website P0 và điều hướng

- Khách: `/`, `/courses`, `/courses/:slug`, `/login`, `/register`, `/help`, `/about`, `/privacy`.
- Sinh viên: `/dashboard`, `/my-courses`, `/enrollments`, `/profile`, `/settings/security`, `/learn/:runId`.
- Giảng viên: `/teaching`, `/teaching/courses`, `/teaching/classes`, `/teaching/requests`, `/teaching/courses/:courseId/overview`, `/teaching/runs/:runId/admissions`, `/teaching/workspace/:courseId`.
- Router History API dùng chung tại `frontend/src/website/navigation.ts`, không thêm dependency. Giữ adapter cho liên kết `#view=...` cũ, Back/Forward, URL sâu và guard khi form/quiz chưa lưu. Nginx và Vite đã có fallback về `index.html`; khi host khác cần cấu hình tương đương cho URL sâu. Không rewrite `/api/` thành HTML.
- Sau đăng nhập, chỉ trở về URL nội bộ hợp lệ; người dùng phải xác nhận tham gia/gửi yêu cầu. Chờ duyệt không giữ chỗ. Sinh viên không tự kích hoạt lại enrollment bị giảng viên vô hiệu.
- Đưa học phần hiện có lên danh mục: **Học phần quản lý → Giới thiệu công khai → lưu nháp → xem trước → công bố**. Trong **Lớp học → Tuyển sinh**, chọn hình thức tham gia, giới thiệu lớp và cửa sổ/chỗ trống. Công bố giới thiệu không công khai PDF/quiz hoặc tự mở tuyển sinh.
- **Tiếp tục học** lưu vị trí điều hướng riêng; tải tổng quan/hồ sơ không tạo log học hay chạy lại mô hình. Tiến độ dựa trên quiz đang công bố; chưa có quiz sẽ hiển thị chưa có dữ liệu.
- Hồ sơ mặc định riêng tư; chỉ sửa tên hiển thị và giới thiệu. Đổi mật khẩu kiểm tra mật khẩu hiện tại và thu hồi tất cả phiên, cần đăng nhập lại. Chưa có dịch vụ gửi email đặt lại mật khẩu. Giới hạn đổi mật khẩu hiện nằm trong tiến trình backend, phù hợp một instance local; nhiều replica cần bộ đếm dùng chung trước khi vận hành thật.

Kiểm thử website tích hợp (đã cài backend dependencies và `npm.cmd ci` trong frontend, PostgreSQL local đang chạy):

```powershell
backend/.venv/Scripts/python.exe scripts/test_website.py
```

Lệnh này chạy cả E2E website và bộ UI hồi quy PDF/quiz/RAG/lộ trình trên cùng phiên bản frontend.

Runner tạo database `_test` riêng, migrate/seed với tài khoản sinh riêng, mở FastAPI/Vite tại cổng loopback tạm rồi chạy Playwright. Không đổi dữ liệu thật; database đạt kiểm thử được xóa, database thất bại giữ lại để chẩn đoán (`--keep-db` giữ cả lần đạt). Log/ảnh ở `.local/website-p0/runs/`; `environment.json` tại đó chứa bí mật kiểm thử, không chia sẻ/commit. Windows mặc định dùng Edge đã cài; môi trường khác cần browser Chromium của Playwright. Các ca lỗi mạng/hết phiên được gây lỗi có chủ đích ở trình duyệt; luồng nghiệp vụ chính dùng API/PostgreSQL thật. Kiểm thử này tắt provider chat để không gửi dữ liệu ra ngoài hoặc tiêu quota Gemini; chất lượng mô hình thật phải nghiệm thu riêng.

### API website P0

Migration **0009_website_p0** thêm metadata công khai, yêu cầu tham gia lớp, hồ sơ riêng và vị trí tiếp tục học. Mọi học phần cũ mặc định **hidden**; lớp cũ mặc định **invite_only**, `listed=false`. Migration không công bố học phần, không ghi danh thêm và không thay kết quả/log cũ. Nâng cấp bằng `docker compose up -d --build` hoặc `alembic upgrade head` trong backend. Sao lưu database và PDF cùng nhau trước nâng cấp; downgrade xóa dữ liệu mới của P0 nên cần backup khi phục hồi.

Tất cả endpoint dưới đây dùng prefix `/api/v1` và envelope lỗi/CSRF hiện có:

- Public: GET `/catalog/categories`, `/catalog/courses`, `/catalog/courses/{slug}`. Catalog chỉ trả metadata whitelist của snapshot đã công bố; không dùng API `/courses` riêng tư. Search `q` hỗ trợ tiếng Việt có/không dấu và tìm literal, `category`, `level`, `availability=all|accepting`, `sort=newest|title|relevance`, `limit`1–24 và `offset`; thứ tự phụ ổn định theo ID.
- Owner: GET/PATCH `/teaching/courses/{id}/publication`; POST `/teaching/courses/{id}/publish` và `/hide`. Bản nháp tách snapshot đang công bố. Slug ổn định khi đổi tên. Public metadata không mở quyền PDF, quiz, đáp án, chat, dự báo hoặc danh sách học viên.
- Owner: GET/PATCH `/teaching/runs/{id}/admissions`; cấu hình `enrollment_mode=invite_only|approval|open`, `listed`, `opens_at`, `closes_at`, `capacity`, `expected_revision`. Lớp synthetic không được tuyển sinh/public catalog. Ngày bắt đầu học độc lập cửa sổ nhận đăng ký.
- Student: POST `/course-runs/{id}/join` cho open, `/enrollment-requests` cho approval; body `expected_revision` từ thông tin lớp. Retry trả cùng enrollment/pending request; inactive không tự kích hoạt. Server khóa Course→Run và kiểm tra chỗ/thời hạn; pending **không giữ chỗ**. Invitation bằng email được giữ, có kiểm tra capacity khi cấp/kích hoạt chỗ.
- Student: GET `/me/enrollment-requests`, POST `/me/enrollment-requests/{id}/cancel`. Owner: GET `/teaching/runs/{id}/requests`, POST `/teaching/requests/{id}/decision` (`action=approve|reject`, `reason`). Chỉ owner quyết định; retry cùng quyết định không tạo enrollment mới, không ghi đè trạng thái terminal khác.
- Private: GET/PATCH `/me/profile` chỉ sửa `display_name`, `bio`; email/role chỉ đọc. POST `/me/password` nhận `current_password`, `new_password`, yêu cầu CSRF, giới hạn5 lần/10 phút theo tài khoản, thu hồi mọi phiên và cần đăng nhập lại. Login và đổi mật khẩu khóa cùng user để không cấp phiên bằng mật khẩu cũ sau đổi. Limiter hiện chạy trong một tiến trình local, chưa dùng shared store. Không có email reset giả.
- Student: GET `/me/overview`, `/me/courses` (q/status/limit/offset), GET/PUT `/me/resume`. Tiến độ từ chủ đề có quiz hiện hành đã đạt; chưa có quiz thì percent=null. Resume chỉ lưu vị trí điều hướng, không tạo LearningEvent/đặc trưng AI; đọc lại kiểm tra quyền và fallback nếu PDF/chủ đề cũ bị thu hồi. Teacher: GET `/teaching/overview` chỉ có dữ liệu thuộc owner.

### Thao tác trong giao diện học phần

- **Sinh viên:** Học phần của tôi → Vào học phần → Vào học một chủ đề. Trong chủ đề, chọn **Đọc tài liệu** hoặc **Làm quiz**; PDF và quiz có trang riêng. **Lộ trình & tiến độ** và **Kết quả** nằm trên thanh điều hướng. Nếu đăng ký nhiều lớp của cùng học phần, chọn lớp trước khi học.
- **Trợ giảng:** bấm **Hỏi trợ giảng** trong học phần. Đóng/mở khung chat giữ phiên đang chọn; nguồn trích dẫn mở đúng phiên bản PDF và trang. Luồng này dùng API RAG hiện có.
- **Giảng viên:** Học phần quản lý → **Tạo học phần** hoặc **Quản lý học phần**. Trong **Chủ đề**, thêm/chỉnh tên, mã, mục tiêu, thứ tự và tiên quyết; mỗi chủ đề tập hợp tài liệu và quiz của nó.
- **Tài liệu:** **Thêm tài liệu** mở form upload riêng → lưu nháp → xem PDF/kiểm tra nguồn → công bố. Danh sách chính hiển thị tên, trạng thái và nút công bố/RAG; **Mở tài liệu** xem chi tiết, phiên bản và các trang cần kiểm tra. Có thể chọn chủ đề và khoảng trang khi upload để gắn sau công bố. Nếu tải lại trang trước khi công bố, lựa chọn gắn chưa lưu sẽ mất; dùng **Gắn tài liệu đã công bố** trong chủ đề để gắn lại.
- **Lớp học:** tạo lớp nháp, thêm tài khoản sinh viên theo email, mở lớp, ngừng/kích hoạt lại đăng ký và xem kết quả lớp. Nội dung thuộc học phần; ngày bắt đầu, đăng ký và kết quả thuộc lớp. Nhãn “lớp học” sử dụng thực thể `CourseRun` hiện có, không thêm actor admin.

URL lưu trang học phần/chủ đề/PDF trong pathname và query để hỗ trợ Back và tải lại trang; liên kết hash cũ được chuyển đổi tương thích. Lựa chọn quiz chưa lưu giữ khi chuyển giữa các phần của cùng chủ đề; đổi chủ đề/lớp hoặc đăng xuất yêu cầu xác nhận. Dùng **Lưu bài làm** để lưu lên server trước khi đóng trình duyệt. Log chưa gửi giữ nguyên ID và có nút gửi lại; đổi lớp/đăng xuất phải gửi xong log.

API bổ sung cho không gian giảng viên:

- PATCH `/api/v1/topics/{id}`: cập nhật `{code, title, order_index, objectives}`, giữ ID, tài liệu và quiz; chỉ tăng `content_revision` khi nội dung đổi. Tiên quyết vẫn cập nhật bằng endpoint PUT hiện có.
- GET `/api/v1/course-runs/{id}/enrollments`: danh sách phân trang `{items, total, limit, offset}`; mỗi mục gồm ID đăng ký, ID/email/tên sinh viên và trạng thái. Chỉ giảng viên sở hữu lớp được đọc.

Không cần migration mới cho bố cục này. Việc đổi giao diện không xác nhận độ chính xác dự báo trên sinh viên hoặc khả năng chịu tải RAG nhiều học phần; hai phần đó cần nghiệm thu riêng.

### Chỉnh sửa, xóa tài liệu và chọn số câu quiz

- Trong **Tài liệu**, chọn **Chỉnh sửa thông tin** để đổi mã/tên. Đánh dấu **Thay file PDF — xóa file cũ**, chọn **PDF thay thế** rồi lưu để thay nội dung ngay trong form. File mới phải hợp lệ trước khi file cũ bị xóa. Sau khi thay, tài liệu về nháp, tắt RAG và bỏ liên kết trang cũ; kiểm tra/gắn lại chủ đề/công bố. Có thể dùng **Thêm phiên bản PDF** trong trang chi tiết khi muốn giữ các file cũ thay vì xóa chúng.
- **Xóa tài liệu** yêu cầu xác nhận rồi xóa vĩnh viễn tài liệu và mọi file PDF của nó, gỡ liên kết chủ đề và xóa corpus/embedding/trạng thái RAG. Không có thùng rác/khôi phục. Điểm, quiz và log đã ghi được giữ; nguồn PDF đã xóa/thay không mở được và không tự trỏ sang file mới. Mã tài liệu được dùng lại sau khi xóa.
- Trong **Biên soạn quiz**, nhập JSON đúng cấu trúc `quiz_draft.json`; tối đa 1 MiB, 1000 câu trong file nhiều chủ đề và 100 câu của chủ đề đang chọn mỗi lần nhập. Hệ thống nhập các câu có trong file, bỏ qua mã đã tồn tại và tự chọn các câu thuộc lần nhập đó. File cần có đủ câu cho chủ đề; không tự sinh thêm câu hỏi.
- Dùng **Chọn 10 câu**, **Chọn 20 câu**, **Chọn tất cả câu** hoặc tích từng câu. Nút chọn nhanh lấy các câu đầu trong ngân hàng đang hiển thị; chỉ bật khi đủ câu. Mỗi quiz hỗ trợ **3–100 câu**. Tạo nháp → kiểm tra câu hỏi/đáp án/nguồn → xác nhận → công bố.

API quản lý tài liệu (chỉ chủ sở hữu học phần; thao tác ghi yêu cầu CSRF):

- PATCH `/api/v1/documents/{id}` nhận `code`, `title`, `status`; mã trùng trả 409. Giữ ID và các phiên bản PDF.
- PUT `/api/v1/documents/{id}/file` nhận multipart `code`, `title`, `file`: thay PDF và metadata trong một giao dịch, xóa các file cũ sau commit; file không hợp lệ không thay đổi tài liệu cũ. Giữ ID tài liệu, tạo ID phiên bản mới.
- DELETE `/api/v1/documents/{id}` trả 204, xóa bản ghi tài liệu, bỏ mapping/corpus và các file PDF. ID không còn tồn tại trả 404. Không còn endpoint khôi phục hoặc danh sách thùng rác.

Cần migration **0008_permanent_documents**: cho phép phiên bản mất liên kết tài liệu đã xóa để giữ khóa tham chiếu của log/quiz, và thêm hàng đợi dọn file. Chỉ giữ metadata phiên bản lịch sử, không giữ PDF hoặc corpus để khôi phục. Tác vụ dọn file chạy sau commit; nếu ổ lưu trữ tạm bị khóa thì giữ yêu cầu và thử lại ở lượt dọn kế tiếp hoặc khi backend khởi động. Migration không tự xóa tài liệu đã có. Chạy `docker compose up -d --build` hoặc `alembic upgrade head` trước khi khởi động backend. Sao lưu database và volume PDF cùng nhau; sau khi đã xóa vĩnh viễn, muốn quay lại dữ liệu cũ phải khôi phục cả hai từ backup.

## Lộ trình cá nhân hóa

Sinh viên vào học phần → **Lộ trình & tiến độ** để xem **Bước học tiếp theo**. Bài hoàn thành mới nhất của quiz đang công bố xác định `weak`/`mastered`; chưa làm là `not_assessed`, chưa có quiz đủ câu là `not_available`. Quy tắc `path_rules_v1` ưu tiên chủ đề yếu, thêm tiên quyết chưa đạt trước, rồi chủ đề chưa đánh giá. Tiên quyết chưa có quiz tạo cảnh báo nhưng không khóa học.

Mỗi snapshot lưu revision, phiên bản nội dung, ID bài làm đầu vào, trạng thái/điểm, lý do và liên kết PDF/quiz. Nộp bài tạo snapshot trong cùng giao dịch chấm điểm; retry không tạo thêm revision. Quiz/prerequisite/material thay đổi thì GET path cập nhật. Điểm rủi ro không điều khiển thứ tự lộ trình.

- GET `/api/v1/course-runs/{id}/learning-path`: snapshot của student đang enroll, kể cả run closed/synthetic.
- GET `/api/v1/course-runs/{id}/report`: owner teacher xem lịch sử và trạng thái/lộ trình hiện tại của từng sinh viên.

## Huấn luyện và cài mô hình dự báo

Lấy bản CSV ZIP gốc của [OULAD, UCI dataset 349](https://archive.ics.uci.edu/dataset/349/open+university+learning+analytics+dataset), giấy phép CC BY 4.0, lưu tại `ml/data/oulad.zip` (không giải nén cũng chạy được). Dataset, report và artifact được Git ignore; clone mới cần lấy dataset và huấn luyện lại:

```powershell
backend/.venv/Scripts/python.exe -m pip install -r ml/requirements.txt
backend/.venv/Scripts/python.exe ml/train_oulad.py
backend/.venv/Scripts/python.exe -m pytest ml/tests -q
docker compose up -d --build
```

Pipeline tính A/B ở ngày 28/42, baseline prior/Random Forest/XGBoost (12 thí nghiệm), giữ cả sinh viên không có hoạt động/điểm. Fail=1, Pass/Distinction=0; Withdrawn bị loại và đếm riêng. Cùng split khoảng 60/20/20 theo **id_student**, không trùng người giữa train/validation/test; median imputer chỉ fit train. Model/feature set triển khai ở ngày 42 và ngưỡng được chọn bằng Fail-F1 trên validation, rồi mới đánh giá test. Không refit bằng test. Các tham số và seed được cố định trong code/báo cáo.

`ml/artifacts/current/` chứa `model.joblib`, `manifest.json`, `evaluation.json`, `split.csv` và feature CSV ở hai cutoff. Report có Precision/Recall/F1 lớp Fail, confusion matrix, ROC-AUC, Brier/reliability, độ phủ và kết quả từng module/presentation. Manifest có feature order/schema, mapping lớp, threshold, dataset/model hash, preprocessing và phiên bản thư viện. Có thể chạy lại với `--output ml/runs/<ten-thi-nghiem>` để đối chiếu. Các split chưa kiểm chứng khả năng tổng quát hóa sang presentation hoàn toàn mới; điểm chưa hiệu chỉnh xác suất và chưa xác nhận trên StudyHub.

Docker mount `ml/artifacts` vào `/models` ở chế độ đọc. Local dùng `ml/artifacts/current` hoặc `MODEL_ARTIFACT_PATH`. API kiểm tra hash/schema/cutoff/phiên bản thư viện trước khi nạp. **Joblib chỉ dành cho artifact do quản trị viên tự huấn luyện và quản lý**, không dùng file tải lên hoặc model nhận từ nguồn không tin cậy. Mã pipeline/dependency được commit; artifact/dataset cần sao lưu riêng. Định dạng serialization phụ thuộc phiên bản thư viện; xem [hướng dẫn model persistence của scikit-learn](https://scikit-learn.org/1.7/model_persistence.html).

### Cửa sổ và trạng thái dự báo

- POST `/api/v1/course-runs/{id}/predictions`: student, body rỗng `{}` hoặc không body; cần Origin + CSRF; không nhận feature/score/model path từ client.
- GET `/api/v1/course-runs/{id}/prediction`: lấy snapshot đã lưu, không tự chạy model; chưa có trả `not_computed`.
- Cửa sổ **ngày 0–42**, tức 43 ngày lịch từ midnight ngày bắt đầu run trong timezone của run. Chỉ tính event trước `cutoff_end_at`, `received_at` cũng trước cutoff và provenance khớp run; quiz theo `graded_at`. Không lấy day43 trở đi.
- Model lấy **lần chấm đầu tiên mỗi topic** trong cửa sổ, không tăng assessment_count theo retake/quiz version. Không có điểm là NULL rồi impute bằng median train. Path dùng bài mới nhất của current version, khác mục đích với feature model.
- `not_ready`: chưa hết cửa sổ; `insufficient_data`: model hợp lệ nhưng không có page_view; cả hai có risk_score=NULL. Model thiếu/hash/schema/version sai trả 503 `MODEL_UNAVAILABLE`. `ok` lưu snapshot bất biến, cache theo enrollment/model/cutoff. Ngày bắt đầu/timezone bị khóa khi có attempt/event/prediction.
- Giao diện ghi **điểm rủi ro thử nghiệm**, `transport_status=unvalidated`, `calibration_status=uncalibrated`. SHAP tính chính xác các coalition của 3/6 feature với 8 background cố định từ train; tổng đóng góp + mốc nền = điểm raw probability. Đóng góp không phải quan hệ nhân quả. OULAD click và page_view StudyHub khác thang đo/ngữ nghĩa.

### Lượt học mô phỏng để demo ngay

Sau khi teacher đã công bố ít nhất một PDF trong học phần, quản trị viên có thể tạo riêng `ML_DEMO_42` cho tài khoản student có sẵn:

```powershell
docker compose exec -T backend python -m app.seed_prediction_demo --course-code MOBILE_MULTIPLATFORM --student-email student@example.com
```

CLI tạo run synthetic closed bắt đầu 60 ngày trước, 3 page_view mô phỏng ngày 0/2/42, không tạo điểm quiz và không sửa ngày/log/attempt của run thật. Chạy lại không nhân đôi sự kiện. Sinh viên chọn `ML_DEMO_42`, bấm **Tính dự báo**; badge mô phỏng luôn hiển thị, client không ghi quiz/log vào run đó. PDF/quiz của học phần vẫn dùng các version đã công bố. Dữ liệu thật mới bắt đầu cần chờ cutoff để dự báo; lộ trình theo quiz hoạt động ngay.

## Chatbot RAG từ PDF

Giảng viên upload PDF nháp, xem trước rồi bấm **Công bố và dùng cho trợ giảng** ngay trên thẻ phiên bản PDF. Một thao tác công bố tài liệu và cho phép phiên bản đó làm nguồn; hệ thống tự trích văn bản, lọc trang có cảnh báo và tạo embedding trong nền. **Chỉ công bố PDF** vẫn có sẵn để phát tài liệu mà chưa bật nguồn mới cho chatbot. Trạng thái hiển thị **Đang chuẩn bị nguồn**, **Sẵn sàng**, **Có trang cần kiểm tra**, lỗi hoặc **Đã tắt**. Không cần thao tác trích/duyệt từng đoạn/lập chỉ mục trong luồng chính.

**Cho phép tài liệu** khác với **giảng viên đã kiểm tra trang**. Các đoạn mới vẫn giữ review_status=pending; auto_eligible ghi riêng điều kiện sử dụng tự động, không giả mạo reviewed_by/reviewed_at. Trang đầu nghi là bìa, mục lục, ít chữ, trích lỗi hoặc phiên chép chưa kiểm tra bị giữ lại. Trang có ảnh nhưng trích đủ chữ được dùng theo chế độ **chỉ dùng phần chữ**, không hiểu/OCR ảnh; mã nguồn chỉ nằm trong ảnh vẫn cần bản phiên chép. Logo/ảnh trang trí không khiến giảng viên phải duyệt mọi slide. Bộ lọc có thể loại nhầm/bỏ sót, không chứng minh nội dung đúng.

Mở **Kiểm tra nguồn** trên phiên bản để xem **Chỉ hiện trang cần kiểm tra**, chọn trang, **Đối chiếu PDF trang …** xem PDF cạnh văn bản rồi **Đã đối chiếu, cho phép trang** hoặc **Loại trang khỏi trợ giảng**. Cần bật nguồn trước khi lưu quyết định. Có thể bỏ bộ lọc để xem nguồn tự động và trang đã kiểm tra. Trang ảnh/thiếu chữ: thêm bản phiên chép (20–3500 ký tự) → **Lưu phiên chép và cho phép trang**; đoạn cũ giữ nguyên text/hash và được loại, đoạn mới được ghi riêng. Hệ thống tự cập nhật embedding sau quyết định theo trang. Không có OCR tự động. **Tắt trợ giảng cho bản này** ngừng sử dụng nguồn và ẩn câu trả lời/trích dẫn liên quan trong lịch sử, nhưng PDF vẫn công bố và xem được. Lưu trữ PDF cũng thu hồi nguồn. Không đưa ngân hàng đáp án quiz vào corpus.

Corpus chia đoạn trong từng trang, giữ ID/version/trang 1-based và hash, không ghi đè hoặc nhân đôi khi thử lại. Migration `0006_rag_workflow` giữ corpus/review/chat cũ, thêm auto_eligible=false và trạng thái chuẩn bị theo phiên bản. Nguồn đã duyệt của luồng cũ tiếp tục hoạt động; chưa tự bật các đoạn pending cũ. Phiên bản PDF mới cần được bật riêng. Retrieval v1 dùng **embedding đa ngôn ngữ local + BM25**, chỉ lấy nội dung đã kiểm tra hoặc đủ điều kiện tự động trong PDF đã công bố của học phần đang enroll, nguồn không bị tắt và đã chuẩn bị xong; tối đa 4 đoạn. Các thuật ngữ như LayoutBuilder phải xuất hiện trong nguồn. Kiểm tra ID/quote không tự chứng minh mọi diễn giải của mô hình đúng.

### Gemini API và embedding local

Phần sinh câu trả lời dùng **Google Gemini API** theo đề cương. Mặc định chọn `gemini-3.5-flash-lite`; có thể đặt `GEMINI_MODEL` bằng model hỗ trợ structured output còn khả dụng trong project Google AI Studio. Xem [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output) và [bảng giá/free tier](https://ai.google.dev/gemini-api/docs/pricing). Dòng 2.5 bị hạn chế với project mới theo [danh sách model của Google](https://ai.google.dev/gemini-api/docs/models); mặc định 3.5 đã kiểm tra khả dụng. Quota/điều kiện free tier phụ thuộc tài khoản và có thể thay đổi; backend không tự chuyển model hoặc bật gói trả phí. Gemini chỉ nhận câu hỏi + tối đa 4 đoạn nguồn đủ điều kiện; không gửi cả PDF, tài khoản/điểm sinh viên, vector hay ngân hàng quiz. Theo bảng giá Google, dữ liệu free tier có thể được dùng để cải thiện sản phẩm; chỉ dùng tài liệu phù hợp với chế độ này.

**Embedding chạy CPU trên máy**, dùng checkpoint có sẵn [intfloat/multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), giấy phép MIT, ONNX quantized INT8 (~118 MB + tokenizer ~17 MB). Revision cố định `614241f622f53c4eeff9890bdc4f31cfecc418b3`; không train. Tokenizer giới hạn 512 token, tiền tố `query: `/`passage: `, mean pooling theo attention mask và chuẩn hóa L2 thành 384 chiều. Script tải file từ tác giả, đối chiếu digest nguồn, lưu manifest/hash; backend kiểm tra hash trước khi nạp. Không gọi API embedding, không tự tải model trong request và không cần PyTorch/GPU.

```powershell
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
backend/.venv/Scripts/python.exe scripts/prepare_embeddings.py
```

Weights/manifest nằm tại `.local/embedding/`, bị Git ignore, Docker mount read-only vào `/embedding`. Clone máy mới cần chạy script; artifact không nằm trong image/Git. Local dùng mặc định đường dẫn trên hoặc `EMBEDDING_MODEL_PATH`; đường dẫn tương đối tính từ repository root.

Điền **chỉ trong .env local** (key không đưa vào source/frontend/Git hoặc URL/log):

```dotenv
CHAT_PROVIDER=gemini
GEMINI_API_KEY=<key riêng của bạn>
GEMINI_MODEL=gemini-3.5-flash-lite
CHAT_TIMEOUT_SECONDS=45
```

```powershell
docker compose up -d --build
```

Chưa có key, provider lỗi hoặc trả JSON/citation không hợp lệ => 503 `CHAT_UNAVAILABLE`; quota 429 từ Google => 503 `CHAT_QUOTA_EXCEEDED`. Model không khả dụng (Google 404) => 503 `CHAT_MODEL_UNAVAILABLE`, cần kiểm tra `GEMINI_MODEL`. Không tự retry API để tránh tiêu thêm quota. Có thể đặt `CHAT_PROVIDER=disabled` để tắt sinh câu trả lời; PDF/quiz/lộ trình vẫn hoạt động. REST gọi `generateContent` tại domain Google cố định, gửi key bằng header, JSON output, không tools/search grounding và không streaming. Khi Gemini gộp xuống dòng của PDF, server chỉ cho phép khác biệt khoảng trắng rồi lấy lại đoạn nguyên văn liên tục từ nguồn để hiển thị; chữ, dấu câu và thứ tự phải khớp, excerpt tối đa 600 ký tự.

Embedding tự tạo khi bật nguồn và khi kiểm tra trang. Vector/mã model lưu PostgreSQL, gắn chunk/version/trang/hash; thử lại không nhân đôi. Nếu chuẩn bị lỗi, sửa cấu hình rồi bấm **Thử chuẩn bị lại**; nếu model đổi sau khi nguồn đã sẵn sàng, tắt rồi bật nguồn để lập lại chỉ mục. Thiếu model/vector hoặc model đổi => 503 `EMBEDDING_UNAVAILABLE`. Tác vụ nền MVP chạy trong backend, không có worker/queue ngoài: trạng thái/generation được lưu, nếu backend bị ngắt thì sau lease 10 phút hiển thị lỗi để thử lại; không tự khôi phục tác vụ. Generation ID chặn tác vụ cũ bật lại nguồn đã tắt. Retrieval dùng cosine + BM25 RRF, ngưỡng cosine 0.72 thử nghiệm, không phải xác suất đúng đã hiệu chỉnh.

### Sử dụng và hợp đồng

- Teacher: GET `/api/v1/document-versions/{id}/rag` đọc trạng thái; POST cùng `/rag/enable` công bố/cho phép và chuẩn bị (202, idempotent khi đang xử lý/đã sẵn sàng); POST `/rag/disable` thu hồi nguồn; GET `/rag/pages?needs_review_only=true&limit=...&offset=...`; PATCH `/rag/pages/{pdf_page}` nhận `{revision,action:allow|exclude,transcription?}`, revision fingerprint của cả trang, conflict 409. Thao tác trang khi nguồn đang xử lý trả 409. GET `/api/v1/document-versions/{id}/content` là preview riêng của owner teacher. API corpus/chunk/index cũ giữ để tương thích, không còn là luồng giao diện chính.
- Student: POST/GET `/api/v1/course-runs/{id}/chat-sessions`; POST `/api/v1/chat-sessions/{id}/messages` nhận `{message,request_key}` với UUID và tối đa 2000 ký tự. Không nhận role/system_prompt/model/citations từ client. GET cùng `/messages` trả các **lượt hỏi đáp** (`question,answer,status,citations`), có phân trang. Mỗi câu hỏi độc lập, chưa dùng lịch sử làm ngữ cảnh cho câu kế tiếp.
- Gửi lại cùng request_key và câu hỏi trả cùng lượt hỏi đáp; key dùng cho câu khác trả 409. Provider lỗi lưu `provider_error`, retry cùng key cập nhật lượt đó. Một enrollment chỉ có một câu hỏi đang xử lý; pending quá thời gian lease cho phép thử lại, generation ID chặn kết quả cũ ghi đè. Tối đa 8 lượt hỏi mới/phút.
- Run real/active mới được tạo phiên/gửi câu hỏi; closed/synthetic chỉ đọc lịch sử. API kiểm tra lại enrollment/run và nguồn sau khi provider trả lời; không giữ transaction/khóa DB trong lúc gọi mô hình.
- Không đủ nguồn trả `insufficient_sources`, citations rỗng. Provider mất kết nối, JSON sai schema hoặc dẫn ID/quote không thuộc nguồn trả 503. Quote phải là đoạn nguyên văn liên tục trong chunk; trang/version/title được lấy từ server. Nội dung PDF là dữ liệu không đáng tin trong prompt, không có quyền đổi phân quyền hoặc gọi tools. Câu trả lời hiển thị dạng văn bản, không chạy HTML/model instructions.

Kiểm thử `scripts/test_backend.py` bao gồm PostgreSQL, PDF và HTTP server local giả lập hợp đồng Gemini và encoder fixture nhỏ. Fixture này **không phải nghiệm thu chất lượng LLM thật**. Trước demo, cấu hình Gemini key, bấm công bố/dùng cho trợ giảng, kiểm tra nguồn/câu hỏi mẫu; lưu kết quả/citations riêng tại `.local/` hoặc `docs/`, đối chiếu RAG01–RAG07. Bộ mẫu CH02/36 (`lib`), CH03/22 (Row/Column), CH03/68 (LayoutBuilder); chỉ từ chối SQLite/MethodChannel/Isolate khi corpus được phép thực sự thiếu chứng cứ, không coi bộ 3 trang cũ là đánh giá toàn bộ corpus tự động. Sao lưu PostgreSQL và volume PDF cùng nhau; Git không chứa corpus/chat/runtime.

## Tài liệu để bắt đầu code

1. [Học phần mẫu và kiểm tra nguồn](docs/hoc_phan_mau.md).
2. [Quiz nháp 30 câu](docs/quiz_hoc_phan_mau.md).
3. [Thiết kế dữ liệu và ERD](docs/thiet_ke_du_lieu_mvp.md).
4. [Hợp đồng API và màn hình MVP](docs/hop_dong_api_mvp.md).
5. [Sự kiện học tập và công thức đặc trưng](docs/su_kien_va_dac_trung.md).
6. [Tiêu chí nghiệm thu và thứ tự triển khai](docs/tieu_chi_nghiem_thu_mvp.md).
7. [Khảo sát OULAD trước khi code](docs/khao_sat_oulad_truoc_khi_code.md).

Nội dung để seed nằm tại `content/mobile_multiplatform/course_manifest.json` và `quiz_draft.json`. PDF nguồn local nằm ngoài repository ở thư mục học phần đã cung cấp; chưa đưa tài liệu gốc hoặc bí mật lên Git. Quiz đang draft, cần rà soát trước khi công bố.

## Hướng triển khai

FastAPI + SQLAlchemy + Alembic; React + TypeScript + Vite + PDF.js; PostgreSQL; Docker Compose và volume private dành cho PDF. Đã có RAG theo trang PDF, duyệt corpus, citation và xử lý thiếu nguồn/provider; cần cấu hình Gemini key và nghiệm thu câu trả lời trước demo.

OULAD dùng cho thí nghiệm mô hình; điểm quiz theo chủ đề dùng cho lộ trình. Kết quả OULAD không được coi là độ chính xác đã xác nhận trên sinh viên StudyHub. Lượt học mô phỏng phải có provenance riêng.

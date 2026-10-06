# StudyHub

Đồ án: **Xây dựng nền tảng Web học tập trực tuyến tích hợp AI dự báo và cá nhân hóa lộ trình học tập**.

Học phần mẫu: **Phát triển ứng dụng di động đa nền tảng**, 5 PDF Flutter/Dart, 8 chủ đề. Mốc báo cáo: 13/12/2026 với giảng viên hướng dẫn và 31/12/2026 báo cáo tổng.

## Trạng thái

Đã có bản nền móng chạy được: FastAPI, React/TypeScript, PostgreSQL, migration, đăng ký/đăng nhập/logout, phân quyền teacher/student, học phần/lượt học, enrollment và 8 chủ đề mẫu. Giảng viên có thể tạo và mở lượt học, thêm sinh viên theo email; sinh viên xem các lượt học đã được đăng ký và mục tiêu/kiến thức tiên quyết.

Đã bổ sung upload/xem PDF có phiên bản, gắn khoảng trang vào chủ đề, biên soạn và công bố quiz, lưu/khôi phục/nộp bài và chấm điểm ở server. Trình xem PDF.js ghi log mở tài liệu và trang đang hiển thị; log gắn enrollment, thời gian server và provenance để chuẩn bị dữ liệu cho AI. Giảng viên xem kết quả và số lượt xem trang theo sinh viên.

Đã có lộ trình theo kết quả quiz hiện tại, snapshot có revision và báo cáo cho giảng viên; pipeline OULAD và API/giao diện điểm rủi ro thử nghiệm có cutoff, cache, đặc trưng và giải thích SHAP. Chatbot RAG là module tiếp theo. Seed nền móng không tự upload/công bố PDF hoặc quiz nháp. Tài liệu trong `docs/` chỉ có trên máy local, không nằm trong bản clone Git.

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

Kiểm tra hợp đồng đặc trưng OULAD và split (fixture nhỏ, không cần dataset thật):

```powershell
backend/.venv/Scripts/python.exe -m pip install -r ml/requirements-dev.txt
backend/.venv/Scripts/python.exe -m pytest ml/tests -q
```

GitHub Actions có cấu hình test backend với PostgreSQL, build frontend và test hợp đồng ML. Trạng thái chạy CI thực tế xem trong repository GitHub.

## Lộ trình cá nhân hóa

Sinh viên chọn lượt học để xem **Bước học tiếp theo**. Bài hoàn thành mới nhất của quiz đang công bố xác định `weak`/`mastered`; chưa làm là `not_assessed`, chưa có quiz đủ câu là `not_available`. Quy tắc `path_rules_v1` ưu tiên chủ đề yếu, thêm tiên quyết chưa đạt trước, rồi chủ đề chưa đánh giá. Tiên quyết chưa có quiz tạo cảnh báo nhưng không khóa học.

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

Giảng viên vào **Rà soát nguồn cho chatbot**, chọn đúng phiên bản rồi **Trích văn bản PDF**. Corpus chia đoạn trong từng trang PDF, giữ ID/version/trang 1-based và hash. Trích lại cùng version không ghi đè hay nhân đôi. PDF/version cũ và dữ liệu học tập được giữ nguyên khi migration `0004_rag` thêm bảng.

Mọi đoạn mới đều **chờ duyệt**. Đối chiếu với trình xem PDF, loại bìa/mục lục/đoạn sai rồi duyệt từng đoạn nội dung. Trang có ảnh được cảnh báo; mã nguồn trong ảnh chưa phiên chép không dùng để trả lời câu hỏi mã nguồn. Có thể thêm bản phiên chép thủ công theo đúng trang, duyệt riêng và loại đoạn sai trước đó; không sửa văn bản của đoạn cũ. Thu hồi đoạn hoặc lưu trữ PDF sẽ ẩn câu trả lời và trích dẫn liên quan trong lịch sử. Không tự lấy ngân hàng câu hỏi/đáp án quiz vào corpus.

Retrieval v1 dùng **embedding đa ngôn ngữ local + BM25**, bỏ dấu và mở rộng một số cụm tiếng Việt sang thuật ngữ nguồn tiếng Anh. Chỉ tìm đoạn `reviewed/content` trong PDF `published/ready` của học phần đang enroll; tối đa 4 đoạn. Các thuật ngữ như LayoutBuilder phải xuất hiện trong nguồn. Độ đúng của câu trả lời cần đánh giá với mô hình thực tế; kiểm tra ID và quote không tự chứng minh mọi diễn giải của mô hình đều đúng.

### Gemini API và embedding local

Phần sinh câu trả lời dùng **Google Gemini API** theo đề cương. Mặc định chọn `gemini-3.5-flash-lite`; có thể đặt `GEMINI_MODEL` bằng model hỗ trợ structured output còn khả dụng trong project Google AI Studio. Xem [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output) và [bảng giá/free tier](https://ai.google.dev/gemini-api/docs/pricing). Dòng 2.5 bị hạn chế với project mới theo [danh sách model của Google](https://ai.google.dev/gemini-api/docs/models); mặc định 3.5 đã kiểm tra khả dụng. Quota/điều kiện free tier phụ thuộc tài khoản và có thể thay đổi; backend không tự chuyển model hoặc bật gói trả phí. Gemini chỉ nhận câu hỏi + tối đa 4 đoạn đã duyệt; không gửi cả PDF, tài khoản/điểm sinh viên, vector hay ngân hàng quiz. Theo bảng giá Google, dữ liệu free tier có thể được dùng để cải thiện sản phẩm; chỉ dùng tài liệu phù hợp với chế độ này.

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

Sau khi duyệt đoạn, bấm **Lập chỉ mục embedding** cho từng PDF có đoạn đã duyệt. Vector và mã model lưu trong PostgreSQL, gắn chunk/version/trang/hash; lập lại không nhân đôi vector. Thiếu model/vector hoặc model đã đổi => 503 `EMBEDDING_UNAVAILABLE`, cần lập lại chỉ mục. Retrieval kết hợp cosine embedding đa ngôn ngữ với BM25 bằng reciprocal rank fusion (RRF), giữ kiểm tra thuật ngữ và ngưỡng cosine 0.72 thử nghiệm; đây không phải xác suất đúng đã hiệu chỉnh.

### Sử dụng và hợp đồng

- Teacher: POST `/api/v1/document-versions/{id}/corpus`; POST `/api/v1/document-versions/{id}/embedding-index` lập vector các đoạn đã duyệt; GET `/chunks?pdf_page=...&limit=...&offset=...` dưới cùng version; POST `/chunks` để thêm phiên chép `{pdf_page,text}`. PATCH `/api/v1/chunks/{id}` nhận `{revision,kind,review_status}`, trả 409 khi tab dùng revision cũ. GET `/api/v1/document-versions/{id}/content` là preview riêng của owner teacher.
- Student: POST/GET `/api/v1/course-runs/{id}/chat-sessions`; POST `/api/v1/chat-sessions/{id}/messages` nhận `{message,request_key}` với UUID và tối đa 2000 ký tự. Không nhận role/system_prompt/model/citations từ client. GET cùng `/messages` trả các **lượt hỏi đáp** (`question,answer,status,citations`), có phân trang. Mỗi câu hỏi độc lập, chưa dùng lịch sử làm ngữ cảnh cho câu kế tiếp.
- Gửi lại cùng request_key và câu hỏi trả cùng lượt hỏi đáp; key dùng cho câu khác trả 409. Provider lỗi lưu `provider_error`, retry cùng key cập nhật lượt đó. Một enrollment chỉ có một câu hỏi đang xử lý; pending quá thời gian lease cho phép thử lại, generation ID chặn kết quả cũ ghi đè. Tối đa 8 lượt hỏi mới/phút.
- Run real/active mới được tạo phiên/gửi câu hỏi; closed/synthetic chỉ đọc lịch sử. API kiểm tra lại enrollment/run và nguồn sau khi provider trả lời; không giữ transaction/khóa DB trong lúc gọi mô hình.
- Không đủ nguồn trả `insufficient_sources`, citations rỗng. Provider mất kết nối, JSON sai schema hoặc dẫn ID/quote không thuộc nguồn trả 503. Quote phải là đoạn nguyên văn liên tục trong chunk; trang/version/title được lấy từ server. Nội dung PDF là dữ liệu không đáng tin trong prompt, không có quyền đổi phân quyền hoặc gọi tools. Câu trả lời hiển thị dạng văn bản, không chạy HTML/model instructions.

Kiểm thử `scripts/test_backend.py` bao gồm PostgreSQL, PDF và HTTP server local giả lập hợp đồng Gemini và encoder fixture nhỏ. Fixture này **không phải nghiệm thu chất lượng LLM thật**. Trước demo, điền Gemini key, duyệt corpus và lập chỉ mục embedding; lưu câu hỏi/kết quả/citations riêng tại `.local/` hoặc `docs/`, đối chiếu RAG01–RAG07. Bộ mẫu cần CH02 trang 36 (`lib`), CH03 trang 22 (Row/Column), CH03 trang 68 (LayoutBuilder); SQLite/MethodChannel/Isolate thiếu ví dụ phải từ chối. Sao lưu PostgreSQL và volume PDF cùng nhau; Git không chứa corpus/chat/runtime.

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

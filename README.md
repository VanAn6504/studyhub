# StudyHub

Đồ án: **Xây dựng nền tảng Web học tập trực tuyến tích hợp AI dự báo và cá nhân hóa lộ trình học tập**.

Học phần mẫu: **Phát triển ứng dụng di động đa nền tảng**, 5 PDF Flutter/Dart, 8 chủ đề. Mốc báo cáo: 13/12/2026 với giảng viên hướng dẫn và 31/12/2026 báo cáo tổng.

## Trạng thái

Đã có bản nền móng chạy được: FastAPI, React/TypeScript, PostgreSQL, migration, đăng ký/đăng nhập/logout, phân quyền teacher/student, học phần/lượt học, enrollment và 8 chủ đề mẫu. Giảng viên có thể tạo và mở lượt học, thêm sinh viên theo email; sinh viên xem các lượt học đã được đăng ký và mục tiêu/kiến thức tiên quyết.

Đã bổ sung upload/xem PDF có phiên bản, gắn khoảng trang vào chủ đề, biên soạn và công bố quiz, lưu/khôi phục/nộp bài và chấm điểm ở server. Trình xem PDF.js ghi log mở tài liệu và trang đang hiển thị; log gắn enrollment, thời gian server và provenance để chuẩn bị dữ liệu cho AI. Giảng viên xem kết quả và số lượt xem trang theo sinh viên.

Dự báo, lộ trình và chatbot là các module tiếp theo. Seed không tự upload/công bố PDF hoặc quiz nháp. Xem [nhật ký bản nền móng](docs/ban_nen_mong_2026_10_04.md) và [hướng dẫn PDF/quiz/log](docs/pdf_quiz_log.md).

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

Mở lại với `docker compose up -d`. Dữ liệu Postgres và PDF riêng tư nằm trong hai volume `postgres_data`, `pdf_storage`, được giữ khi stop/up. Sau khi sửa mã, dùng script setup hoặc `docker compose up -d --build` để build lại. Migration `0002_learning` bổ sung bảng và giữ dữ liệu nền móng hiện có. Sao lưu database và volume PDF cùng nhau; không dùng `docker compose down -v` nếu muốn giữ dữ liệu.

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

Runner tự tạo database riêng `studyhub_test`, chạy migration và các ca tích hợp auth/course/PDF/quiz/log. Có thể đặt `TEST_DATABASE_URL` khác nhưng tên database bắt buộc kết thúc `_test`; fixture xóa dữ liệu trong database kiểm thử này trước mỗi ca. PDF kiểm thử nằm trong thư mục tạm riêng. Runner/fixture dùng `127.0.0.1` cho PostgreSQL local để tránh độ trễ IPv6 trên Windows.

Build frontend:

```powershell
Set-Location frontend
npm.cmd run build
```

GitHub Actions có cấu hình test backend với PostgreSQL và build frontend. Trạng thái chạy CI thực tế xem trong repository GitHub.

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

FastAPI + SQLAlchemy + Alembic; React + TypeScript + Vite + PDF.js; PostgreSQL; Docker Compose và volume private dành cho PDF. Giai đoạn tiếp theo thêm lộ trình theo quiz, pipeline đặc trưng có cutoff, dự báo OULAD và RAG theo kế hoạch.

OULAD dùng cho thí nghiệm mô hình; điểm quiz theo chủ đề dùng cho lộ trình. Kết quả OULAD không được coi là độ chính xác đã xác nhận trên sinh viên StudyHub. Lượt học mô phỏng phải có provenance riêng.

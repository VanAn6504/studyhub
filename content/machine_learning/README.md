# Nội dung nháp học phần Học máy

- Mã học phần: `MACHINE_LEARNING`; tên: **Học máy**.
- `course_manifest.json`: metadata 6 PDF, hash SHA-256, mục tiêu, điều kiện tiên quyết và khoảng trang của 10 chủ đề. Không phải file import học phần tự động.
- `quiz_draft.json`: 40 câu trắc nghiệm một đáp án, 4 câu/chủ đề; nhập bằng chức năng hiện có tại màn hình soạn quiz. Mọi câu vẫn ở trạng thái draft, cần giảng viên rà soát trước khi công bố.

## Cách sử dụng

1. Tạo học phần bằng mã và tên trên; tạo các chủ đề `ML01`–`ML10` theo manifest.
2. Upload 5 bài giảng gốc trong thư mục local `../../Học máy/` với mã tài liệu `ML_CH01`–`ML_CH05` đúng manifest. `ML_REF01` là sách đọc thêm, không bắt buộc để nhập ngân hàng câu hỏi này.
3. Gắn khoảng trang nguồn vào các chủ đề. Số trang tính từ 1 theo vị trí trang PDF.
4. Mở soạn quiz của từng chủ đề, nhập cùng file `quiz_draft.json`. Trình nhập lọc theo mã chủ đề đang chọn và bỏ qua mã câu hỏi đã có.
5. Kiểm tra đáp án, giải thích và phiên bản PDF, chọn câu hỏi rồi tạo quiz nháp. Xem trước, xác nhận rà soát và công bố khi phù hợp.

Trình nhập hiện tại tìm mã tài liệu và lấy phần tử phiên bản đầu trong danh sách, không kiểm tra hash của manifest. Đối chiếu nguồn nếu tài liệu có nhiều phiên bản. Không dùng script seed học phần mẫu để nạp manifest này khi chưa điều chỉnh và kiểm tra.

## Phạm vi và trạng thái xác minh

10 chủ đề: tổng quan; hồi quy/gradient; cây quyết định; K-NN/đánh giá; SVM/Bayes; ensemble; phân cụm; ANN; học sâu/học tăng cường; GA.

Đã kiểm tra cấu trúc JSON, mã duy nhất, 4 lựa chọn khác nhau, đáp án hợp lệ, 4 câu/chủ đề, trang nguồn thuộc tài liệu và khoảng trang chủ đề, thứ tự tiên quyết, kích thước file dưới 1 MiB. Dữ liệu sau khi ánh xạ như trình nhập đã qua các schema backend `CourseInput`, `TopicInput`, `QuestionInput` với UUID phiên bản giả lập, không ghi database. Chưa thực hiện import hoặc nghiệm thu trên giao diện.

Các slide có thứ tự/thời lượng chương không thống nhất. Không dùng các lỗi thuật ngữ ở chương 3 trang 6–7 (LDA/NMF), chương 3 trang 40 (linkage), chương 2 trang 90 (likelihood) và trang 119 (kết quả Boosting) làm đáp án chuẩn. Câu tính toán được diễn giải từ công thức/ví dụ, không phải sao chép nguyên văn. Bộ câu hỏi này chưa thay thế đề thi tổng kết chính thức.

Hướng dẫn điền chi tiết và bản câu hỏi có đáp án nằm tại thư mục local `../../Học máy/Soan_hoc_phan/`. Các file local đó và PDF gốc không được backup bởi commit này. Không phân phối PDF công khai khi chưa xác nhận quyền; không gửi ngân hàng đáp án cho sinh viên trước khi nộp bài.

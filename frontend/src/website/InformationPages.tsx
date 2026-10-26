import { Link } from './ui'
export default function InformationPage({ page }: { page: 'help' | 'about' | 'privacy' }) {
  if (page === 'help')
    return (
      <article className="site-document">
        <h1>Hướng dẫn học cùng StudyHub</h1>
        <section className="site-panel">
          <h2>1. Tìm học phần và chọn lớp</h2>
          <p>
            Trong Khám phá, tìm bằng tên hoặc mã, xem giới thiệu và điều kiện từng lớp. Tạo tài
            khoản sinh viên và đăng nhập; sau đó bạn vẫn cần xác nhận tham gia.
          </p>
          <p>
            Lớp mở cho phép tham gia trực tiếp. Lớp xét duyệt cần giảng viên chấp thuận; yêu cầu chờ
            không giữ chỗ. Lớp chỉ mời do giảng viên thêm bạn bằng email tài khoản.
          </p>
          <Link to="/courses">Khám phá học phần →</Link>
        </section>
        <section className="site-panel">
          <h2>2. Học theo từng chủ đề</h2>
          <p>
            Vào Học phần của tôi, chọn đúng lớp. Trong chủ đề, mở tài liệu PDF hoặc làm quiz. Sử
            dụng Lưu bài làm trước khi đóng trình duyệt; hệ thống cảnh báo nếu có lựa chọn chưa lưu
            hoặc log chưa gửi.
          </p>
          <p>
            PDF ghi lại lượt mở và trang thật đang xem. Thao tác tìm kiếm, xem tổng quan và lưu vị
            trí tiếp tục học không được tính là hoạt động đọc PDF.
          </p>
        </section>
        <section className="site-panel">
          <h2>3. Xem tiến độ và dùng trợ giảng</h2>
          <p>
            Tiến độ dựa trên chủ đề có quiz hiện hành đã đạt. Chưa có quiz được ghi là chưa đủ dữ
            liệu. Khi giảng viên đổi quiz, tỷ lệ có thể thay đổi.
          </p>
          <p>
            Trợ giảng chỉ dùng nguồn giảng viên cho phép, có dẫn tài liệu và trang. Hãy đối chiếu
            nguồn; khi thiếu chứng cứ, hệ thống có thể từ chối trả lời.
          </p>
        </section>
        <section className="site-panel">
          <h2>Khi không vào được lớp hoặc quên mật khẩu</h2>
          <p>
            Kiểm tra bạn đã đăng nhập đúng email và lớp đã mở. Đăng ký bị vô hiệu cần giảng viên
            kích hoạt lại, không tự tham gia lại để vượt quyền.
          </p>
          <p>
            Liên hệ trực tiếp giảng viên phụ trách theo kênh học tập hiện có. Website chưa có dịch
            vụ email đặt lại mật khẩu tự động, thanh toán hoặc chứng chỉ.
          </p>
        </section>
      </article>
    )
  if (page === 'about')
    return (
      <article className="site-document">
        <h1>Về StudyHub</h1>
        <section className="site-panel">
          <p>
            StudyHub là sản phẩm đồ án tốt nghiệp “Xây dựng nền tảng Web học tập trực tuyến tích hợp
            AI dự báo và cá nhân hóa lộ trình học tập”.
          </p>
          <p>
            Học phần chứa nội dung dùng chung; mỗi lớp có giảng viên phụ trách, ngày bắt đầu, đăng
            ký và kết quả riêng. Giảng viên tổ chức chủ đề, tài liệu PDF, quiz và nguồn trợ giảng.
          </p>
          <h2>Phạm vi AI</h2>
          <p>
            Lộ trình hiện tại sử dụng quy tắc dựa trên kết quả quiz theo chủ đề. Điểm rủi ro là tính
            năng thử nghiệm với mô hình học từ OULAD; độ chính xác chưa được xác nhận trên sinh viên
            StudyHub. Điểm này không quyết định việc đạt chủ đề.
          </p>
          <p>
            Trợ giảng RAG dùng Google Gemini và embedding chạy local. Câu trả lời có thể sai hoặc
            thiếu; nguồn trích dẫn giúp bạn đối chiếu với tài liệu.
          </p>
          <Link to="/help">Xem hướng dẫn sử dụng</Link>
        </section>
      </article>
    )
  return (
    <article className="site-document">
      <h1>Thông tin riêng tư và dữ liệu</h1>
      <section className="site-panel">
        <h2>Thông tin công khai và thông tin riêng</h2>
        <p>
          Catalog chỉ giới thiệu các học phần giảng viên đã công bố. Công bố metadata không công
          khai PDF, quiz, đáp án, chat, email sinh viên hoặc kết quả học tập.
        </p>
        <p>
          Hồ sơ cá nhân và giới thiệu ngắn mặc định riêng tư. Tên giảng viên xuất hiện trên học phần
          công khai do giảng viên phụ trách.
        </p>
        <h2>Dữ liệu phục vụ học tập</h2>
        <p>
          Hệ thống lưu tài khoản, phiên đăng nhập, đăng ký/yêu cầu tham gia, đáp án và kết quả quiz,
          lượt mở/trang PDF, vị trí tiếp tục học và trao đổi với trợ giảng. Giảng viên chỉ quản lý
          học phần và lớp thuộc quyền của mình.
        </p>
        <p>
          Cookie phiên là HttpOnly; các thao tác ghi đã xác thực yêu cầu CSRF. Đổi mật khẩu thu hồi
          các phiên hiện tại. Website dùng mô hình vận hành thử nghiệm trên môi trường được cấu
          hình; đây không phải cam kết kiểm định bảo mật độc lập.
        </p>
        <h2>Dữ liệu gửi tới dịch vụ AI</h2>
        <p>
          Khi hỏi trợ giảng, câu hỏi và một số đoạn nguồn đủ điều kiện được gửi tới Google Gemini.
          Hệ thống không gửi toàn bộ PDF, tài khoản/điểm sinh viên hoặc ngân hàng đáp án quiz trong
          lời gọi này. Không nhập thông tin nhạy cảm không cần thiết vào câu hỏi.
        </p>
        <p>
          Điều kiện xử lý dữ liệu và hạn mức của Google phụ thuộc cấu hình/tài khoản dịch vụ. Trên
          free tier, dữ liệu có thể được dùng để cải thiện sản phẩm theo chính sách của nhà cung
          cấp. Embedding được tính local.
        </p>
        <h2>Xóa tài liệu và hỗ trợ</h2>
        <p>
          Giảng viên xóa tài liệu sẽ xóa file PDF và nguồn RAG liên quan. Điểm, bài làm và log lịch
          sử được giữ để bảo toàn kết quả. Sao lưu do người vận hành quản lý riêng.
        </p>
        <p>
          Để trao đổi về dữ liệu hoặc quyền truy cập, liên hệ giảng viên phụ trách theo kênh hiện có
          của lớp. Website chưa có cổng xử lý yêu cầu quyền dữ liệu tự động hoặc thời hạn lưu giữ
          cấu hình sẵn.
        </p>
      </section>
    </article>
  )
}

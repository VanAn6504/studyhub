export const documentTypeLabels = {
  textbook: 'Giáo trình chính',
  lecture: 'Bài giảng',
  supplement: 'Tài liệu bổ sung',
}
export type DocumentType = keyof typeof documentTypeLabels
export type DocumentSettingsValue = { document_type: DocumentType; show_in_learning: boolean }
export const defaultDocumentSettings: DocumentSettingsValue = {
  document_type: 'lecture',
  show_in_learning: true,
}
export default function DocumentSettings({
  value,
  onChange,
}: {
  value: DocumentSettingsValue
  onChange: (value: DocumentSettingsValue) => void
}) {
  return (
    <>
      <label>
        Loại tài liệu
        <select
          aria-label="Loại tài liệu"
          value={value.document_type}
          onChange={(e) => onChange({ ...value, document_type: e.target.value as DocumentType })}
        >
          {Object.entries(documentTypeLabels).map(([key, title]) => (
            <option key={key} value={key}>
              {title}
            </option>
          ))}
        </select>
      </label>
      <label className="review-confirm">
        <input
          type="checkbox"
          checked={value.show_in_learning}
          onChange={(e) => onChange({ ...value, show_in_learning: e.target.checked })}
        />
        Hiển thị trong thư viện học phần
      </label>
      <p className="muted">
        Loại và thư viện không thay đổi trạng thái công bố, liên kết chủ đề hay quyền làm nguồn trợ
        giảng. Nguồn trợ giảng phải được công bố để sinh viên mở trang trích dẫn.
      </p>
    </>
  )
}

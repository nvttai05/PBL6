# Tìm dữ liệu theo tên mẫu

`hardware` là dữ liệu USB từ thiết bị; `simulation` là demo; `emulation` là
kiểm thử USB bằng thiết bị giả. Mỗi loại có cùng cấu trúc:

```text
hardware/2026-11-06/
  Phien_200707_2026-11-06_20c1efbb3143/
    session/                         Toàn bộ dữ liệu của phiên
      raw.csv
      metadata.json
      events.jsonl
      checkpoint.json
      wire.jsonl
    trials/                          Từng lượt thu
      index.json
      Tai_203529_2026-11-06_c2941e057e24/
        raw.csv
        metadata.json
        summary.json
      Tai_204448_2026-11-06_b8396a74cc66/
      Tai_205405_2026-11-06_3722da93f44e/
      Chua_dat_ten_212227_2026-11-06_ae707239de77/
```

Folder mẫu: **Tên_HHMMSS_YYYY-MM-DD_ID12**. Ví dụ `Tai_203529_2026-11-06_...`
là mẫu Tai, bắt đầu lượt lúc 20:35:29 ngày 06/11/2026 (+07). Ba tên Tai là ba
lượt khác nhau. ID12 là phần rút gọn để folder gọn; UUID đầy đủ vẫn có trong
metadata/raw. Không có tên thì dùng `Chua_dat_ten`; trạng thái COMPLETE/ERROR
và chất lượng xem metadata/summary, không suy từ tên folder.

Lọc folder `Tai_*` để lấy các lượt Tai. Hoặc chạy từ thư mục dự án:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --find-sample Tai
```

`name Tai` sau finish cập nhật metadata và đổi folder bởi writer. Tên gốc giữ
nguyên trong metadata; tên folder giữ dấu tiếng Việt, đổi khoảng trắng/ký tự
không an toàn thành `_`, rút phần tên còn tối đa 32 ký tự. Tên dài hoặc tên
chuẩn hóa giống nhau vẫn được phân biệt bởi ID. Dữ liệu nằm trong raw.csv của
từng lượt là bản tách từ session/raw.csv; mỗi phép đo vẫn giữ nguyên UUID/seq.

Folder phiên dùng thời gian mở chương trình; folder lượt dùng thời gian vào
BASELINE, không phải thời gian nhập name hoặc mẫu dữ liệu đầu tiên. Dữ liệu
cũ đã chuyển folder có ánh xạ tại `runtime/DATA_LAYOUT_MIGRATION.json`.

File `.writer.lock` trong mỗi loại dữ liệu phục vụ khóa chống chạy migration
trong lúc đang ghi. File có thể còn sau khi thoát; sự tồn tại của file không
đồng nghĩa chương trình vẫn chạy.

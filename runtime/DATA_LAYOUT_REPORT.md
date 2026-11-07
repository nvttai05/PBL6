# Đổi cách đặt tên folder dữ liệu — layout v2

Đã triển khai cho dữ liệu mới và chuyển **14 phiên, 18 lượt thu** hiện có
trong hardware/simulation/emulation. Tổng cộng **32 lần đổi tên folder**;
đối chiếu SHA-256 xác nhận **124 file lưu trữ giữ nguyên mọi byte**, gồm cả
raw.csv, metadata, index, summary, events và wire. Không đổi UUID hoặc trạng
thái ERROR/COMPLETE của dữ liệu cũ.

## Cấu trúc đang dùng

```text
data/hardware/2026-11-06/
  Phien_200707_2026-11-06_20c1efbb3143/
    session/...
    trials/
      Tai_203529_2026-11-06_c2941e057e24/
      Tai_204448_2026-11-06_b8396a74cc66/
      Tai_205405_2026-11-06_3722da93f44e/
      Chua_dat_ten_212227_2026-11-06_ae707239de77/
```

Folder lượt theo **Tên_HHMMSS_YYYY-MM-DD_ID12**. Có thể lọc trực tiếp `Tai_*`.
Folder phiên theo **Phien_HHMMSS_YYYY-MM-DD_ID12**: một phiên có thể chứa nhiều
mẫu khác tên, nên tên mẫu nằm ở cấp lượt. Giữ các cấp hardware/simulation/
emulation để nhận biết nguồn dữ liệu; ngày cha là ngày bắt đầu phiên.

Giờ trong folder mẫu là lúc vào BASELINE, ánh xạ UTC+07; không phải thời gian
đặt tên hoặc thời điểm mẫu khí tới cảm biến. Bởi vậy folder Tai thứ nhất là
20:35:29, còn dòng dữ liệu đầu là 20:35:30. Với dữ liệu cũ, thời gian bắt đầu
được khôi phục từ timestamp/mono_s của raw và started_mono_s của trial;
không sửa số đo. Nếu hồ sơ cũ thiếu căn cứ thời gian thì ghi rõ
`Gio_khong_ro_Ngay_khong_ro` thay vì đoán.

ID12 là 12 ký tự hex đầu của UUID; UUID đầy đủ vẫn giữ trong raw/metadata và
giao thức. Trùng prefix thì tăng độ dài lên 20 hoặc 32 ký tự; không ghi đè.
Tên folder giữ dấu tiếng Việt, đổi khoảng trắng/ký tự không an toàn thành `_`
và giới hạn phần tên 32 ký tự. Tên người dùng nhập đầy đủ vẫn nằm trong
metadata; các tên sau chuẩn hóa giống nhau được phân biệt bằng ID.

## Hành vi lưu mới

- Khi start, tạo `Chua_dat_ten_<giờ>_<ngày>_<ID>`.
- `name Tai` trong WAIT_NAME cập nhật metadata và đổi folder thành `Tai_...`.
  Đổi tên lần nữa vẫn giữ thời gian bắt đầu và UUID.
- Chỉ writer đóng/reopen CSV và đổi folder; acquisition/UI/heartbeat tiếp tục
  qua queue. Nếu Windows khóa folder, ghi event `trial_folder_rename_deferred`,
  tiếp tục lưu và thử lại khi có cập nhật metadata hoặc chốt lượt.
- Metadata/index mới có thông tin folder/thời gian để tra cứu. Reader, CLI,
  fixture và auditor hỗ trợ cả layout UUID cũ lẫn layout v2.
- Backend có khóa writer để maintenance không đổi folder lúc đang ghi.
  Phiên PARTIAL/không rõ trạng thái được bỏ qua và báo rõ.

Thay đổi ở chương trình host; không đổi firmware hoặc cơ chế chạy bơm.

## Migration và đường dẫn

[DATA_LAYOUT_MIGRATION.json](DATA_LAYOUT_MIGRATION.json) là journal chính,
gồm từng đường dẫn cũ/mới, 124 hash trước chuyển và kết quả kiểm chứng sau
chuyển. Không có phiên nào bị bỏ qua trong lần chạy này. Công cụ tự rollback
những bước đã thực hiện nếu đổi folder lỗi trong tiến trình; trường hợp dừng
đột ngột vẫn cần xem journal trước khi phục hồi, không hứa transaction chống
mất điện.

Đã cập nhật đường dẫn trong các báo cáo hiện hành và ba fixture/validation
manifest bước 02/03. Bản manifest trước sửa nằm ở
`runtime/layout_reference_backups`; danh sách sửa ở
[DATA_LAYOUT_REFERENCE_UPDATES.json](DATA_LAYOUT_REFERENCE_UPDATES.json).
Log/evidence chẩn đoán gốc được giữ nguyên làm bằng chứng lịch sử; dùng path_map
trong journal khi đối chiếu đường dẫn cũ.

Các tab VS Code mở bằng đường dẫn UUID cũ cần mở lại file ở folder mới.
Ví dụ [metadata của Tai lượt 1](../data/hardware/2026-11-06/Phien_200707_2026-11-06_20c1efbb3143/trials/Tai_203529_2026-11-06_c2941e057e24/metadata.json).

Để hoàn tác lần chuyển này, đóng app thu và chạy:

```powershell
.\.venv\Scripts\python.exe scripts/migrate_data_layout.py --rollback runtime/DATA_LAYOUT_MIGRATION.json
```

Rollback đối chiếu hash và từ chối nếu các file lưu trữ đã thay đổi.

## Kiểm chứng thực hiện

- Test targeted ban đầu: 27 passed; sau đó bổ sung kiểm Windows khóa folder
  và ánh xạ giờ MCU/host vào suite đầy đủ.
- Toàn bộ suite: **113 passed, 1 skipped**, 25.27 s;
  [log](DATA_LAYOUT_FULL_TESTS.txt), [JUnit](DATA_LAYOUT_TEST_RESULTS.xml).
  Skip C++ native như trước do chưa có compiler native; 47 test gốc bước 02
  vẫn đạt. Test chỉ cập nhật cách tìm folder theo UUID trong metadata, giữ
  kiểm so sánh export/raw, pha và pump/sensor initialization.
- Test migration giữ byte, rollback, dữ liệu thay đổi giữa plan/apply,
  folder bị khóa, ngăn path escape/ghi đè, idempotence, Unicode và trùng prefix.
- Lookup CLI trả đúng 3 Tai với đường dẫn mới:
  [log](DATA_LAYOUT_LOOKUP_TAI.txt).
- Demo offscreen với cấu trúc mới: session CLOSED, PWM mô phỏng 0 khi đóng:
  [log](DATA_LAYOUT_DEMO_SMOKE.txt). Demo tạo thêm một phiên mới đã mang tên
  Phien; số 14 ở trên chỉ tính các phiên đã chuyển từ layout cũ.
- Audit schema, reference/Bosch, fixture và source hash/build trước vẫn đạt:
  [log](DATA_LAYOUT_AUDIT.txt). Firmware không đổi trong đợt sửa lưu folder,
  không build/nạp lại hoặc mở serial thật.

Hướng dẫn dùng thường ngày: [data/README.md](../data/README.md).

Xác nhận cuối: [DATA_LAYOUT_VALIDATION.json](DATA_LAYOUT_VALIDATION.json) kiểm
lại đủ 124 hash sau migration, 18 liên kết source_raw đều tồn tại, 3 folder
Tai tìm được, và chạy lại kế hoạch không còn thao tác đổi tên nào.

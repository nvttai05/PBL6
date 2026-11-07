# Chẩn đoán START làm dừng phiên và tắt bơm

Phiên: `data/hardware/2026-11-06/Phien_200707_2026-11-06_20c1efbb3143`.
Lượt 4: `ae707239-de77-4a6b-8999-7e03985d609b`.

Đã xác nhận MCU chủ động chuyển ERROR và ra lệnh PWM 0 ngay sau khi chấp nhận
START. Đã tìm và sửa lỗi tràn phép trừ thời gian trong watchdog USB, phù hợp
với trình tự lỗi này. Log firmware cũ chỉ ghi ERROR chung, không có mã nguyên
nhân nội bộ; vì vậy chưa thể khẳng định tuyệt đối nhánh stop nào đã chạy trên
thiết bị trong sự cố. Bản sửa đã kiểm ở mức phần mềm/build; chưa nạp hoặc đo
trên hardware.

## Bằng chứng từ dữ liệu gốc

[START_FAULT_EVIDENCE.json](START_FAULT_EVIDENCE.json) chứa các frame USB đã
giải mã và SHA-256 của toàn bộ file trong phiên, gồm cả ba lượt Tai trước đó.
Chỉ đọc các file dữ liệu; không sửa trạng thái ERROR hoặc tạo số đo bù.

| Thứ tự | Mốc MCU / dữ liệu | Kết quả |
| --- | --- | --- |
| 1 | PING ACK `2263`, `device_ms=4525984` | MONITOR, PWM 80; heartbeat vẫn nhận bình thường |
| 2 | Mẫu `seq=4528`, kết thúc scan `4527.196 s` | Năm cảm biến valid, BME new_data/gas_valid/heater_stable đều true |
| 3 | START `2264`, `applied_ms=4527216` | Chấp nhận, BASELINE, lượt 4, PWM 80 |
| 4 | ERROR event, `device_ms=4527218` | BASELINE → ERROR, PWM 0; cùng boot ID |
| 5 | Laptop gửi FAULT `2265` sau ERROR | MCU ACK `commanded_off`; lỗi đã xảy ra trước lệnh này |

START được chấp nhận khoảng 21:22:27 ngày 06/11/2026 (+07). Giờ lịch là ánh xạ
host/MCU có độ trễ USB chưa đo; trình tự nguyên nhân dựa trên frame và thời
gian monotonic của MCU. Hai event BASELINE/ERROR cùng ghi effective/processed
`4527216 ms` dù serialization của ERROR đã tới `4527218 ms`.

Lượt lỗi có `rows=0`: dừng trước lần đo thuộc BASELINE đầu tiên. `name=null`
vì chưa tới bước đặt tên. Raw CSV của lượt chỉ có header; summary không thể
đánh giá một lượt hoàn chỉnh. Đây là lỗi kết thúc quy trình, không phải một
bộ dữ liệu Tai hoàn chỉnh bị mất tên. Ba lượt Tai trước vẫn nằm trong ba thư
mục UUID riêng.

## Lỗi trong mã và cách sửa

Trước sửa, `datasetLoop()` lấy `now` trước `commands()`. Trong lúc xử lý START,
event và ACK được đưa vào TX queue; task TX chạy song song có thể ghi
`txProgress` mới hơn `now`. Watchdog sau đó tính `now-progress > 2000` bằng
`uint64_t`. Khi mốc progress mới hơn 1 ms, phép trừ cho
`18446744073709551615`, đủ kích hoạt nhầm nhánh
`usb_task_stalled_or_queue_full` và tắt bơm. Hiện tượng phụ thuộc lịch chạy hai
task, nên có thể xuất hiện sau nhiều lượt thành công.

Cặp số `4527216/4527217` trong reproducer là ví dụ tái hiện xác định, không
phải giá trị txProgress đo được trong log cũ. Log cũ không chứa biến này hoặc
fault_reason nội bộ. Kết luận phân biệt rõ: lỗi phép trừ đã được xác nhận;
việc quy sự cố cụ thể cho nhánh watchdog đó là suy luận có căn cứ.

Đã sửa:

- [runtime.cpp](../firmware/RoboNose_Dataset_S3/runtime.cpp): lấy lại thời gian
  sau xử lý lệnh và snapshot TX progress.
- [time_policy.h](../firmware/RoboNose_Dataset_S3/time_policy.h): bảo vệ phép
  trừ khi timestamp từ task khác mới hơn mốc vòng lặp; áp dụng cho watchdog
  USB/sensor và lease heartbeat trong trial engine.
- Giữ các ngưỡng bảo vệ: USB/sensor stall lớn hơn 2 s, lease 15 s, lỗi sensor
  liên tiếp và queue/output fault vẫn latch OFF. START/NEXT không bật lại bơm.
- Context giữ mã `fault_reason` đầu tiên; host lưu mã đó vào event và lỗi phiên.
  FAULT sau đó không ghi đè nguyên nhân gốc. Field mới tùy chọn, đọc được log
  firmware cũ và giữ CSV schema v1.
- HELLO của bản sửa có `firmware_revision=usb_watchdog_time_order.v1`;
  firmware_version vẫn 3.0.0. Có thể dùng revision để phân biệt bản đã nạp sau
  này; phiên gặp sự cố chưa có revision này.

## Kiểm chứng

- Dùng đúng `python_exe` trong `configs/paths.local.json`.
- Test USB/host liên quan: **44 passed**,
  [log](START_FAULT_TARGETED_TESTS.txt).
- Toàn bộ suite: **98 passed, 1 skipped**, 30.13 s,
  [log](START_FAULT_FULL_TESTS.txt), [JUnit](STAGE03_TEST_RESULTS.xml).
  Skip là chạy C++ native vì chưa có compiler native; không gọi đó là pass.
- C++ mock/test compile bằng Xtensa: thành công,
  [kết quả](stage03/CPP_TEST_RESULTS.json). Mười `static_assert` của
  [test_timing.cpp](../tests/firmware_stubs/test_timing.cpp) đã được compiler
  kiểm trực tiếp: tái hiện phép trừ cũ, timestamp mới hơn, biên 2 s/15 s và
  thời gian trên 32 bit. Các assert runtime của engine/driver chỉ compile,
  chưa thực thi native hoặc trên ESP32.
- Cả hai profile S3 build/link thành công, chỉ compile với core 3.3.12:

| Profile tạm | Program | Static RAM | Kết quả |
| --- | ---: | ---: | --- |
| CDC-on | 353241 byte | 36464 byte | LINK_PASS |
| CDC-off | 357933 byte | 36272 byte | LINK_PASS |

Source SHA-256 đúng với hai build; binary chính của cả hai có revision mới.
[START_FAULT_VALIDATION.json](START_FAULT_VALIDATION.json) ghi hash binary và
xác nhận **18 file của phiên sự cố không thay đổi**, gồm raw/events/wire và
các metadata/summary của bốn lượt. [Audit](START_FAULT_AUDIT.txt) cũng xác nhận
47 test gốc bước 02 đạt, schema/header và fixture mô phỏng cũ được giữ nguyên,
source reference và Bosch không đổi. Profile/log và validation mới nằm trong
`runtime/stage03`; bản profile/log/validation/JUnit trước đợt sửa được giữ tại
`runtime/start_fault/prior_validation`.

Lần build đầu trong sandbox lỗi giải nén `VCRUNTIME140.dll` vào thư mục tạm;
đã chạy lại build bằng quyền cho phép ghi thư mục tạm, dùng nguyên core/toolchain.
Không cài lại môi trường, không mở COM hoặc upload.

## Áp dụng trên thiết bị

Bản sửa cần được **nạp lại vào ESP32** để thay đổi watchdog đang chạy trên MCU.
Hiện chỉ sửa source và build trên laptop. Sketch:
`firmware/RoboNose_Dataset_S3/RoboNose_Dataset_S3.ino`.

Hai cấu hình build là PROVISIONAL_COMPILE_ONLY, không chứng minh flash/PSRAM
hoặc cấu hình USB của board thật. `configs/paths.local.json` vẫn chưa có model
và FQBN board. Chưa nạp firmware, mở COM8, bật tải hoặc chạy lại lượt thật
trong đợt chẩn đoán này. Sau khi nạp đúng cấu hình board đã xác minh, cần kiểm
HELLO revision, lặp START/NEXT nhiều lượt và kiểm các fault thật vẫn tắt bơm.
Đây là phần hardware còn chưa xác minh, không tính vào kết quả mock/build.

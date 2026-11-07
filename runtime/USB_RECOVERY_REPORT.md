# Sửa USB lặp lại và xác nhận OFF sau lỗi ghi

**Báo cáo lịch sử cho revision v2.** Phiên tiếp theo lúc 23:59:35 xác nhận đã
nạp v2 nhưng gặp panic ngắt USB. Bản hiện tại là `usb_irq_handoff.v3`; dùng
[USB_ISR_REPORT.md](USB_ISR_REPORT.md) để xem nguyên nhân mới, kiểm thử và cách
kiểm bản đang chạy. Các số liệu và hướng dẫn v2 bên dưới giữ làm lịch sử.

Đã sửa firmware và host, kiểm phần mềm/build. Chưa nạp hoặc kiểm lại trên
ESP32 thật trong đợt này. Lỗi nguồn/cáp/driver vật lý còn cần kiểm thực tế;
không coi build/mock là bằng chứng đã hết lỗi COM8 ngoài mạch.

## Phiên vừa lỗi

`data/hardware/2026-11-06/Phien_223533_2026-11-06_07632f9005f7`:

- Firmware đang chạy trong log là revision `usb_watchdog_time_order.v1`.
- Lệnh heartbeat PING request 792 trả về **0/64 byte**; emergency ALL_OFF sau
  đó cũng trả về **0/8 byte**. Không phải lệnh recover bị MCU từ chối.
- Lưu 1570 dòng; thiếu seq 475 và 1192, trước đó có mẫu JSON bị cắt/ghép với
  ACK trong MONITOR. Lúc mất USB đang WAIT_RECOVERY, cùng boot ID đã nhận.
- Lượt 1 tên Tai: COMPLETE, 356 dòng. Lượt 2 chưa đặt tên: ERROR, 331 dòng.
  COMPLETE chỉ là quy trình, không phải kết luận quality tốt.
- Trạng thái bơm vật lý của phiên mới chưa được xác nhận với người dùng. Người
  dùng đã báo bơm tắt ở phiên lỗi trước; không áp dụng quan sát đó sang phiên này.

[USB_RECOVERY_EVIDENCE.json](USB_RECOVERY_EVIDENCE.json) giữ các lần write lỗi,
seq gap và hash của 17 file trong hai phiên. Dataset gốc giữ nguyên nội dung.

## Phát hiện và thay đổi

1. Core HWCDC cục bộ có nhánh disconnected dùng FIFO replacement với buffer
   mặc định 256 byte; write lớn có thể bị cắt mà vẫn trả về kích thước yêu cầu.
   Kiểu prefix 256 byte khớp các JSON lỗi quan sát được. Điều này chưa chứng
   minh nguyên nhân làm Windows hủy PING/ALL_OFF. Không sửa file core.
2. Với CDC-on/USBMode=hwcdc, firmware dùng driver USB Serial/JTAG ESP-IDF sẵn
   có thay cho HWCDC. TX 16384 byte, RX 1024 byte; không có hai ISR owner cho
   cùng peripheral. TX giữ offset theo số byte thật được nhận, chunk tối đa
   64 byte, timeout mỗi call tối đa 20 ms và budget frame/drain 1 s. Lỗi báo
   output owner để OFF; LF giúp tách lại frame sau một lần gửi dở.
3. Host giữ handle COM sau write/read fault chỉ để emergency OFF/đọc ACK và
   raw đang trên đường về. Tối đa 3 lần OFF/FAULT cùng request ID, cách 0.1 s,
   trong budget shutdown mặc định 1.5 s. Gửi ký tự hủy `!` rồi LF trước
   emergency để vô hiệu phần lệnh ghi dở; chỉ LF có thể hoàn thiện BEGIN đang
   thiếu newline và làm ON ngoài ý định sau fault. Đã thêm test chặn trường
   hợp này. Không mở lại COM, không gửi BEGIN/PING/lệnh thu sau lỗi.
   Đứt hẳn vẫn ERROR/OFF unconfirmed. Echo host_off không che lỗi ghi gốc.
4. Lệnh info hiển thị revision và transport thực. Chốt trial lỗi khi không có
   event OFF dùng clock MCU đã ánh xạ, đánh dấu `host_shutdown_clock_estimate`,
   không dùng nhầm uptime của Python hoặc giả đó là thời điểm OFF đo được.
   Không sửa lại metadata/raw của phiên cũ.

Revision hiện tại: **`usb_idf_stream_off_ack.v2`**. Firmware version vẫn 3.0.0,
wire và CSV schema v1 giữ nguyên; bản này gồm cả sửa watchdog trước đó.

## Bơm lỏng dây/quá nóng

Người dùng xác nhận bơm **có nguồn riêng**. Điều đó giảm khả năng dòng bơm trực
tiếp kéo sụt nguồn USB, nhưng chưa loại trừ đầu nối/mass/nhiễu hoặc tải nhiệt.
Không có đo dòng, nguồn hoặc nhiệt bơm. BME cuối hai phiên khoảng 32°C và năm
device status đều OK; BME không phải cảm biến nhiệt bơm. Không có frame đổi
boot ID trong phần log nhận được; khi USB mất có thể không nhận được reboot.

Đã đọc log Windows System quanh hai mốc lỗi: không tìm được sự kiện liên quan;
không dùng kết quả đó để khẳng định nguồn/USB không lỗi.
[PUMP_POWER_EVIDENCE.json](PUMP_POWER_EVIDENCE.json),
[Windows events](USB_RECOVERY_WINDOWS_EVENTS.json).

Quy trình kiểm dây/nguồn/nhiệt và so sánh có tải/không tải ở
[USB_POWER_PUMP_DIAGNOSTICS.md](../docs/USB_POWER_PUMP_DIAGNOSTICS.md).

## Kiểm chứng

- Reproducer trước sửa: test 0-byte write thất bại vì không nhận OFF ACK:
  [log](USB_RECOVERY_REPRO_BEFORE.txt). Không đổi kỳ vọng để bỏ lỗi.
  Rà soát thêm bắt được BEGIN thiếu duy nhất newline bị hoàn thiện bởi resync
  cũ; [log trước sửa](USB_RECOVERY_PARTIAL_BEGIN_BEFORE.txt). Đã dùng ký tự hủy
  trước LF và giữ kiểm tra pump_start_count=0.
- Sau sửa: test 0 byte, partial prefix, exception, đứt hẳn, mất ACK OFF đầu,
  giữ nguyên lỗi gốc, info và hủy BEGIN dở đều đạt. Kết quả suite đầy đủ mới
  nhất: **126 passed, 1 skipped**, 27.66 s;
  [log](USB_RECOVERY_TEST_RESULTS.txt), [JUnit](USB_RECOVERY_TEST_RESULTS.xml).
  Có đủ 47 test gốc bước 02. Skip là chạy C++ native do chưa có compiler native.
- C++ engine/driver/transport/framed TX/timing đã cross-compile thành object;
  chưa thực thi native hoặc trên MCU:
  [CPP_TEST_RESULTS.json](stage03/CPP_TEST_RESULTS.json).
- Build/link hai profile tạm dùng core 3.3.12/CLI hiện có:

| Profile | Program | Static RAM | Kết quả |
| --- | ---: | ---: | --- |
| CDC-on/hwcdc | 356393 byte | 36472 byte | LINK_PASS |
| CDC-off/UART | 358861 byte | 36280 byte | LINK_PASS |

ELF CDC-on có symbol usb_serial_jtag_driver_install/read_bytes/write_bytes và
binary có revision/transport IDF mới. Source hash đúng build. Heap/stack/USB
timing thật chưa đo; profile 4M/no-PSRAM không nhận dạng board thật.
[USB_RECOVERY_VALIDATION.json](USB_RECOVERY_VALIDATION.json),
[audit](USB_RECOVERY_AUDIT.txt). Core/source reference/Bosch không bị sửa.
Artifact và log bản trước được giữ ở `runtime/usb_recovery/prior_validation`.

## Áp dụng

Nạp lại sketch `firmware/RoboNose_Dataset_S3/RoboNose_Dataset_S3.ino` với cấu
hình board đã xác minh. Sau đó chạy host hiện tại, dùng đúng COM/loại USB,
đợi MONITOR và nhập `info`:

```text
firmware_revision: usb_idf_stream_off_ack.v2
serial_transport: idf_usb_serial_jtag
serial_ready: True
serial_init_error: 0
```

Các trường trên cần được đọc từ thiết bị sau nạp, chưa được đo trong phiên
thật bởi agent. Nếu còn hiện v1 thì firmware cũ vẫn đang chạy; nếu transport
khác IDF thì kiểm lại đường USB/Tools của board thay vì giả định profile tạm
là cấu hình thật. Chương trình vẫn tự bật PWM80 sau preflight/log hợp lệ;
không thêm bước opt-in bơm. Chưa upload hoặc mở serial thật trong đợt sửa này.

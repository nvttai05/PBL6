# Sự cố PING: MCU panic watchdog ngắt USB — bản sửa v3

Đã xác định MCU phát panic và reset lặp trước lỗi `ACK timeout for PING`.
Phiên này thực sự đã nạp revision v2. Phần bàn giao ngắt USB của v2 còn thiếu
bước dọn enable ngắt kế thừa; đã sửa trong `usb_irq_handoff.v3` và kiểm
phần mềm/build. Chưa nạp hoặc đo lại trên ESP32 thật trong đợt sửa này.

## Bằng chứng từ phiên người dùng thu

Phiên: `data/hardware/2026-11-06/Phien_235935_2026-11-06_8df0399528dc`.
Session UUID: `8df03995-28dc-47b5-8fac-a1923fd5a164`.

- HELLO: `firmware_revision=usb_idf_stream_off_ack.v2`,
  `serial_transport=idf_usb_serial_jtag`, ready=true, init_error=0. Không phải
  trường hợp chưa nạp bản v2. Boot ID `bcde436f8d69428c`.
- Raw có **758 dòng**, seq **71–828 liên tục**, gồm OFF preflight 1 dòng và
  MONITOR 757 dòng; chưa có trial. Mẫu cuối seq 828 ở host mono 757.234 s,
  PWM báo lại 80%. Đây là trạng thái cuối đã nhận, không phải PWM hiện tại.
- Wire dòng **1507**, host mono **758.531 s**, có:
  `Guru Meditation Error: Core  1 panic'ed (Interrupt wdt timeout on CPU1).`
- Host gửi PING request **379** sau đó ở **759.000 s**, retry **759.843 s**.
  MCU đã lỗi trước hai lần PING này. FAULT request 380 được gửi trong shutdown
  nhưng không có OFF ACK. Wire có **sáu** panic và nhiều lần ROM reboot.
- Thời điểm nhận panic đầu xấp xỉ **00:12:14 ngày 07/11/2026, UTC+7**; tính
  theo mốc host, có độ trễ USB chưa đo. Session kết thúc 00:12:17.966.
- Host cũ ghi 186 dòng dump/ROM thành `malformed_or_boot_chatter`. Replay
  offline bằng parser mới nhận đúng sáu `mcu_panic`, giữ byte gốc, không dồn
  toàn bộ backtrace vào event queue. Không sửa metadata lịch sử có lý do
  `ACK timeout for PING` hoặc đổi OFF ACK=false thành true.

Người dùng cho biết nguồn bơm riêng, đã hàn chắc dây nguồn, bơm dừng khi chưa
nóng. Đây là quan sát người dùng, chưa phải số đo nhiệt/nguồn. Với sự cố này,
có bằng chứng lỗi firmware USB; chưa có căn cứ kết luận dây bơm hoặc quá nhiệt
gây dừng. Tác nhân phát sinh USB bus reset vẫn UNKNOWN; chưa đo đường điện
hoặc xác định sự kiện phía Windows gây reset bus.

## Giải mã đúng firmware đã nạp

Dump in `ELF file SHA256: 8708bee49`. Đã tìm ELF trong Arduino IDE cache,
SHA-256 đầy đủ:

```text
8708bee4944ba2f31f758697c8a7b363fa202e9beae70c68e5fe008bb0193887
```

Đã lưu bản sao ELF/options tại `runtime/usb_isr/incident/`; không dùng ELF
build tạm có địa chỉ khác để quy nguyên nhân. Xem
[backtrace giải mã](USB_ISR_BACKTRACE.txt),
[disassembly ELF sự cố](USB_ISR_DISASSEMBLY.txt),
[dump console tách từ wire](usb_isr/incident/console_dump.txt).

| Bằng chứng | Ý nghĩa |
| --- | --- |
| PC 0x42015d3a / 0x42015c44 | `usb_serial_jtag_isr_handler_default` |
| PC 0x42015c41 | đọc `USB_SERIAL_JTAG.int_st` |
| A2=0x200, A7=0x60038000 | trạng thái ngắt BUS_RESET tại peripheral USB |
| ISR chỉ nhánh 0x4 và 0x8 | nhận RX và gửi TX; không xử lý/xóa 0x200 |
| Stack reboot có `usb_serial_jtag_driver_install` | có lần panic xảy ra ngay khi cài lại driver |

Disassembly ELF khớp và header SDK đang cài cùng xác nhận bit BUS_RESET=1<<9.
Driver chỉ xử lý RX/TX, trong khi install bật thêm RX mà không loại enable
ngắt kế thừa. Bit BUS_RESET còn bật và pending có thể kích ISR liên tục mà
không được xóa, dẫn đến watchdog ngắt CPU1. V2 chưa bảo đảm điều kiện bàn giao
này. Đối chiếu thêm [source driver chính thức ESP-IDF v5.5.5](https://raw.githubusercontent.com/espressif/esp-idf/v5.5.5/components/esp_driver_usb_serial_jtag/src/usb_serial_jtag.c).
SDK cục bộ ghi `esp-idf: v5.5.5 b774170ff46`; không thay SDK/core.

Cache ELF cũng giữ bộ Tools USBMode=hwcdc, CDCOnBoot=cdc, CPUFreq=240,
FlashMode=qio, FlashSize=4M, PSRAM=disabled, PartitionScheme=default. Đây là
cấu hình **đã build quan sát được**, chưa chứng minh bộ nhớ/model vật lý.
`configs/paths.local.json` tiếp tục giữ board UNKNOWN; không tự điền theo cache.

## Các thay đổi

1. Firmware `serial_transport.cpp` và `usb_irq_policy.h`: kiểm owner, bật clock
   peripheral, snapshot enable/pending, tắt enable kế thừa trước khi cài IDF.
   Xóa pending ngoài RX/TX, **giữ pending RX/TX** cho lần truyền đầu. Sau cài
   chỉ cho phép các ngắt driver sở hữu (mask 0xC). Không sửa driver SDK.
2. HELLO/info thêm trạng thái bàn giao ngắt. Host v3/IDF yêu cầu snapshot có
   RX, không có bit ngoài 0xC và diagnostics hợp lệ trước BEGIN. Snapshot là
   mốc khởi tạo; TX runtime có thể thay enable nên không phải số đo live.
3. Host nhận diện console panic/brownout/assert/heap corruption ngay khi đọc,
   giữ lý do MCU và thử OFF có giới hạn trên handle hiện tại. Không đợi lỗi
   PING che nguyên nhân ban đầu; không tự reconnect/BEGIN hoặc bật lại bơm.
4. Giữ các sửa v1/v2: watchdog thời gian có thứ tự, TX chunk/deadline, xử lý
   partial write và OFF ACK. Giữ pha, PWM80, terminal/dashboard, UUID và raw.
   Không tăng timeout watchdog hoặc bỏ chính sách dừng khi lỗi.

## Kiểm chứng thực hiện

Lệnh dùng trực tiếp `python_exe` trong `configs/paths.local.json`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -ra --junitxml=runtime/USB_ISR_TEST_RESULTS.xml
.\.venv\Scripts\python.exe scripts/check_firmware_tests.py
.\.venv\Scripts\python.exe scripts/build_stage03.py --profile cdc_on
.\.venv\Scripts\python.exe scripts/build_stage03.py --profile cdc_off
.\.venv\Scripts\python.exe scripts/stage03_audit.py --test-results runtime/USB_ISR_TEST_RESULTS.xml
.\.venv\Scripts\python.exe runtime/usb_isr/analyze_incident.py
```

- Python: **139 passed, 1 skipped**, gồm đủ **47 test bước 02**. Thêm kiểm
  panic chia chunk/truncated JSON, log lỗi ưu tiên, shutdown mock và từ chối
  BEGIN khi mask ngắt v3 sai. [Log](USB_ISR_TEST_RESULTS.txt),
  [JUnit](USB_ISR_TEST_RESULTS.xml).
- C++: mock object cross-compile thành công; compiler thực thi các
  `static_assert` policy ngắt với mask BUS_RESET/0x20C/all-mask/clean boot.
  Không có compiler C++ native nên chưa chạy các test C++ runtime; đây là
  lý do một test skip. [Log](USB_ISR_CPP_TESTS.txt).

| Build/link provisional v3 | Program | Static RAM | Kết quả |
| --- | ---: | ---: | --- |
| CDC-on, IDF USB Serial/JTAG | 356761 byte | 36488 byte | LINK_PASS |
| CDC-off, UART | 359117 byte | 36296 byte | LINK_PASS |

Các profile vẫn PROVISIONAL_COMPILE_ONLY; không phải xác nhận board vật lý.
BIN cả hai có revision v3; CDC-on có marker IDF. Source hash khớp profile đã
link; Bosch/reference và raw bước 02 giữ nguyên. Đối chiếu **5 file phiên
mới**, **17 file hai phiên lỗi cũ** và core HWCDC không đổi. ELF/log v2 đã
được lưu riêng tại `runtime/usb_isr/prior_v2` trước build mới.

[Evidence](USB_ISR_EVIDENCE.json) giữ hash, timeline, replay và đúng ELF;
[validation](USB_ISR_VALIDATION.json) giữ kết quả/hash artifact;
[audit tổng hợp](stage03/VALIDATION.json) kiểm các nguồn/fixture liên quan.

## Áp dụng lên thiết bị

Nạp lại [sketch hiện tại](../firmware/RoboNose_Dataset_S3/RoboNose_Dataset_S3.ino)
bằng bộ Tools đã dùng cho thiết bị ở lần nạp hiện tại. Đóng Serial Monitor,
chạy host hiện tại bằng lệnh cũ (COM8 nếu cổng vẫn là COM8):

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --port COM8 --serial-kind native-cdc
```

Chương trình vẫn tự PWM80 sau handshake/preflight/log hợp lệ. Khi MONITOR,
nhập `info` và kiểm các trường dự kiến trên đường native:

```text
firmware_revision: usb_irq_handoff.v3
serial_transport: idf_usb_serial_jtag
serial_ready: True
serial_init_error: 0
serial_irq_owned_mask: 12
serial_irq_enabled_after_init: 4
```

Mask enabled sau init thường 4; phải có RX và không có bit ngoài 12. Host mới
kiểm điều kiện này. Trường before/pending có thể khác giữa các lần boot.
Nếu vẫn v2 thì firmware trên board chưa cập nhật. Sau nạp cần kiểm lại MONITOR
đủ lâu (ví dụ 30 phút) và một lượt đủ pha; đây là kiểm thực tế còn chờ, chưa
thực hiện hoặc bảo đảm đạt. Mọi log lỗi mới tiếp tục lưu nguyên trạng.

Agent không mở COM thật, upload hoặc chạy tải trong đợt sửa này. Không suy
OFF ACK=true từ việc bơm dừng, và không coi build/mock là kết quả đo hardware.

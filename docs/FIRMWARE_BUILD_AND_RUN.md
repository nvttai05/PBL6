# Build firmware dataset ESP32-S3

Sketch mới: `firmware/RoboNose_Dataset_S3/RoboNose_Dataset_S3.ino`, firmware 3.0.0, host 0.3.0. Reference ControlTest giữ nguyên ở `stage03_input/reference_s3/RoboNose_ControlTest_v2_1`; không dùng firmware/protocol A2 TGS cũ để thu dataset A0 TGS mới.

## Profile hiện tại

Arduino CLI 1.5.1/core 3.3.12 đã có; không cài dependency/core mới, không dùng PlatformIO fallback. CLI `board listall`/`board details` xác nhận generic `esp32:esp32:esp32s3` và options CDCOnBoot `cdc/default`, USBMode `hwcdc/default`, FlashSize `4M/8M/16M/32M`, PSRAM `disabled/enabled/opi`.

**Board thật UNKNOWN.** Hai profile `PROVISIONAL_COMPILE_ONLY` dùng USBMode=hwcdc, FlashSize=4M, PSRAM=disabled, PartitionScheme=default, lần lượt CDCOnBoot=cdc và default. Không điền các giá trị này thành cấu hình của board thật.

```powershell
.\.venv\Scripts\python.exe scripts/build_stage03.py --profile cdc_on
.\.venv\Scripts\python.exe scripts/build_stage03.py --profile cdc_off
```

Script dùng Arduino CLI từ paths.local.json, chỉ `compile` với build/output path riêng và không có port/upload flag. Argv/options/core/exit code/source SHA-256 lưu tại `runtime/stage03/profile_cdc_*.json`; log ở `build_cdc_*.log`; ELF/BIN ở `runtime/stage03/artifacts/cdc_on` và `cdc_off`. Mức sử dụng bộ nhớ thực nằm trong STAGE03_REPORT.md.

Bản hiện tại có HELLO `firmware_revision=usb_irq_handoff.v3`, gồm sửa
watchdog, đường USB native và bàn giao ngắt USB. CDC-on/USBMode=hwcdc dùng driver ESP-IDF sẵn có,
TX 16384 byte/RX 1024 byte, không đi qua nhánh HWCDC có thể cắt JSON khi mất
trạng thái connected. CDC-off vẫn dùng UART. Không đổi core/toolchain.

Cần nạp lại sketch với cấu hình board đã xác minh, sau đó chạy host mới và
nhập `info` khi đã vào MONITOR. Đường native đã sửa phải hiện revision trên
và `serial_transport=idf_usb_serial_jtag`. Nếu hiện Arduino USB-OTG hoặc UART,
đó là đường build khác; kiểm lại Tools/loại kết nối của board. Không dùng
profile 4M/no-PSRAM tạm làm cấu hình board thật. Chỉ sửa source/build trên
laptop chưa thay firmware trên thiết bị. Chi tiết tại
`runtime/USB_ISR_REPORT.md`.

V3 dọn enable ngắt kế thừa trước khi cài driver RX/TX, loại BUS_RESET 0x200
khỏi ISR không xử lý nó, giữ pending RX/TX để không mất lượt truyền đầu.
Không sửa SDK/core hoặc tăng/bỏ watchdog. `info` cần hiện revision v3,
`serial_irq_owned_mask=12` và `serial_irq_enabled_after_init` thường bằng 4;
host từ chối BEGIN nếu snapshot có bit ngoài 12 hoặc thiếu RX. Đây là snapshot
lúc khởi tạo, không phải đo trạng thái ngắt hiện tại. Các trường before/pending
có thể khác nhau giữa các lần boot.

Phiên người dùng thu lúc 23:59:35 đã nạp v2 và ghi panic watchdog ngắt USB.
ELF cache Arduino IDE có SHA trùng dump cho thấy Tools đã build USBMode=hwcdc,
CDCOnBoot=cdc, FlashSize=4M, PSRAM=disabled. Đây là cấu hình build quan sát được,
chưa xác minh model/kích thước bộ nhớ vật lý. Khi nạp v3, giữ bộ Tools đã dùng
cho thiết bị hiện tại; không tự đổi sang profile tạm chỉ vì build thử đạt.

Đã đối chiếu header core cục bộ: LEDC 3.x dùng pin, bool attach/write; lỗi giữ OFF/not-ready. Hai bus TwoWire timeout 50 ms. Tham khảo [Arduino CLI compile](https://arduino.github.io/arduino-cli/1.5/commands/arduino-cli_compile/), [LEDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html), [I2C](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html).

## Ownership

| Thành phần | Vai trò |
| --- | --- |
| setup/control loop | OFF sớm; phase/deadline/lease/output; không gọi USB read/write trong loop |
| sensor task | Một owner cả hai bus; ADS A0→A3/config trước-sau conversion; Bosch forced/readback; không điều khiển output |
| RX task | Driver USB native hoặc UART; framing; normal queue 8; mailbox OFF riêng |
| TX task | Queue 4 frame <8192 byte; chunk tối đa 64 byte; budget gửi/drain 1 s; lỗi báo control để OFF |
| serial worker host | Một owner COM; giữ handle để thử OFF/đọc ACK có giới hạn sau lỗi; không reconnect/resume |
| controller/writer/analysis host | Projection state MCU; raw/events/meta/wire một writer; analysis đọc export đã đóng |

Sketch không tự pin task vào core. Full frame staging của control ở static storage, tránh đặt frame 8 KiB lên loop stack 8 KiB. RX tách task vì UART RX/TX core dùng chung mutex; tick/OFF không chờ mutex đó. Stack/queue chưa có high-water/soak benchmark thật.

Bosch C/header/LICENSE/provenance copy sau khi kiểm SHA-256, vendor không sửa. Requested heater °C khác readback register. ADS lỗi ghi bus/address/stage/Wire code; lỗi một kênh không bỏ kênh khác. ERROR/STALE null, ADC_LIMIT giữ raw và invalid, không xóa/sửa đỉnh suspect. Chưa đo nguồn/ADC/BME hay thời gian OFF thật.

Firmware boot/reset OFF không thay thế kiểm gate pull-down/cực tính/diode/nguồn/brownout trên mạch. Không có RPM/airflow/valve position feedback. Build/link không xác nhận hardware đã chạy.

## Demo, test, emulator

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo
.\.venv\Scripts\python.exe scripts/stage03_fixture.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_firmware_tests.py
```

Demo không import/mở serial. Fixture mode EMULATED ghi dưới `data/emulation`; không phải dữ liệu ADC/BME. Default tests không mở COM/GPIO. TSV `fixtures/stage03_phases.tsv` gồm 116 bước dùng chung Python/C++. Nếu không có g++/clang++ native, chỉ cross-compile mock/test thành object và ghi COMPILE_ONLY; không gọi đó là chạy C++ hoặc parity native.

## Chạy hardware ở bước sau

Chưa chạy lệnh hardware trong bước 03. Cần model/ký hiệu module, flash/PSRAM, USB native/bridge, Tools đã nạp thành công và wiring. COM3 ở inventory bước 01 là Intel SOL, chưa xác nhận ESP.

```powershell
# Thay placeholder bằng cổng/loại USB đã xác minh:
.\.venv\Scripts\python.exe -m robonose_s3 --port COM_THUC_TE --serial-kind native-cdc
# Chọn --serial-kind uart nếu cổng đã xác minh là USB-UART bridge.
```

**Chương trình hardware tự command PWM 80% sau handshake + preflight + log/sync hợp lệ.** Không thêm lệnh bật bơm riêng. Terminal/WAIT giữ nguyên; MCU sở hữu pha. DTR/RTS false trước open, không chủ động toggle reset/nạp. Driver Windows/bridge có gây xung khi mở hay không vẫn cần đo thực.

Đóng Serial Monitor/app khác trước khi thu. Không tự mở từng COM để đoán; không fallback demo khi handshake sai. Lỗi latch OFF, không reconnect/resume. MCU đã latch cần reset và kiểm readiness; sau quit sạch dùng HELLO ticket/session UUID mới, sensor không reinit giữa trial.

**Chưa upload.** Mẫu lệnh điều kiện cho bước nạp đã được yêu cầu sau khi xác minh board:

```powershell
# & <arduino_cli_exe> upload --fqbn <FQBN_VA_OPTIONS_DA_XAC_MINH> --port <CONG_THAT> firmware/RoboNose_Dataset_S3
```

Không dùng profile generic làm bằng chứng board có 4 MB flash hoặc không PSRAM. Xem `runtime/STAGE03_BOARD_READINESS.json`.

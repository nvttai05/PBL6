# Prompt bước 03 — firmware dataset ESP32-S3 và SerialDevice

Người dùng đã duyệt kế hoạch và hoàn thành bước 02 với báo cáo 47 test phần mềm đạt. Hãy tiếp tục triển khai code trong workspace Windows hiện tại. Giao source chạy/build được và kết quả thực, không chỉ tạo kế hoạch.

## A. Đọc source và giữ mốc đã đạt

1. Đọc AGENTS, `configs/project_target.json`, `configs/paths.local.json`, schema/command-state docs, source package `robonose_s3`, test hiện có và `runtime/STAGE02_REPORT.md`. Đọc implementation thực trước khi thiết kế adapter; báo cáo không thay source.
2. Source tham chiếu mới: `stage03_input/reference_s3/RoboNose_ControlTest_v2_1`. Đọc `REFERENCE_SOURCE.json`, manifest, firmware `RoboNose_SensorTest`, Bosch provenance/license, ADS/PWM/command parser và các test liên quan. Dùng làm tham chiếu, không sửa bản nguồn hoặc chạy app cũ trên thiết bị.
3. Nếu `legacy_s3_source` đang null, ghi đường dẫn tham chiếu đã xác minh vào cấu hình/inventory kèm vai trò reference; nếu đã có source khác thì đọc/đối chiếu, không ghi đè lựa chọn. Source Pi còn thiếu ghi NEEDS_INPUT, không ngăn triển khai phần mới từ đặc tả.
4. Giữ demo và các test bước 02. Cập nhật mốc công việc trong AGENTS/target spec cho bước firmware/USB; không thay yêu cầu A0/PWM80/terminal/WAIT. Dùng Python .venv đã có, không đổi dependency/core/ExecutionPolicy chỉ để bắt đầu lại.

## B. Phần cứng và quy trình đích

| Mục | Đích đã chốt |
| --- | --- |
| A0 | **TGS2602**, thay MQ135 #1 |
| A1/A2/A3 | MQ3 #1 / MQ135 #2 / MQ3 #2 |
| ADS1115 | 5 V, 0x48, single-shot single-ended, FSR ±6.144 V/gain 2/3, 128 SPS, count ×0.0001875 V; không chia áp/nhân đôi |
| Bus ADS | GPIO10 SDA / GPIO11 SCL, qua BSS138 |
| BME688 | GPIO8 SDA / GPIO9 SCL, 3.3 V, 0x77 ưu tiên, 0x76 dự phòng |
| Profile bring-up BME | Forced, 300°C/100 ms, T2/H2/P4; requested/applied/readback có version; profile Pi là cấu hình khác |
| Bơm | GPIO5 qua MOSFET, PWM 1 kHz/10 bit khởi điểm; chương trình thu hardware tự chạy **80%** sau kết nối/log/preflight |
| Van | GPIO4; ON/B=SAMPLE, OFF/A=FILTERED_AIR |
| Lưu và xem | Laptop qua USB, 1 Hz, terminal + dashboard song song |

Giữ đủ state/commands và semantics bước 02. `start`: baseline 60 s → WAIT_EXPOSURE. `expose` mới bắt đầu exposure 120 s → WAIT_RECOVERY, vẫn SAMPLE. `recover` mới đổi van về lọc và đếm recovery 60 s → WAIT_FINISH. `finish`, `name Mau1`, notes tùy chọn, `next` → MONITOR rồi chờ `start`. Bơm giữ 80% xuyên WAIT/name/next. Quit/đóng app/Ctrl+C/lỗi phiên dừng bơm và về lọc. Extend tạo segment riêng. Hết giờ không tự bắt đầu pha tiếp.

Thay A2→A0 của bản tham chiếu phải đồng bộ sensor ID, config/profile, hello, sample, schema mapping, app cards/CSV, fixture/tests. Không chỉ đổi nhãn dashboard. Không thêm ppm/Rs hoặc coi trạng thái GPIO là lưu lượng/vị trí cơ khí đã đo.

## C. Giao thức USB và một owner trạng thái

Thiết kế và ghi đặc tả wire protocol có version, giới hạn kích thước và framing; có thể tái sử dụng flat JSON writer/strict parser nguồn nếu phù hợp. Không giả định ControlTest 2.1 là protocol dataset mới.

- Handshake có firmware/protocol/schema version, boot/device ID, channel map, gain/LSB/divider, I2C pins/address, heater/profile, output-ready, trạng thái OFF lúc kết nối và reset reason nếu lấy được.
- Host từ chối firmware cũ/sai mapping trước khi tự yêu cầu PWM80. Ghi lỗi cụ thể; không có fallback mô phỏng trong hardware.
- Request ID/session ID/trial ID/context epoch và ACK accepted/rejected/reason/state; retry cùng request không tạo lượt/marker hoặc ON pulse trùng. Chống áp lệnh cũ sau reboot/session thay đổi. ALL_OFF/OFF ưu tiên không bị chặn bởi log queue hoặc quy tắc chống lặp.
- Sau handshake và log/health sẵn sàng, chương trình thu tự bắt đầu session và PWM80/MONITOR. Không thêm nút Start Session hoặc yêu cầu bật bơm riêng. Mở Serial Monitor chỉ xem không tự chạy bơm; MCU boot/reset đầu ra OFF.
- Lệnh start/expose/recover/extend/finish/abort/next được MCU xác nhận đúng pha. MCU là owner phase/deadline trong hardware. Name/notes là metadata host, nhưng state naming/between và nhãn mẫu phải tương thích semantics bước 02; ghi rõ cách phối hợp, không để host tự tạo lịch pha thứ hai.
- Telemetry phát cả khi MONITOR/WAIT/name/between; chứa boot/seq/time, context lúc bắt đầu scan, thời gian từng sensor, errors/fresh/valid và commanded outputs. Phase event có thời điểm hiệu lực deadline và thời điểm xử lý. Mẫu in-flight giữ context gốc, không lấy lúc host nhận làm nhãn đo.
- UI dùng snapshot báo lại; sample cũ tới sau ACK không được kéo trạng thái hiện tại lùi về pha/output cũ. Raw mẫu đó vẫn giữ đúng context nguồn.
- Host ghi bytes/frames gốc và event parser; boot chatter không bị ghi như mẫu hợp lệ. Frame hỏng/thiếu/quá dài/trùng/out-of-order/reset phải có quy tắc và test. Null/flags/count/voltage/timing theo schema đã công bố.
- Quy định rõ request được gửi/nhận/áp dụng, phase start và ánh xạ monotonic MCU với wall-clock host. Deadline không phụ thuộc nhảy giờ Windows; không hứa timestamp nhận là thời điểm khí tới sensor.

Ưu tiên giữ hợp đồng CSV dataset bước 02; nếu cần thêm trường thì version/schema adapter có tài liệu và test. Không âm thầm sửa ý nghĩa cột đã có.

## D. Firmware mới

Tạo sketch riêng, ví dụ `firmware/RoboNose_Dataset_S3/RoboNose_Dataset_S3.ino`. File ino có entry setup/loop thật; tách module sensor, timing, trial engine, protocol, output supervisor và config. Không sửa bản ControlTest tham chiếu.

- Kế thừa Bosch vendor C và LICENSE/provenance; kiểm SHA-256 trước dùng và ghi nguồn. Giữ readback, status/index, fresh vs gas-valid; không sao chép mẫu cũ khi no-new-data. Pa→hPa một lần.
- ADS: một owner bus/ADC, A0→A3, count và voltage cùng conversion; kiểm config/MUX/PGA/rate trước/sau, timeout hữu hạn, giữ signed count và lỗi từng kênh. Chẩn đoán nên ghi rõ bus/address/stage/Wire error code, không chỉ một chuỗi i2c_write_failed chung.
- Hai bus riêng. Pin/tốc độ/timeout cấu hình rõ, kiểm API theo core 3.3.12 đang có. PWM dùng API LEDC đúng core, kiểm lỗi attach/write; nếu output init lỗi phải giữ OFF/not-ready.
- Đọc/chờ sensor, serialize/USB và xử lý lệnh không được chặn OFF hoặc deadline lâu. Có thể dùng sensor state machine hoặc task/queue hữu hạn, một owner I2C và một owner output/trial; ghi rõ ownership và snapshot context. Không tự pin core hoặc tăng buffer để che writer/TX treo.
- Lịch scan theo monotonic 64-bit, không tạo mẫu bù giả. Ghi lag/skipped và scan/control-change flags nếu có ranh giới pha giữa phép đọc.
- Boot OFF; BEGIN/session sau handshake/host log-ready mới ON80. Không reinit heater/readers hoặc ON lại ở finish/name/next. Không có kick-start 100% ẩn hoặc tự chọn duty khác.
- Heartbeat/lease ban đầu tham chiếu 15 s của test cũ; chỉ host khỏe cả receive/write/sync mới gia hạn. Invalid command không kéo dài lease. Mất lease, lỗi đầu ra hoặc lỗi phiên dừng/latch; heartbeat phục hồi không tự bật lại.
- OFF không phụ thuộc TX/log queue còn chỗ; sensor/USB task lỗi phải được nhận diện. Phần cứng kéo gate OFF khi reset vẫn là điều kiện cần xác minh thực, không suy từ unit test.

## E. Host SerialDevice và tích hợp app

- Viết adapter theo interface phần cứng/telemetry thực; đọc schema/device API đã có trước khi sửa. Một worker sở hữu COM. Import/open serial chỉ khi chọn backend hardware; đường demo vẫn không import/mở Serial theo guard bước 02.
- Bổ sung cách chọn hardware rõ ràng, ví dụ `--port COMx`; giữ `--demo`. Không chọn COM3 Intel SOL làm mặc định hoặc thử mở từng COM để đoán. Serial options/native CDC/UART và DTR phải là cấu hình có lý do, không tự bấm reset/nạp.
- Khi chạy chương trình thu hardware, tự handshake/preflight/log-ready rồi yêu cầu PWM80 và MONITOR; không cần lệnh bật bơm riêng. Terminal control gửi request, chỉ ACK/telemetry MCU quyết định phase/state, không tự gán thành công trước ACK.
- Logger/quality/dashboard dùng pipeline hiện có; raw ghi context device, không context UI. Nhận/parse/command/write/analysis không chặn nhau. Giữ console dễ gõ, UI zoom/pause không dừng raw.
- Lỗi handshake, ACK timeout/mismatch, reset, mất sensor/receive kéo dài, disk/queue/sync fail làm fault latch/OFF, ghi ERROR/PARTIAL và không resume trial hoặc tự ON sau reconnect. Tách một lần gas-invalid/drift warning khỏi lỗi giao tiếp nghiêm trọng theo chính sách có config.
- Quit/Ctrl+C/GUI-close gửi OFF ưu tiên, chờ ACK hữu hạn và báo rõ nếu chưa xác nhận; hoàn tất log không vô hạn. ACK chỉ xác nhận commanded state, không được gọi là đo bơm đã dừng cơ khí.

## F. Test, fixture và compile

1. Giữ và chạy suite bước 02 sau khi thay đổi phần chung; bổ sung tests ở nhóm có thay đổi. Không đổi kỳ vọng chỉ để bỏ qua lỗi sản phẩm.
2. Fake serial/byte transport: handshake đúng/sai firmware/mapping/FSR, split/oversized/malformed frames, boot chatter, gap/trùng/reordered/old snapshot, reboot, request retry/ID reuse, ACK timeout/khác state và shutdown thiếu ACK.
3. Chạy session nhiều trial bằng device emulator/transport giả trong khi logger/dashboard hiện có tiếp tục hoạt động. Kiểm raw/null/units/timing/route/trial IDs, name/notes/next không reset PWM và không ghi đè. Không ghi emulator là ADC/BME thật.
4. Fixture phase/command/deadline phải dùng lại được giữa mô hình Python và trial engine firmware. Nếu có compiler host thì chạy C++ native parity và ghi output. Nếu chỉ có Xtensa cross-compiler, ghi compile-only, không tuyên bố đã chạy C++ trên host.
5. Driver mocks từ source tham chiếu có thể tái sử dụng và mở rộng cho mapping A0/TGS, I2C errors, BME freshness và LEDC core 3.x; cập nhật theo implementation cuối. Test watchdog/off independent queue, no auto-restart và command bounds.
6. Build bằng Arduino CLI thực đã tìm thấy trong paths.local.json. Giữ core đang cài, chưa cài/chọn core khác. Đọc board listall/details để lấy FQBN/options có thật. Không dùng PlatformIO làm fallback.
7. Nếu chưa biết bo thật: có thể compile/link smoke với generic ESP32-S3 FQBN do CLI xác nhận, CDC on/off nếu core hỗ trợ. Lưu profile `PROVISIONAL_COMPILE_ONLY` và build log, core/toolchain/options/RAM/flash usage. Không ghi flash/PSRAM/FQBN của bo thật bằng giá trị generic. Không upload hoặc mở Serial trong bước chuẩn bị này.
8. `arduino-cli compile` không dùng `--upload`/`-u`. Object compilation hoặc API-shaped stubs không thay build/link đầy đủ. Ghi đúng phần nào thực chạy, phần nào chưa có toolchain/hardware.
9. Nếu build/test fail thì sửa phần được phép và chạy lại kiểm liên quan. Không tuyên bố completed khi còn lỗi build của profile đã chọn; báo giới hạn cụ thể nếu thiếu board/toolchain ngăn xác minh thêm.

## G. Đầu ra và báo cáo

Giao firmware mới, SerialDevice, protocol docs, test/emulator và build profiles/log. Tạo:

- `docs/USB_PROTOCOL.md`, `docs/FIRMWARE_BUILD_AND_RUN.md`, cập nhật schema/commands nếu cần.
- `runtime/STAGE03_REPORT.md`, test log/JUnit và build log/profile thực.
- `runtime/STAGE03_BOARD_READINESS.json`: bo/USB/port/flash/PSRAM nào đã biết, nguồn bằng chứng và mục còn thiếu. Đừng suy bo từ mỗi USB VID/PID.
- Lệnh compile/demo/hardware có thật; lệnh upload chỉ ghi mẫu điều kiện theo board khi chưa xác minh. Ghi rõ chương trình hardware sẽ tự bật 80% sau startup hợp lệ.

Theo dõi phần chưa xong từ bước 02: median summary, delta, AUC, recovery metrics, analog thresholds/quality classifier, native GUI và soak/blank thật. Chúng không được tự đổi thành PASS khi thêm SerialDevice. Nếu bổ sung phép phân tích, cần fixture số/coverage/gap và checksum nguồn; nguồn Pi còn thiếu thì giới hạn tương thích vẫn NEEDS_INPUT.

Kết thúc ở mốc source + kiểm phần mềm + build đã thực hiện. Cần người dùng cung cấp model/ảnh module và cấu hình Tools từng nạp thành công trước khi hướng dẫn nạp/thu thật theo bo. Không yêu cầu hỏi lại A0 TGS, 80%, 60/120/60, terminal WAIT hoặc route; chúng đã thống nhất.

## Tài liệu kỹ thuật

- Arduino CLI compile: https://arduino.github.io/arduino-cli/1.5/commands/arduino-cli_compile/
- Arduino CLI board details: https://arduino.github.io/arduino-cli/1.5/commands/arduino-cli_board_details/
- Espressif LEDC: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html
- Espressif I2C: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html
- Bosch source/provenance: xem bản nguyên trạng kèm reference_s3.

# Bàn giao RoboNose: từ Raspberry Pi sang ESP32-S3

Ngày khảo sát source: 06/11/2026. Tài liệu này là đặc tả bàn giao cho AI viết lại hệ thống, không phải firmware đã triển khai. Phần “hiện tại” mô tả working tree đang có; phần “đề xuất/yêu cầu mới” là định hướng cho bản ESP32-S3.

## 1. Mục tiêu và phạm vi

Viết lại hệ thống RoboNose để ESP32-S3 trực tiếp đọc cảm biến, quản lý phiên/lượt và pha thu mẫu, điều khiển bơm, lưu dữ liệu bền vững và nhận thao tác người dùng. Raspberry Pi không còn là thành phần bắt buộc khi thu mẫu. Máy tính có thể dùng để build/nạp firmware, tải dữ liệu và phân tích offline.

Mục tiêu hiện tại là khảo sát dữ liệu linh hoạt, có thể tái phân tích và kiểm tra nguồn gốc; chưa phải thiết bị đo ppm, IAQ hay phân loại mùi. Không thêm ML, hiệu chuẩn nồng độ, van hoặc lọc than như tính năng đã có.

Giữ nguyên dữ liệu cũ và dự án Python để đối chiếu. Triển khai firmware trong thư mục/repository riêng; không thay toàn bộ Python bằng một chương trình Arduino duy nhất. Tài liệu này đủ làm đề bài triển khai; nếu cần đối chiếu chính xác thuật toán và kiểm thử, chuyển kèm repository, đặc biệt các file ở mục 4.

## 2. Phần cứng và các thông tin còn thiếu

| Thành phần | Hiện tại / yêu cầu giữ |
|---|---|
| Bộ xử lý hiện tại | Raspberry Pi 4, Python 3.11 |
| Bộ xử lý đích | ESP32-S3; chưa chốt model board, dung lượng flash/PSRAM |
| Buồng | Buồng thủy tinh; đường ống và nắp thao tác tay |
| BME688 | I2C 0x77; gas resistance, nhiệt độ, độ ẩm, áp suất |
| ADS1115 | I2C 0x48, đọc bốn MQ qua A0–A3 |
| A0 | MQ135_1 |
| A1 | MQ3_1 |
| A2 | MQ135_2 |
| A3 | MQ3_2 |
| Nguồn MQ | 5 V ngoài; mỗi AO có cầu chia áp riêng |
| Nguồn BME/ADS | 3,3 V ngoài theo bố trí hiện tại |
| Bơm | 12 V qua MOSFET; hệ hiện tại ESP32-S3 điều khiển GPIO5 |
| Van | Chưa có; GPIO4 chỉ là dự phòng trong mô tả cũ |
| Lọc than | Chưa có |
| Lưu trữ đích | Chưa có xác nhận module microSD; đề xuất bổ sung để thu độc lập |

Không tự đoán SDA/SCL, chân SD, USB hay cực tính MOSFET. Trước triển khai phần cứng phải chốt sơ đồ board, chân đang chiếm dụng, nguồn, GND, pull-up và mức logic. GPIO5 chỉ được giữ sau khi kiểm tra board thực tế. Không dùng chân dành cho flash/PSRAM/USB hoặc chân ảnh hưởng boot nếu chưa đối chiếu sơ đồ.

Giữ ADS1115 ngoài thay vì tự thay bằng ADC tích hợp ESP32: giữ đường đo để so sánh với dữ liệu Pi. Gain ±4,096 V không cho phép đưa 5 V vào ADS chạy 3,3 V. Thiết kế điện áp hoạt động trong dải nguồn cho phép, có biên an toàn; không dùng giới hạn absolute maximum làm mức vận hành. Đối chiếu [datasheet ADS1115 của TI](https://www.ti.com/lit/ds/symlink/ads1115.pdf).

Nguồn bốn heater MQ và bơm phải được tính riêng theo module thực tế; không lấy tải này từ GPIO hay mặc định bộ ổn áp board đủ dòng. Xác minh MOSFET phù hợp logic 3,3 V, điện trở kéo gate về OFF khi reset, chống xung tải cảm, tụ lọc và đường hồi dòng. Sụt nguồn/nhiễu khi bơm chạy có thể làm sai dữ liệu hoặc reset MCU. Các yêu cầu điện cần được kiểm chứng trên mạch, không được coi là đã đạt nhờ unit test.

## 3. Những điểm phải phân biệt trước khi viết lại

- Quy ước AGENTS.md nêu pipeline mặc định **30–60–60 s**. `robonose/config.py`, `config.five-esp32.example.toml` và hướng dẫn hiện tại dùng **60–120–60 s**. Đề xuất bản mới mặc định 30–60–60 theo quy ước, có preset 60–120–60; luôn lưu thời lượng thực sự áp dụng. Không sửa ý nghĩa dữ liệu cũ.
- “Năm cảm biến” là một BME688 và bốn MQ; BME688 tạo nhiều đại lượng. Hai MQ cùng loại là hai kênh độc lập, không lấy trung bình thay cho raw.
- Repository có Python phía host giao tiếp ESP32 qua Serial; chưa tìm thấy source firmware ESP32 trong danh sách file khảo sát. ACK/watchdog mô tả ở đây là hợp đồng phía Python mong đợi, chưa chứng minh firmware đang nạp thực hiện đúng.
- Working tree đã có thay đổi ở `readers.py`, `analysis.py` và các file mới `adc_diagnostic.py`, `i2c_lock.py`, `test_ads_integrity.py`. Bản bàn giao này có xét chúng; AI tiếp nhận phải kiểm tra working tree được gửi kèm, không chỉ đọc HEAD.
- `docs/schema.md` còn tiêu đề 1.0 và nội dung lịch sử; hằng số đang chạy trong `schema.py` là **2.0**. Ưu tiên code thực thi và test hiện tại khi có khác biệt.

## 4. Bản đồ toàn bộ source hiện tại

| File/nhóm | Trách nhiệm và cách chuyển |
|---|---|
| `robonose/__main__.py`, `__init__.py` | Entry point và version; chuyển thành app startup và firmware version |
| `cli.py` | Lệnh doctor/monitor/collect/analyze/esp-pump-check, chọn sim/hardware và opt-in; chuyển parser nghiệp vụ sang firmware, analyze để offline |
| `config.py` | Default, load TOML, kiểm tra giới hạn, mapping profile; chuyển schema cấu hình và validation, không port phụ thuộc `tomllib` |
| `channels.py` | Legacy hai MQ và profile four; giữ danh tính kênh, hỗ trợ dữ liệu legacy ở công cụ offline |
| `schema.py` | Schema 2.0, cột CSV, timezone và mẫu trống; làm hợp đồng dữ liệu tham chiếu |
| `state.py` | Máy trạng thái, deadline và recovery extension; port thành logic thuần C/C++ có test |
| `session.py` | Context acquisition, worker đọc, queue, session/trial, writer, command, chất lượng, cleanup, analysis worker; tách thành các module firmware |
| `readers.py` | SimReader, BoschBME, ADS1115, timing, ADCAnomalyGuard, HardwareReader; thay lớp truy cập Linux bằng ESP-IDF |
| `i2c_lock.py` | Khóa liên tiến trình trên Pi; thay bằng ownership/mutex trong firmware, không port lock file Linux |
| `adc_diagnostic.py` | Chẩn đoán ADS từng kênh, không BME/bơm; giữ chức năng trong diagnostic mới |
| `quality.py` | Đánh giá trôi nền gas/T/H, gap và thiếu dữ liệu; port phần cảnh báo nhẹ hoặc tính offline |
| `writer.py` | UUID, raw/events/meta, flush/fsync, kết thúc, tên không đè; thiết kế lại theo SD/FAT và crash recovery |
| `esp32.py` | Một worker sở hữu Serial, handshake, ACK/STATUS, health lease, heartbeat và OFF; thay bằng PumpSupervisor nội bộ khi ESP làm chủ toàn hệ thống |
| `esp_commands.py` | Doctor hardware và thử bơm có giám sát, audit; chuyển thành diagnostic/short-test opt-in |
| `pump.py`, `pump_test.py` | Nhánh GPIO Pi cũ; CLI mới từ chối pump-test/enable-pump cũ. Không mang GPIO BCM sang ESP |
| `terminal.py` | Prompt và pipe/UTF-8 không cản acquisition; thay bằng USB console, tùy chọn web UI |
| `analysis.py` | Đọc CSV, lọc hợp lệ, baseline/response/recovery/AUC, summary và PNG; ưu tiên giữ trên máy tính |
| `build_driver.py` | Build `.so` Linux; không dùng trên ESP |
| `native/bridge.c` | Adapter ioctl Linux + ctypes bridge, cấu hình/readback BME; viết lại adapter I2C/delay, giữ logic đo |
| `native/vendor/*` | Bosch BME68x SensorAPI và LICENSE; có thể tái sử dụng C, giữ nguyên bản và giấy phép |
| `config*.toml` | Profile example, five-esp32 và cấu hình khác; không đè config cá nhân, không chọn legacy làm đích mặc định |
| `pyproject.toml`, `requirements-lock.txt` | Môi trường Python host; giữ cho analysis/test, không cài lên MCU |
| `tests/test_core.py`, `test_session.py`, `test_acquisition.py`, `test_terminal.py` | Hành vi state, thu nền, tương tác và vòng đời |
| `tests/test_analysis.py`, `test_review.py`, `test_integration_ready.py` | Phân tích, độ toàn vẹn và kiểm tra tích hợp |
| `tests/test_five_esp32.py`, `test_external_pump.py`, `test_ads_integrity.py` | Profile bốn MQ, Serial giả, ngoại bơm, bảo vệ ADS |
| `scripts/verify_two_trials.py`, `verify_interactive.py` | Kiểm chứng tương tác nhiều trial; dùng làm kịch bản đối chiếu |
| `README.md`, `AGENTS.md`, `docs/*` | Quy tắc, thiết kế, schema, thao tác, review, bằng chứng test, nguồn gốc vendor |
| Các guide MD ở root, `run.txt` | Tài liệu thao tác/lịch sử; đối chiếu với code và profile mới, không coi mọi ví dụ là cấu hình hiện hành |

Một số file Python có khối code cũ đã comment trước phần đang chạy. Chỉ port định nghĩa thực thi; không nhân đôi hai phiên bản. Không mang `.venv`, `.so`, cache hay toàn bộ dữ liệu thu sang flash MCU.

## 5. Luồng hoạt động hiện tại cần bảo toàn

### 5.1 Phiên và lượt

Session là toàn bộ thời gian vận hành; trial là một lượt lấy mẫu. Reader BME/ADS khởi tạo một lần mỗi session. `next` tạo trial mới, không reset heater hay bật bơm lại. Session log vẫn ghi lúc đặt tên, ghi chú và giữa trial. Trial liên kết session bằng ID/đường dẫn; dữ liệu trùng thời gian không phải hai mẫu thí nghiệm độc lập.

Trong collect có bơm: preflight sensor → xác nhận bộ điều khiển đang OFF → mở writer và acquisition ở PUMP_STARTUP → mẫu mới ghi thành công → ON được xác nhận ở mức điều khiển → MONITOR. Bơm ON một lần, chạy liên tục cả session qua finish/name/next. `finish` hoặc `abort` chỉ kết thúc trial; `quit` kết thúc session và OFF. Chế độ monitor không tự bật bơm.

### 5.2 Máy trạng thái

```text
MONITOR --start--> BASELINE --hết giờ--> WAIT_EXPOSURE
WAIT_EXPOSURE --expose--> EXPOSURE --hết giờ--> WAIT_RECOVERY
WAIT_RECOVERY --recover--> RECOVERY --hết giờ--> WAIT_FINISH
WAIT_FINISH --extend N--> RECOVERY (đoạn bổ sung riêng)
WAIT_FINISH --finish--> WAIT_NAME -> WAIT_NOTES -> BETWEEN_RUNS
BETWEEN_RUNS --next--> MONITOR (trial mới)
mọi trạng thái --quit/lỗi phiên--> dừng bơm, kết thúc session
```

Tất cả WAIT tiếp tục thu/ghi dữ liệu. WAIT không cộng vào thời lượng pha chính. Khi hết deadline, mốc chuyển pha là deadline thực, không phải thời điểm UI xử lý. Vòng đọc chụp run/phase/context ở đầu vòng; vòng bắt đầu trước deadline giữ nhãn đó dù đọc xong sau deadline. Mỗi thiết bị có timing riêng vì đọc tuần tự.

`finish` sớm hoặc `abort` giữ dữ liệu ABORTED; đủ pha và finish hợp lệ mới COMPLETE. COMPLETE chỉ nói pipeline hoàn thành, không chứng minh nền ổn định hay buồng sạch. Lệnh sai trạng thái bị từ chối, không tự chuyển pha.

### 5.3 Tương tác cần giữ

Giữ ý nghĩa các lệnh `start`, `expose`, `recover`, `extend <s>`, `finish`, `abort`, `next`, `quit`, `mark <nội dung>`, `status`, `name`, `notes`, `info`, `durations`. Cú pháp chi tiết phải đối chiếu `Session.command` trước port; không giả định mọi lệnh hợp lệ ở mọi pha. Cho phép bỏ qua tên/notes; dùng UUID làm tên lưu chính, tên tiếng Việt làm metadata để giảm rủi ro rename trên FAT.

`external-pump on/off/not-used/unknown` chỉ ghi khai báo nguồn ngoài, không tác động GPIO. `mark` ghi thời điểm ứng dụng nhận thao tác, không chứng minh thời điểm thay đổi khí vật lý. Không có lệnh VALVE/AUTO/AIR/SAMPLE; thay đầu ống và mở nắp bằng tay.

## 6. Hợp đồng đo cảm biến

### 6.1 BME688

Giữ forced mode, heater yêu cầu 320 °C/150 ms, oversampling T8/H2/P4, filter OFF như cấu hình đang có. Lưu requested và applied/readback riêng, gồm chip/variant, thanh ghi heater và thời gian heater được lượng tử hóa. Chờ theo thời gian đo Bosch cộng heater thực lập trình và biên chờ, không dùng delay tùy ý.

Đọc Ω, °C, %RH, áp suất Pa từ API rồi đổi sang hPa đúng một lần. Giữ `gas_valid`, `heater_stable`, `new_data`, status bits, meas/gas index, res_heat/idac/gas_wait. Không suy ra cờ từ giá trị. Không có dữ liệu mới thì STALE/null, không copy mẫu trước. Gas-invalid vẫn có thể giữ raw gas với cờ không hợp lệ.

Tái sử dụng vendor C ở `robonose/native/vendor`, thay callback I2C/delay bằng adapter ESP. `docs/vendor-provenance.json` ghi nguồn Bosch v4.4.8, SHA-256 và BSD-3-Clause; phải chuyển cùng LICENSE và kiểm tra hash nếu dùng lại. Không cần BSEC để thu raw; không tự thay pipeline bằng BSEC/IAQ.

### 6.2 ADS1115

Giữ single-shot, gain 1 tương ứng FSR ±4,096 V, 128 SPS; đây là tốc độ conversion nội bộ, không phải vòng ghi 1 Hz. A0→A1→A2→A3 tuần tự. Mỗi kênh: ghi config đúng MUX/PGA/rate/mode → kiểm readback → chờ conversion mới với timeout hữu hạn → đọc signed 16-bit → kiểm config sau đọc. Không gọi hai API làm hai conversion riêng cho count và voltage.

```text
voltage_v = signed_adc_count * 4.096 / 32768
ao_voltage_v = voltage_v * divider_factor đã xác nhận của chính kênh đó
```

Chưa xác nhận factor thì AO estimate=null. Mô tả điện trở không tự xác nhận factor. Không dùng factor legacy cho bốn kênh mới. Giữ count âm/saturation và gắn cờ; không clamp 0. Lỗi một kênh không ngăn đọc các kênh còn lại.

Giữ bảo vệ MUX/config mismatch và anomaly guard: `NEGATIVE`, `ADC_LIMIT`, `SUSPECT_MUX_ECHO`, `SUSPECT_JUMP`. Guard hiện dùng lịch sử tối đa 7 mẫu, so bước nhảy lớn với median và đối chiếu kênh khác; đây là heuristic, có thể nhầm phản ứng nhanh thật. Giữ raw, lưu lý do và version/threshold thuật toán; không tự sửa hoặc xóa xung. Đối chiếu `ADCAnomalyGuard` và `test_ads_integrity.py` nếu port nguyên hành vi.

## 7. Kiến trúc firmware đề xuất

Đề xuất ESP-IDF với C/C++ và FreeRTOS, khóa một release cụ thể sau khi build thử trên board đích. Đây là lựa chọn thiết kế, chưa phải toolchain đã cài. Ưu tiên USB console + microSD ở bản đầu; Wi-Fi/web UI là lớp bổ sung. Không yêu cầu Pi chạy Python để duy trì acquisition.

```text
USB console / web UI tùy chọn
          | command queue
          v
Session + StateMachine -----> PumpSupervisor -----> GPIO/MOSFET
          | snapshot               ^
          v                        | tiến độ đọc + ghi + sync
Acquisition --> bounded queue --> StorageWriter --> microSD
     |                             |
BME688 + ADS1115              telemetry snapshot --> UI
```

| Module/task | Trách nhiệm |
|---|---|
| Board/HAL | Pin map, I2C, GPIO, SD, clock; mock thay được |
| Acquisition | Một owner cảm biến/bus, lịch 1 Hz, timing, flags và error |
| State/session | Một owner trạng thái, kiểm lệnh, deadline, trial context |
| StorageWriter | Một owner file, thứ tự ghi, checkpoint, sync và báo tiến độ |
| PumpSupervisor | Quyền quyết định ON/OFF, lease, fault latch, tắt ưu tiên |
| Console/UI | Parser có giới hạn, không thực hiện I2C/file blocking trong handler |
| Quality | Cửa sổ vòng hữu hạn cho gas/T/H, cảnh báo nhẹ |
| Export | Chỉ đọc file đã đóng hoặc snapshot nhất quán, không khóa writer lâu |

Không cần cố định mọi task vào core ngay từ đầu. Đặt ưu tiên để OFF và deadline không bị UI/download chặn. Timer callback chỉ đánh thức task, không đọc I2C/SD hoặc serialize JSON trong ISR. Dùng queue/notification thay busy loop. Snapshot phải có ID/epoch để mẫu in-flight không bị ghi nhầm trial sau finish/next; barrier đóng trial phải đợi hoặc phân loại mẫu còn trong queue theo context gốc.

Cấu trúc gợi ý:

```text
firmware/
  CMakeLists.txt
  sdkconfig.defaults
  partitions.csv
  main/app_main.cpp
  components/board/
  components/config/
  components/sensors/{bme688,ads1115,sim}/
  components/bosch_bme68x/  # vendor + LICENSE
  components/acquisition/
  components/session/
  components/storage/
  components/pump/
  components/quality/
  components/console/
  components/telemetry/
  test/
tools/                       # export/validate/analyze trên máy tính
docs/                        # wiring/build/operation/schema/recovery
```

## 8. An toàn bơm khi gom về một ESP32

Host Serial heartbeat cũ không còn là kiến trúc chính. Không bê nguyên yêu cầu PC phải PING mỗi 4 s vào chế độ thu độc lập. Thay bằng health lease nội bộ dựa trên tiến độ acquisition, writer và checkpoint storage.

1. Boot đặt đầu ra OFF sớm nhất có thể; phần cứng phải kéo gate OFF cả lúc firmware chưa chạy.
2. Mặc định pump disabled. Chỉ phiên hardware có opt-in mới được điều khiển tải.
3. Preflight sensor và storage phải đạt, có mẫu mới ghi được, cấu hình/cực tính đã xác nhận rồi mới cho ON.
4. Một session chỉ ON một lần. Pha thu, đặt tên và next không phát ON lại.
5. Supervisor chỉ gia hạn lease khi cả acquisition và writer có tiến triển thực. Lưu `last_acquisition_completed`, `last_write_completed`, `last_sync_completed` và queue depth; heartbeat task còn chạy không đủ chứng minh hệ thống khỏe.
6. Sensor task treo, writer/SD lỗi, queue overflow hoặc lease hết hạn: OFF, latch lỗi, giữ dữ liệu và không tự ON lại sau phục hồi/reset.
7. `quit`, lỗi phiên hoặc yêu cầu dừng khẩn phải OFF trước khi chờ analysis/đóng file lâu. OFF không phụ thuộc queue ghi log còn chỗ.
8. Watchdog chỉ là dự phòng; reset MCU không thay thế mạch giữ OFF. Lỗi treo ảnh hưởng toàn MCU cần kiểm thử thực tế, cân nhắc interlock/watchdog phần cứng nếu cần mức bảo đảm cao hơn.

Task watchdog có thể theo dõi task/user đã đăng ký; AI triển khai phải cấu hình hành vi timeout/reset rõ ràng theo release IDF, thay vì giả định bật mặc định là đủ. Tham khảo [ví dụ watchdog chính thức Espressif](https://github.com/espressif/esp-idf/blob/master/examples/system/task_watchdog/README.md).

`pump_command` là yêu cầu, trạng thái GPIO/controller là báo cáo mức điều khiển, không chứng minh bơm quay hay có lưu lượng. Không tạo ACK giả cho “phản hồi vật lý”. Backend mới ghi `local_gpio`; phần chưa biết ghi UNKNOWN/null. Mất máy tính/USB không làm dừng chế độ autonomous đã định nghĩa; nếu có chế độ supervised thì chính sách mất kết nối phải tách riêng và lưu metadata.

Đề xuất ban đầu giữ ngưỡng lease theo cấu hình cũ làm tham chiếu (health 3 s, lease 2 s), nhưng phải đo latency SD/I2C và kiểm thử trước chốt. Watchdog 15 s của ESP cũ chỉ là kỳ vọng giao thức, không tự coi là giá trị phù hợp cho firmware mới.

## 9. Thời gian và lịch thu

Dùng monotonic 64-bit microsecond cho deadline và elapsed; ESP-IDF cung cấp `esp_timer_get_time()` theo thời gian từ khởi tạo timer. Sau reset có cơ sở thời gian mới, vì vậy luôn có boot_id. Tham khảo [ESP Timer cho ESP32-S3](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/system/esp_timer.html); API phải được đối chiếu lại với release khóa trong dự án mới.

Lịch vòng = mốc đầu + n×chu kỳ. Nếu trễ, ghi lag và gap; không tạo nhiều dòng bù mang số đo giả. Timestamp đầu vòng và từng phép đọc là thời điểm host MCU thực hiện yêu cầu, không phải timestamp nội tại sensor.

ESP không được giả định có ngày giờ đúng sau mất nguồn. Cho phép đặt giờ qua console, NTP tùy chọn hoặc RTC ngoài nếu sau này bổ sung. Lưu time_source, time_valid, sync events và offset mapping wall-clock↔monotonic. Chưa có giờ: timestamp trống, lưu elapsed/boot_id, thư mục `unsynced/<boot_id>/<run_id>`; không ghi năm giả. Đồng bộ giữa phiên không sửa raw cũ và không làm nhảy deadline. Hiển thị +07:00 khi có thời gian hợp lệ.

## 10. Dữ liệu và tương thích

### 10.1 Hợp đồng raw

Ưu tiên export tương thích schema 2.0 để dùng lại analysis Python. Nếu thay ý nghĩa/cấu trúc thì tăng schema version, viết converter và test; không gắn nhãn 2.0 cho dữ liệu có semantics khác. Dưới đây là toàn bộ nhóm cột hiện hành, thứ tự chuẩn lấy từ `schema.py`:

```text
run_id, seq, timestamp, elapsed_s, phase_elapsed_s, phase,
sensor_uptime_s, loop_interval_s, loop_duration_s, schedule_lag_s,
pump_command, external_pump_state, external_pump_source,
pump_reported_state, pump_reported_at, pump_report_age_s, pump_backend

temperature_c, humidity_pct, pressure_hpa, gas_resistance_ohm,
gas_valid, heater_stable, new_data, bme_status_bits,
bme_meas_index, bme_gas_index, bme_res_heat, bme_idac, bme_gas_wait

Với từng device: bme, mq135, mq3, mq135_1, mq3_1, mq135_2, mq3_2:
  <device>_read_started_at, _read_elapsed_s, _read_duration_s,
  _status, _error, _fresh
Với từng MQ ở trên thêm:
  <device>_adc_count, _voltage_v, _ao_voltage_v, _quality
```

Profile four để trống cột mq135/mq3 legacy; không nhân đôi kênh. CSV UTF-8, quote đúng dấu phẩy/dấu nháy/newline, ô trống là thiếu; JSON null, không NaN/Infinity. Boolean export tương thích True/False của parser cũ. Giữ đủ chữ số để tái phân tích; chỉ làm tròn màn hình. Seq tăng trong từng log, UUID run bất biến.

Status thiết bị gồm OK/ERROR/STALE và SUSPECT ở guard hiện tại. Không đồng nhất fresh với valid: gas có thể fresh nhưng gas_valid=false. Không biến lỗi thành 0 hoặc điền giá trị vòng trước. Timestamp/timing phải dùng cùng cơ sở thời gian của log; thêm session_elapsed/boot_elapsed cần mô tả riêng.

### 10.2 Events và metadata

`events.csv`: run_id, timestamp, elapsed_s, phase_elapsed_s, phase, event, details_json. Ghi phase_change, thao tác, marker, sensor error, quality, pump ON/OFF/fault, session/trial start/end, storage fault, time sync, reset và config changes. Giữ thời điểm hiệu lực và thời điểm xử lý nếu khác, không coi thứ tự append luôn là thứ tự thời gian vật lý.

Metadata tối thiểu: schema/program/firmware version, git commit, toolchain/IDF version, board/flash/PSRAM, boot_id/reset_reason, run_id/session_id, backend, kind, started/ended/status/reason, rows/checkpoint, config requested, applied/readback, mapping sensor, divider factors, phương pháp thu, trạng thái nắp, mã mẫu tùy chọn, phase_intervals, extensions, planned/actual durations, tên/notes và giới hạn feedback bơm. Không ghi mật khẩu Wi-Fi vào snapshot xuất dữ liệu.

Giữ trạng thái PARTIAL/COMPLETE/ABORTED/ERROR. Có thể bổ sung `recovered_after_reset`/recovery report nhưng không tự đổi PARTIAL thành COMPLETE. Metadata `sample` giữ sample_description, person_code tùy chọn, source, sampling_method, purge_method, lid_state, distance_cm. Không yêu cầu thông tin định danh người.

### 10.3 Tệp đầu ra

```text
data/<exploration|simulation>/<date hoặc unsynced>/<session_id>/
  session/{raw.csv,events.csv,metadata.json}
  trials/<run_id>/{raw.csv,events.csv,metadata.json}
```

Đây là cấu trúc mới đề xuất, phải cập nhật exporter/analyzer tương ứng. Bản Pi hiện tạo thư mục session/trial dưới root theo ngày, trial có liên kết session. Giữ hai log hoặc dùng một log session cùng index trial đều được nếu exporter tái tạo đầy đủ trial và không lẫn timeline. Bản đầu nên giữ mô hình hiện tại để đối chiếu dễ hơn. `summary.json`, `signals.png`, `normalized.png` có thể sinh trên máy tính sau export; không bắt ESP render matplotlib.

## 11. Lưu trữ, mất điện và phục hồi

Đề xuất microSD là nơi lưu raw chính; NVS chỉ lưu cấu hình nhỏ và trạng thái cần thiết, không ghi mỗi mẫu vào NVS. Nếu chưa có SD thì phải công khai chế độ stream phụ thuộc máy tính; không gọi đó là thu độc lập bền vững. Bộ đệm RAM/PSRAM không giữ dữ liệu khi mất điện.

ESP-IDF có ví dụ SDMMC/FatFs; không sao chép hành vi tự format thẻ khi mount lỗi từ ví dụ. Luôn tắt format-on-fail để bảo vệ dữ liệu. Tham khảo [ví dụ SD chính thức](https://github.com/espressif/esp-idf/blob/master/examples/storage/sd_card/sdmmc/README.md).

- Một writer sở hữu raw/events/meta. Queue hữu hạn; đầy queue là lỗi được ghi nhận và dừng bơm, không âm thầm bỏ mẫu.
- Dùng flush/checkpoint theo chu kỳ cấu hình; 5 s hiện tại là điểm xuất phát. Phân biệt ghi vào buffer, ghi xuống filesystem và sync thành công; lease không được chỉ nhìn số mẫu enqueue.
- Lưu số seq checkpoint và số đã append riêng nếu cần. Không hứa không mất dữ liệu: dữ liệu sau checkpoint và cache nội bộ SD có thể mất khi mất nguồn.
- Metadata kiểu temp+rename trên Linux không bảo đảm cùng tính chất trên FAT. Đề xuất hai slot metadata có generation/checksum hoặc journal append; chọn bản hợp lệ mới nhất lúc boot, giữ bản hỏng để kiểm tra.
- Có thể dùng journal record length+CRC rồi export CSV, hoặc CSV append với quy tắc nhận diện dòng cuối thiếu. Chọn một cách rõ ràng, test corruption; CRC kiểm tra toàn vẹn không phải bảo đảm chống mất điện.
- Boot sau reset tạo session mới, bơm OFF, phát hiện session dang dở và tạo recovery report. Không nối monotonic hai boot như cùng một lượt liên tục.
- Không sửa/xóa raw cũ khi recovery. Công cụ phục hồi xuất bản sao và ghi rõ số dòng bỏ qua, lý do, checksum nguồn.
- Thẻ đầy/rút thẻ/lỗi sync: OFF, lỗi latch, giữ dữ liệu đã có; không tự format, không tự ghi đè file cũ và không tự tiếp tục bơm sau cắm thẻ lại.
- Export có manifest/checksum để kiểm tra sau sao chép. Download file đang thu phải được kiểm soát hoặc chỉ cho tải trial đã đóng.

Ước lượng dung lượng bằng số byte mỗi dòng đo thật × sample_hz × thời gian, cộng events và phần ghi trùng session/trial. Ví dụ giả định 2 KB/dòng × 1 Hz ≈ 173 MB/ngày cho một raw stream, chưa tính stream trùng; không coi đây là kích thước đã benchmark. Đo latency p95/p99/max của write/sync, queue high-water mark, heap và stack trước tối ưu.

## 12. Chất lượng và phân tích

Giữ raw và normalized riêng. Trước start đánh giá gas/T/H trong cửa sổ 30 s: số mẫu, coverage, gap, invalid_fraction, slope và range. Ngưỡng hiện tại trong `config.py`: min_samples=5, min_window_fraction=0,8, max_gap=3 s, max_invalid_fraction=0,2; gas 5 %/phút và range 5 %, T 0,3 °C/phút và range 0,2 °C, H 1 điểm %RH/phút và range 1 điểm %RH, advisory T>35 °C. Đây là ngưỡng khảo sát đang dùng, không phải chuẩn hiệu chuẩn.

Cho phép start khi cảnh báo và lưu baseline_started_without_stability. heater_stable không chứng minh nền ổn định. Nhiệt độ BME có thể chịu ảnh hưởng bố trí/heater, không tự gọi là nhiệt độ môi trường đã bù. Chưa có lọc than nên recovery chỉ là đưa về điều kiện nền đã khai báo, không chứng minh khí sạch.

Giữ phân tích đầy đủ offline: baseline n/mean/median/std ddof=1/min/max/slope/drift, extrema/delta có dấu, phần trăm chia abs(mean baseline), AUC trapezoid theo thời gian thực, coverage và recovery. Nền thiếu/gần zero, pha thiếu, cuối pha thiếu mẫu trả null+reason. Không nối AUC qua WAIT, gap lỗi hoặc hai đoạn recovery riêng. Mẫu âm/saturation/suspect vẫn xuất raw nhưng loại khỏi thống kê hợp lệ theo quy tắc công khai.

`analyze` chỉ sinh summary/PNG; không sửa raw/events/metadata. Kiểm hash trước/sau. Với firmware mới phải cập nhật `analysis.py` nếu metadata/time/schema thay đổi, rồi thử trên cả schema 1.0, 2.0 và dữ liệu export mới. Không bắt MCU giữ toàn bộ session trong RAM để tính median hay vẽ biểu đồ.

## 13. Cấu hình và giao diện đề xuất

Firmware có thể dùng JSON trên SD và NVS cho phần nhỏ; không cần port TOML. Có schema_version, validation và snapshot applied. Không lưu config thay đổi giữa pha vào dữ liệu như thể đã áp dụng từ đầu; thay đổi quan trọng chỉ có hiệu lực ở phiên/lượt mới hoặc event rõ ràng.

```json
{
  "config_version": 1,
  "backend": "sim",
  "sample_hz": 1.0,
  "durations_s": {"baseline": 30, "exposure": 60, "recovery": 60},
  "bme": {"address": 119, "heater_c": 320, "heater_ms": 150},
  "ads": {"address": 72, "gain": 1, "data_rate_sps": 128},
  "mq_channels": {"mq135_1": 0, "mq3_1": 1, "mq135_2": 2, "mq3_2": 3},
  "divider_factors": {"mq135_1": null, "mq3_1": null, "mq135_2": null, "mq3_2": null},
  "pump": {"enabled": false, "gpio": 5, "active_high": null},
  "storage": {"sync_interval_s": 5, "format_on_fail": false}
}
```

Ví dụ trên chỉ minh họa ý nghĩa, chưa đủ cấu hình phần cứng: SDA/SCL, chân SD, board và cực tính phải chốt trước hardware mode. `active_high=null` phải làm validation từ chối enable pump. Giới hạn mọi số hữu hạn/dương, channel không trùng, pin không xung đột, độ dài string/command hữu hạn. Config sai không tự rơi về cấu hình làm bật tải.

USB console là giao diện tối thiểu để dùng không Wi-Fi; 115200 là thông số Serial cũ, cần phân biệt USB CDC với UART bridge khi chọn board. Log debug không trộn vào protocol machine-readable; response có request_id, accepted/rejected, reason và state. Thiết kế chống gửi lặp: retry cùng request_id không tạo trial hoặc marker trùng.

Nếu có web UI: màn hình phase/countdown, gas/T/H/P, bốn MQ, trạng thái ghi/SD/queue, cảnh báo, nút start/expose/recover/extend/finish/next/quit/mark. UI lấy snapshot, không đọc sensor trực tiếp. Mất trình duyệt không dừng acquisition autonomous; thao tác bật bơm cần session opt-in rõ ràng, không bật khi refresh hoặc kết nối lại. Nếu mở điều khiển qua mạng phải có xác thực, giới hạn request và quản lý quyền điều khiển; không mặc định phơi cổng điều khiển ra Internet.

## 14. Quy trình cài đặt và triển khai bản mới

### 14.1 Chuẩn bị trên máy phát triển

1. Chốt board ESP32-S3, dung lượng flash/PSRAM, sơ đồ nối I2C/SD/bơm và lưu trữ. Ghi bảng BOM và pin map đã xác nhận.
2. Chọn release ESP-IDF phù hợp, khóa version/commit và dependency; dùng hướng dẫn cài chính thức tương ứng hệ điều hành máy phát triển. Không tự sửa OS/mạng của Pi trong quá trình viết code.
3. Tạo firmware riêng, vendor Bosch kèm LICENSE/provenance, cấu hình mặc định sim/pump-disabled. Lưu sdkconfig.defaults, partition table và hướng dẫn build tái lập.
4. Nếu giữ công cụ Python trên Pi, dependency chỉ cài trong `.venv` của dự án. Không mang numpy/matplotlib/ctypes `.so` vào ESP32.

Lệnh ESP-IDF dự kiến sau khi đã cài/chọn đúng môi trường SDK, chạy tại root firmware:

```bash
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
```

Build không nạp board và không thử tải. AI phải cung cấp lệnh chính xác theo cây source hoàn thiện, không ghi “build passed” nếu chưa chạy thành công. Kiểm partition hợp flash thực; không mặc định mọi S3 đều có PSRAM hoặc SD slot.

### 14.2 Nạp và bring-up có giám sát

Các bước sau là hướng dẫn tương lai, chưa được chạy trong lượt lập tài liệu này. Chỉ nạp/đọc phần cứng/bật bơm khi người dùng yêu cầu rõ.

```bash
idf.py -p <CONG_USB_THUC_TE> flash
idf.py -p <CONG_USB_THUC_TE> monitor
```

Lần đầu tách nguồn bơm hoặc cô lập tải để kiểm boot/reset OFF. Kiểm sim, storage và console trước. Sau đó người dùng chủ động chạy diagnostic cảm biến; xác nhận địa chỉ và readback, bốn kênh đúng mapping. Chỉ thử bơm ngắn riêng khi đã xác nhận dây/cực tính/nguồn, thời lượng hữu hạn (giữ giới hạn tối đa 10 s như công cụ cũ), OFF mọi đường thoát và có audit.

Không triển khai OTA ở bước đầu nếu chưa cần. Nếu bổ sung OTA phải chỉ khi không thu, bơm OFF, không xóa SD, có phục hồi firmware lỗi. Nạp firmware mới không được tự format storage.

### 14.3 Quy trình thu thực tế sau nghiệm thu

1. Kiểm nguồn, SD/dung lượng, đường ống/nắp, mã mẫu và config snapshot.
2. Chọn hardware/pump opt-in nếu cần; preflight sensor + storage. Quan sát xác nhận mức điều khiển, tự kiểm bơm/lưu lượng nếu cần.
3. MONITOR và kiểm nền; start BASELINE theo preset đã chọn.
4. WAIT_EXPOSURE: đổi đầu ống hoặc đưa mẫu bằng tay, mark, expose gần thời điểm tiếp xúc.
5. WAIT_RECOVERY: đưa về nền bằng tay, mark, recover.
6. WAIT_FINISH: extend nếu cần hoặc finish; tên/notes rồi next. Bơm vẫn chạy nếu phiên có bơm.
7. Quit dừng phiên/bơm; kiểm trạng thái. Chờ đóng/sync trước rút SD.
8. Export, kiểm checksum, sao lưu và analyze trên máy tính; không ghi đè dữ liệu gốc.

## 15. Kế hoạch kiểm thử và tiêu chí nghiệm thu

### 15.1 Chỉ phần mềm, không tải thật

| Nhóm | Phải kiểm |
|---|---|
| State | 30–60–60 và preset khác; command sai pha; deadline khi UI chậm; WAIT không cộng pha; recovery extension tách đoạn |
| Acquisition | Timing từng device, seq, gap/lag, lỗi một sensor không xóa kênh khác, dữ liệu mới/null đúng |
| ADS | Signed count, voltage cùng conversion, đúng MUX, readback trước/sau, timeout, saturation, suspect raw giữ nguyên |
| BME | Đơn vị, status bits, stale, gas-invalid, readback heater và oversampling |
| Session | Hai trial, cùng tên không đè, next không reinit sensor, in-flight context không ghi nhầm, WAIT/name/notes vẫn có raw |
| Pump mock | Không ON mặc định/sim/diagnostic; ON chỉ sau preflight và mẫu ghi được; một lần/session; finish/next vẫn ON; quit/lỗi OFF |
| Fault injection | Treo acquisition/writer, SD full/remove/write/sync fail, queue full; OFF không bị log queue chặn, không tự ON lại |
| Reset/recovery | Record cắt, metadata hỏng, boot mới giữ PARTIAL, không nối thời gian, không format hoặc sửa nguồn |
| Clock/UI | Chưa có giờ, sync/nhảy wall-clock không đổi deadline, mất UI, command lặp/UTF-8/string quá dài |
| Export/analyze | Parser đọc được, null/flags đúng, summary so với fixture Python, hash raw/events/meta không đổi |

Tạo fixture deterministic từ sim, fake clock/fake I2C/fake storage/fake GPIO để chạy trên host; test ESP-IDF/Unity cho phần nền tảng cần thiết. Không mở thiết bị thật trong test mặc định. Không copy “passed” từ báo cáo lịch sử `docs/validation.md` làm kết quả bản mới.

Lệnh tham chiếu kiểm dự án Pi hiện tại khi cần đối chiếu, chỉ chạy trong môi trường phù hợp:

```bash
.venv/bin/python -m pytest -q -k "not pump_test"
.venv/bin/python scripts/verify_two_trials.py
```

### 15.2 Kiểm thực tế do người dùng yêu cầu riêng

Xác minh điện áp AO/chia áp/GND, nguồn khi bơm bật, đúng kênh bằng tín hiệu kiểm tra phù hợp, BME/ADS readback, OFF boot/reset/brownout, watchdog/interlock, lưu lượng và tác động nhiệt/ẩm. Chạy nhiều trial và soak test đủ thời gian phiên dự kiến; theo dõi heap/stack, độ trễ, tỷ lệ gap và độ bền file. Kiểm mất điện/rút SD chỉ trên dữ liệu test và có giám sát, không trên dữ liệu thu duy nhất.

Nghiệm thu tối thiểu: thu độc lập không cần Pi; đủ năm cảm biến; đủ pha và marker; dữ liệu không bị đè; bơm không tự khởi động lại sau lỗi; export tái phân tích được; mọi giới hạn mất dữ liệu được mô tả bằng kết quả đo thật. Ngưỡng jitter/gap, thời gian OFF tối đa và độ dài soak phải thống nhất trước nghiệm thu, không tự tuyên bố đáp ứng thời gian thực cứng.

## 16. Ưu tiên tối ưu

1. Đúng dữ liệu, OFF khi lỗi, lưu bền vững và khả năng truy vết trước UI/Wi-Fi.
2. Chỉ thu 1 Hz ban đầu; giữ cấu hình heater/SPS để so Pi và ESP. Đổi tốc độ/gain/heater tạo config version khác, không trộn như cùng điều kiện thí nghiệm.
3. Buffer hữu hạn và cấp phát trước; không giữ toàn raw trong RAM, không tạo JSON lớn mỗi vòng nếu chưa cần.
4. Đo latency SD rồi chọn batch/checkpoint cân bằng mất dữ liệu và jitter; không tăng buffer để che lỗi writer kéo dài.
5. UI cập nhật chậm hơn hoặc bằng acquisition, dùng snapshot; tải file/đồ thị không cản đọc/ghi.
6. Giữ điện trở và điện áp raw; smoothing/normalization là sản phẩm dẫn xuất có version, không ghi ngược raw.
7. Chỉ tối ưu đọc chồng lấp BME/ADS sau khi bản tuần tự đúng và timing được đo. Chồng lấp thay đổi temporal semantics phải được mô tả.
8. Tách bơm/MQ khỏi nguồn số và bố trí nhiệt hợp lý; phần mềm không sửa được sai mức điện áp, rò khí hay nguồn nền không kiểm soát.

## 17. Những quyết định AI tiếp nhận phải chốt

| Cần chốt | Cách tiến hành khi chưa có thông tin |
|---|---|
| Model board, flash/PSRAM, chân SDA/SCL/SD | Viết HAL/config và mock; chưa hardcode để chạy hardware |
| Có microSD/module nào, SPI hay SDMMC | Chọn theo board đã xác nhận; công khai nếu chưa có lưu độc lập |
| Cực tính MOSFET, wiring và OFF khi reset | Pump mặc định disabled; không suy từ GPIO5 |
| Giờ thực: console/NTP/RTC | Hỗ trợ unsynced ngay từ đầu; RTC là tùy chọn chưa có |
| Giao diện độc lập mong muốn | USB console tối thiểu; web/nút/màn hình chỉ triển khai theo lựa chọn thực tế |
| Autonomous hay supervised | Autonomous là đề xuất chính; không nhập nhằng chính sách mất UI |
| Preset thu | Default 30–60–60 theo AGENTS, giữ tùy chọn 60–120–60; người dùng có thể chốt lại |
| Định dạng lưu nội bộ và schema export | Ưu tiên tương thích 2.0; đổi schema phải có converter/test |
| Thời gian OFF/lease/checkpoint/soak | Chọn sau benchmark và ghi giới hạn rõ trong tài liệu nghiệm thu |

Các thiếu sót phần cứng không ngăn AI viết kiến trúc, mock và test; nhưng phải ngăn firmware tự bật tải bằng pin/cực tính suy đoán.

## 18. Đề bài có thể gửi nguyên văn cho AI triển khai

> Hãy xây dựng lại RoboNose cho ESP32-S3 dựa trên tài liệu này và source Pi gửi kèm. ESP phải trực tiếp đọc BME688 + ADS1115 A0 MQ135_1, A1 MQ3_1, A2 MQ135_2, A3 MQ3_2; quản lý session/trial, pipeline thao tác tay, bơm liên tục cả session có opt-in, thu và lưu độc lập, export dữ liệu tái phân tích được. Không thêm van, không suy ppm/IAQ, không gộp hai MQ cùng loại. Giữ raw/null/flags/timing và giấy phép Bosch. Ưu tiên ESP-IDF, module tách trách nhiệm, USB console và microSD; Wi-Fi là tùy chọn. Phân biệt hiện trạng và đề xuất, không khẳng định firmware ESP cũ đã có source khi chưa được cung cấp. Không xóa dữ liệu hoặc sửa dự án Pi để thay thế. Trước phần cứng hãy cung cấp bản build, mock tests, schema/export, pin map còn thiếu và hướng dẫn cụ thể. Chỉ nạp/chạy hardware/bật bơm khi tôi yêu cầu rõ. Không tự ON sau reset/lỗi. Hãy giao đầy đủ source, cấu hình mẫu an toàn, dependency khóa phiên bản, hướng dẫn cài/build/flash/thu/export/recovery, kết quả kiểm thử thực đã chạy và danh sách điểm chưa xác minh. Nếu thiếu thông tin board/chân/SD, tiếp tục phần độc lập phần cứng và hỏi các mục thật sự chặn triển khai.

## 19. Phạm vi thực hiện tài liệu này

Chỉ bổ sung file Markdown bàn giao. Không sửa code/config, không chạy sensor, không mở Serial/GPIO, không bật bơm, không nạp firmware và không thay đổi dữ liệu thu. Các thay đổi working tree đã tồn tại trước lượt này được giữ nguyên. Kiểm tra tài liệu là kiểm cấu trúc, đường dẫn nguồn và diff; không phải nghiệm thu firmware hoặc phần cứng mới.

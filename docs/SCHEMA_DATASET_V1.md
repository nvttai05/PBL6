# RoboNose dataset v1 — stage 02

Schema ID: **`robonose.dataset.v1`**. App `robonose_s3` 0.3.0 giữ demo SIMULATED và thêm adapter HARDWARE/EMULATED ở bước 03. Kết quả đã chạy hiện là phần mềm/emulator/offscreen; chưa đo ADC/BME/đầu ra thật. Không fallback mô phỏng khi hardware lỗi.

## Mapping và đơn vị

| ADS input | ID | Raw |
| --- | --- | --- |
| A0 | `tgs2602` | signed count và V |
| A1 | `mq3_1` | signed count và V |
| A2 | `mq135_2` | signed count và V |
| A3 | `mq3_2` | signed count và V |

`voltage_v = adc_count × 0.0001875`. Không nhân đôi AO. ADS đích là 5 V, gain 2/3, FSR ±6.144 V, single-shot/single-ended, 128 SPS. Bước này chỉ kiểm công thức số mô phỏng. Không suy Rs/ppm của TGS. BME: gas Ω, nhiệt °C, RH %, áp suất hPa. Dashboard đổi gas sang kΩ đúng một lần cho hiển thị.

Schema này khác Pi 2.0 và ControlTest. Đã có source ControlTest tham chiếu nhưng chưa có adapter dữ liệu legacy/Pi: **NEEDS_INPUT Pi source/sample**. Không đổi nhãn MQ135 cũ thành TGS hoặc trộn profile.

## Cấu trúc file

```text
data/<hardware|simulation|emulation>/<ngày>/Phien_<HHMMSS>_<YYYY-MM-DD>_<ID12>/
  session/raw.csv
  session/events.jsonl
  session/metadata.json
  session/checkpoint.json
  trials/index.json
  trials/<Tên_mẫu>_<HHMMSS>_<YYYY-MM-DD>_<ID12>/raw.csv
  trials/<Tên_mẫu>_<HHMMSS>_<YYYY-MM-DD>_<ID12>/metadata.json
  trials/<Tên_mẫu>_<HHMMSS>_<YYYY-MM-DD>_<ID12>/summary.json
```

Storage layout v2 giữ session/trial UUID đầy đủ bất biến trong raw/metadata;
folder hiển thị tên, giờ/ngày UTC+07 và 12 ký tự hex đầu của UUID. Nếu trùng
prefix, tăng lên 20 hoặc 32 ký tự; luôn kiểm tra không ghi đè. Tên gốc UTF-8
vẫn ở metadata, tên folder thay khoảng trắng/ký tự không an toàn bằng `_`,
giữ dấu tiếng Việt và giới hạn phần tên 32 ký tự. Chưa đặt tên dùng
`Chua_dat_ten`. Giờ folder lượt là mốc vào BASELINE, không phải giờ đặt tên;
hardware dùng ánh xạ clock MCU/host, chưa phải thời điểm khí tới cảm biến.

Writer đóng/reopen CSV khi đổi folder trên Windows; acquisition/UI/heartbeat
tiếp tục qua queue. Nếu Windows đang khóa folder, log
`trial_folder_rename_deferred`, giữ ghi dữ liệu và thử lại ở cập nhật metadata
kế tiếp hoặc lúc chốt lượt. Metadata mới có `folder`, `started_at`,
`storage_layout_version`; index có `folder` và `started_at` để trỏ tới lượt.
Tên không thay UUID trong USB/raw. Reader và công cụ kiểm chứng hỗ trợ cả
folder UUID cũ lẫn folder v2. Migration offline chỉ đổi tên folder, giữ mọi
byte trong các file cũ và lưu ánh xạ/journal tại runtime.

Session raw là nguồn chính, liên tục từ MONITOR qua các WAIT/đặt tên/giữa lượt.
Trial export là bản sao các dòng có đúng `trial_id`, giữ seq/context;
**không phải thí nghiệm độc lập thứ hai**.

Trial export được ghi thêm bởi cùng writer khi raw tới. `finish` đánh dấu COMPLETE/ABORTED và mở WAIT_NAME; raw WAIT_NAME tiếp tục liên kết lượt đó. `next` hoặc đóng phiên là barrier cuối: đóng export, ghi index/metadata cuối và gửi file đã đóng cho analysis. **Summary cuối xuất sau next/quit**, gồm dữ liệu đặt tên nhưng thống kê pha chính chỉ tính các segment tương ứng. Không phân tích file đang tiếp tục ghi.

## Cột raw chuẩn

Danh sách và thứ tự chính thức nằm ở `robonose_s3/schema.py:COLUMNS`; recorder dùng DictWriter với kiểm tra cột lạ.

| Nhóm | Trường |
| --- | --- |
| Danh tính | `schema`, `mode`, `session_id`, `boot_id`, `seq` |
| Thời gian | `timestamp`, `mono_s`, `received_at`, `received_mono_s`, `cycle_end_mono_s`, `schedule_lag_s`, `skipped_cycles` |
| Context lúc bắt đầu đọc | `trial_id`, `phase`, `segment_id`, `context_epoch`, `phase_elapsed_s`, `context_straddled` |
| Đầu ra được ra lệnh | `pump_pwm_pct`, `valve_energized`, `air_path_commanded` |
| Cấu hình | `config_hash`, `profile_id`, `quality_flags` |
| BME | `gas_resistance_ohm`, `temperature_c`, `humidity_pct`, `pressure_hpa`, `new_data`, `gas_valid`, `heater_stable`, `bme_status_bits`, `bme_meas_index` |
| Mỗi analog ID | `<id>_adc_count`, `<id>_voltage_v` |
| Mỗi device (4 analog và `bme688`) | `<id>_read_started_mono_s`, `<id>_read_duration_s`, `<id>_status`, `<id>_error`, `<id>_fresh`, `<id>_valid` |

CSV UTF-8 với chuẩn quoting cho dấu phẩy, dấu nháy và newline. `None` ghi ô trống, bool ghi `True`/`False`. JSON dùng null/boolean chuẩn, serializer không xuất NaN/Infinity. Không fill 0/forward-fill, không tạo mẫu bù. Status ERROR/STALE tạo null ở device tương ứng; lỗi một device không xóa device khác. SUSPECT_JUMP giữ nguyên raw/valid và flag cảnh báo mềm. Smoothing/analysis không sửa raw.

Monotonic tính từ clock của phiên mô phỏng; wall time ánh xạ origin + monotonic, biểu diễn UTC+07:00. FakeClock của fixture có origin cố định và được ghi rõ là thời gian ảo. SimDevice sinh offset đọc giả (analog 8 ms/kênh, BME 100 ms, cycle/receive 160 ms); **đây không phải latency đo thực**. `context_straddled` báo conversion giả đi qua deadline/context thay đổi. Deadline hiệu lực được ghi riêng với thời điểm engine xử lý; mẫu đang đọc giữ context đầu vòng dù writer ghi sau chuyển pha. Lịch chậm chỉ tạo một mẫu hiện tại và ghi số skipped, không tạo dòng đo giả cho các mốc bỏ qua.

## Events và metadata

`events.jsonl`: lệnh nhận ở host (`received_mono_s`), lệnh áp dụng (`applied_mono_s`), request ID/result/reason, phase change có `effective_mono_s` và `processed_mono_s`, marker, trial metadata/finish, simulated ON/OFF và checkpoint. Lệnh lặp cùng request ID không thực thi lại trong cache 256 ID. Đây là kết quả mô phỏng, không phải ACK phần cứng.

Metadata ghi mode/schema/app version, config/hash, mapping, requested BME profile, applied **simulated**, Pi reference, production profile null, route rules, trial UUID/index/status/name/notes/intervals, liên kết source và seq range của export. Board vẫn null, hardware_validated false. Profile S3 bring-up là 300°C/100 ms T2/H2/P4; Pi reference 320°C/150 ms T8/H2/P4; không coi chúng tương đương.

Session khi đang chạy: PARTIAL. Quit sạch: CLOSED. Lỗi: ERROR nếu còn ghi được metadata; mất điện có thể để lại PARTIAL hoặc file cắt. Phiên cũ chỉ được phát hiện/báo, không tự resume hoặc đổi thành COMPLETE. COMPLETE chỉ dùng cho quy trình trial đầy đủ; quality độc lập.

## Ghi bền vững và fault

Một writer sở hữu raw/events/metadata, queue mặc định 256. Flush sau mẫu/event; fsync/checkpoint mặc định 5 s và lúc đóng. `last_written_seq` khác `synced_seq`; checkpoint ghi seq đã sync. Metadata dùng temp + replace, không hứa tuyệt đối không mất dữ liệu khi mất điện.

Queue full, lỗi ghi/sync/analysis: engine latch ERROR, PWM mô phỏng 0 và route FILTERED_AIR trước khi đợi log. Không tự ON lại. Writer cố giữ ERROR/PARTIAL và số item chưa commit. Nếu thiết bị lưu trữ không ghi được thì báo lỗi trong UI/process; không thể bảo đảm ghi thêm được chính báo cáo lỗi lên ổ đó. Đóng file một lần; stdin không được join khi đang chờ Enter.

Analysis chạy ở worker riêng trên export đã đóng, đọc streaming, kiểm hash trước/sau; kết quả được writer ghi. Backlog analysis hữu hạn 4 lượt. Nếu đầy thì fault có lý do, không bỏ summary âm thầm. Timeout đóng writer 10 s; quá hạn báo completion chưa xác nhận, output đã OFF. Chưa benchmark fsync/queue hoặc soak dài.

## Quality và summary

Quality version `quality.v1`, cửa sổ 30 s. Mỗi kênh có n/valid_n, union coverage của khoảng hỗ trợ `[t, t+1/hz)`, max gap gồm biên cửa sổ, invalid fraction, mean/median/std/min/max, slope theo phút, range và noise là std mẫu của residual sau detrend tuyến tính. Muốn đánh giá cần ít nhất ceil(30 × hz × 0.8) mẫu valid và đủ span/coverage. Thiếu: WARMING_UP/INSUFFICIENT.

Ngưỡng BME được snapshot trong config: gas slope 5%/phút và range 5%; T 0.3°C/phút và range 0.2°C; RH 1 điểm %/phút và range 1 điểm %; gap 3 s, invalid fraction 0.2; T > 35°C advisory. Analog và pressure chưa có ngưỡng khảo sát: UNCONFIGURED. heater_stable không thay kết luận nền ổn định. Start vẫn được phép; lưu `baseline_started_without_stability` cùng lý do.

Summary streaming theo segment có n/valid/invalid, coverage, max gap, mean/std/min/max/slope và null_reason nếu thiếu. Baseline statistics được liên kết riêng. Trial COMPLETE có thể quality INSUFFICIENT vì thiếu coverage/validity ở các pha; đủ dữ liệu vẫn UNCONFIGURED do analog chưa được khảo sát. Đây là quality độ đủ dữ liệu sơ bộ; đánh giá drift chi tiết có ở live window, chưa có classifier chất lượng toàn lượt.

Median trong summary streaming, delta, AUC, recovery metrics và analyzer Pi **chưa triển khai**, trả lý do `NOT_IMPLEMENTED_*`/NEEDS_INPUT thay vì số giả. Live window có median/noise được kiểm fixture riêng. Không có phép AUC bắc cầu WAIT/gap/extension vì bước này chưa tính AUC.

## Bổ sung bước 03: hardware và emulator

Cột/header/đơn vị CSV v1 giữ nguyên. HARDWARE ghi dưới `data/hardware`, EMULATED dưới `data/emulation`; mode xuất hiện trong raw/metadata/summary/dashboard. EMULATED dùng byte transport giả, không được gọi là cảm biến thật. Firmware phát `robonose.usb.v1`; adapter kiểm version, mapping, FSR/LSB/profile trước BEGIN, không đọc/trộn dữ liệu ControlTest như schema mới.

Trong hardware, `mono_s`, cycle/per-device timing và phase intervals là **MCU boot seconds**; `received_mono_s` là **host process monotonic seconds**. Metadata ghi clock mapping HELLO receive cùng giới hạn USB/queue delay chưa đo. `timestamp` là ước lượng wall time đo theo mapping, `received_at` là lúc host nhận. Trong demo các clock mô phỏng cùng cơ sở; các offset 8/100/160 ms ở mô tả demo không phải latency hardware đo thực.

Nguồn raw hardware luôn giữ context đầu scan của MCU. Sample epoch cũ vẫn có thể được lưu sau ACK mới; snapshot UI chỉ tiến theo epoch/device_ms. Trial export chỉ chốt sau barrier_seq của NEXT/OFF để không mất mẫu đang đọc. Seq lặp/lệch thứ tự ở wire/parser log, không nhân đôi canonical; seq gap/skipped được ghi, không backfill. Wire RX/TX gốc nằm ở `session/wire.jsonl` dạng hex lossless.

ADC_LIMIT giữ count/V gốc, fresh=true nếu có conversion, valid=false để loại khỏi thống kê; ERROR/STALE không điền số cũ. Negative count được giữ dấu. Hello/readback/config thực được snapshot riêng; hash cấu hình không chứa ticket/boot/time/session. Các phần phân tích/threshold/native GUI/soak chưa xong ở bước 02 vẫn chưa được tự coi là đã đạt. Xem [USB_PROTOCOL.md](USB_PROTOCOL.md).

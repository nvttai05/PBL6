# Schema RoboNose 1.0

UTF-8. CSV có header, ô trống nghĩa là không có giá trị; JSON dùng null.
Không dùng 0 thay lỗi. Boolean CSV là `True`/`False`, JSON là boolean.
Giữ độ chính xác số Python, không làm tròn CSV cho giao diện.

## raw.csv

Một dòng cho mỗi vòng acquisition. Nhãn pha và lệnh bơm được chụp **ở đầu vòng đọc**;
các thời điểm đọc riêng thể hiện phép đọc có thể kéo dài qua mốc chuyển pha.

| Trường | Ý nghĩa |
|---|---|
| run_id, seq | UUID lượt bất biến; số dòng bắt đầu 1 |
| timestamp | ISO 8601, Asia/Ho_Chi_Minh +07:00, đầu vòng đọc |
| elapsed_s | Monotonic từ khi mở lượt/session |
| phase, phase_elapsed_s | Pha tại đầu vòng đọc; thời gian từ đầu pha đó |
| sensor_uptime_s | Thời gian từ lúc bắt đầu khởi tạo reader trong phiên; không phải tuổi heater/thiết bị ngoài phiên |
| loop_interval_s | Khoảng cách hai lần bắt đầu vòng liên tiếp; dòng đầu trống |
| loop_duration_s | Tổng thời gian reader của vòng |
| schedule_lag_s | Độ trễ so với lịch vòng; không tạo mẫu bù giả |
| pump_command | ON/OFF/DISABLED/UNKNOWN; lệnh, không có feedback vật lý |
| temperature_c, humidity_pct, pressure_hpa | °C, %RH, hPa |
| gas_resistance_ohm | Ω của phép đo BME gốc, không quy đổi nồng độ |
| gas_valid, heater_stable, new_data | Cờ được đọc từ Bosch status, không suy ra từ giá trị |
| bme_status_bits | Byte trạng thái, dạng số nguyên; mask 0x80/0x20/0x10 |
| bme_meas_index, bme_gas_index | Chỉ số đo/profile driver cung cấp |
| bme_res_heat, bme_idac, bme_gas_wait | Thanh ghi heater gốc driver cung cấp |
| mq135_adc_count, mq3_adc_count | Signed count ADS1115, một conversion mỗi kênh |
| mq135_voltage_v, mq3_voltage_v | V tại chân ADS: count × FSR / 32768 |
| mq135_ao_voltage_v, mq3_ao_voltage_v | V AO suy ra chỉ nếu hệ số chia áp đã được cấu hình; mặc định trống |

Mỗi tiền tố thiết bị `bme`, `mq135`, `mq3` có:

| Hậu tố | Ý nghĩa |
|---|---|
| _read_started_at | ISO bắt đầu phép đọc thiết bị/kênh |
| _read_elapsed_s | Monotonic bắt đầu đọc theo cơ sở thời gian lượt |
| _read_duration_s | Thời gian phép đọc (bao gồm conversion/chờ ready) |
| _status | OK/ERROR/STALE |
| _error | Lý do lỗi hoặc không có dữ liệu mới |
| _fresh | Có dữ liệu mới; False khi lỗi/stale |

Lỗi BME không ngăn đọc ADS; lỗi một kênh không ngăn kênh còn lại.
Không có phép đo mới thì số đo trống, không chép lại mẫu cũ. Gas-invalid vẫn giữ
giá trị với cờ False. `_fresh` ở ADS nghĩa là conversion single-shot mới đã ready.
Timestamp là thời điểm host yêu cầu đọc, không phải timestamp nội bộ sensor.
Đọc tuần tự: BME rồi MQ135 rồi MQ3; không giả định ba tín hiệu đồng thời.

## Pha

MONITOR, BASELINE, WAIT_EXPOSURE, EXPOSURE, WAIT_RECOVERY, RECOVERY, WAIT_FINISH.
Session thêm WAIT_NAME, WAIT_NOTES, BETWEEN_RUNS. Những khoảng chờ vẫn có raw.
Baseline, exposure và từng đoạn recovery có timer monotonic độc lập, không tính
khoảng chờ. Tần suất vòng đọc mục tiêu khác SPS nội bộ ADC.
Deadline là mốc kết thúc pha có timer. Worker tự nhận diện deadline khi bắt đầu
vòng đọc, không chờ UI poll; event chuyển pha dùng mốc hiệu lực đó. Một phép đọc
bắt đầu trước deadline vẫn giữ nhãn đầu vòng và có timestamp thiết bị thể hiện
độ lệch đọc tuần tự. Linux không bảo đảm đọc được mẫu đúng ngay deadline.

## metadata.json

`schema_version`, `program_version`, `software` (Python/platform/dependency),
`run_id`, `kind` (collect/session/monitor), `backend`, `started_at`, `ended_at`,
`elapsed_s`, `rows`, `status`, `end_reason`.

- `sample`: sample_description, person_code, source, sampling_method,
  purge_method, lid_state, distance_cm; văn bản khai báo tự do/tùy chọn.
- `config`: snapshot cấu hình yêu cầu, địa chỉ/kênh, sample_hz, ADC SPS,
  các ngưỡng phân tích, chia áp, pump confirmed và cực tính nếu biết.
- `applied`: driver/backend và cấu hình đã được áp dụng/kiểm tra;
  hardware ghi BME chip/variant, oversampling readback, heater target/requested,
  programmed duration, register và hash library. ADS config readback trước thu.
  Sim ghi cấu hình mô phỏng, seed và hardware_access=false.
- `durations`: thời lượng dự kiến/thực tế của từng pha chính; recovery planned
  là thời lượng gốc cộng extensions.
- `phase_intervals`: từng đoạn với start_s/end_s/actual_s/planned_s;
  khoảng chờ planned_s=null. Đoạn recovery thêm được lưu riêng.
- `extensions`: at_s và duration_s từng lần kéo dài.
- `original_name`, `notes`, `rename_error` nếu có.

PARTIAL trong lúc mở; COMPLETE khi đủ pha và finish đúng lúc; ABORTED do dừng
sớm/EOF/tín hiệu; ERROR do exception/OFF lỗi. Session/monitor COMPLETE nghĩa
phiên kết thúc bình thường, không có nghĩa một lượt collect hoàn thành.
Nếu tiến trình chết không thể xử lý, metadata có thể còn PARTIAL; `rows` có thể
chỉ phản ánh checkpoint fsync gần nhất. Có thể chạy analyze offline dữ liệu đó.
Hủy đặt tên sau thu không đổi trạng thái COMPLETE. Không có claim lưu lượng.

## events.csv

run_id, timestamp, elapsed_s, phase_elapsed_s, phase, event, details_json.
Thời gian cùng cơ sở với raw của cùng lượt. details_json giữ marker nguyên văn,
phase_change from/to, pump_command (không feedback), read_error device/status,
run_start/run_end/session_end, sample_info/durations và lý do dừng.
Các event xử lý trễ vẫn lưu elapsed_s tại mốc hiệu lực; ISO được suy từ thời gian
host hiện tại trừ độ trễ monotonic. Khi đồng hồ hệ thống nhảy, monotonic là cơ sở
cho timer và phân tích. Thứ tự ghi event có thể khác thứ tự elapsed_s khi drain queue.

## summary.json và PNG

Thống kê gốc theo pha và quy tắc lọc công khai trong summary. Baseline có n,
mean, median, sample std (ddof=1), min/max, slope và drift cuối−đầu.
Extrema và delta có dấu đối với mean nền; % chia abs(mean nền) nếu đủ điều kiện.
Slope là hồi quy tuyến tính theo elapsed_s. AUC trapezoid có dấu theo thời gian
thực, đơn vị Ω·s hoặc V·s; ghi auc_covered_s, không nối qua lỗi/khoảng trống lớn.
Không nối hai đoạn recovery riêng, ngay cả khi khoảng chờ không có dòng raw.
Hồi phục có lệch cuối, thời điểm/tuổi mẫu cuối và xu hướng tiến về nền.
Mẫu cuối quá xa cuối pha cho lệch cuối null và lý do.

Pha thiếu/chưa hoàn thành hoặc thiếu nền cho metrics null và reason. Ngưỡng gần
zero, drift, recovery, thiếu mẫu, ADC limit và max_gap_s cấu hình được.
Warnings chỉ thông báo, không xóa dữ liệu. `signals.png` hiển thị giá trị raw kể
cả giá trị có flag không hợp lệ (đánh đỏ); `normalized.png` chỉ dùng mẫu hợp lệ.
PNG/summary có thể tạo lại; raw/events/metadata không bị analyze sửa.
Baseline chưa hoàn thành/không đủ mẫu giữ n quan sát được, các thống kê số trả null
với reason, cả ba tín hiệu chính và T/H/P. Session/monitor không tính đáp ứng theo
nền để tránh trộn lượt; dùng summary của từng collect. NaN/Infinity từ driver được
lưu null kèm lỗi, không coi là dữ liệu fresh/OK.

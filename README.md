# RoboNose v1.0 — thu khảo sát phản ứng cảm biến

Công cụ CLI Python trên Pi 4: BME688, MQ135 tại ADS1115 A0, MQ3 tại A1,
buồng thủy tinh và bơm 12V qua MOSFET. Bạn chọn mẫu, cách lấy khí và thời điểm
tiếp xúc/hồi phục. Chưa có van ba chiều/lọc than; chương trình không tự chuyển
đường khí, không phân loại mùi, không tính ppm/CO2/IAQ.

**Mặc định mô phỏng, bơm disabled.** Triển khai chỉ được kiểm thử bằng mô phỏng
và thiết bị giả. Biên dịch driver không chạy phần cứng. `--hardware` mở I2C và
khởi tạo heater; các lệnh hardware bên dưới dành cho bạn tự chạy sau khi xác nhận dây.

## Môi trường và cài đặt

Đã triển khai trên Raspberry Pi 4 Model B Rev 1.4, Debian 12, ARM64, Python 3.11.2.
Mọi package Python nằm trong `.venv`. Không sửa OS hoặc cài package hệ thống.
Chạy lệnh từ root repo; không cần activate khi dùng đường dẫn `.venv/bin/python`.

```bash
cd /home/pi/robonosev1.0
.venv/bin/python -m robonose doctor --config config.example.toml
.venv/bin/python -m pytest -q
```

Nếu dựng môi trường mới:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m robonose.build_driver
```

`requirements-lock.txt` ghi phiên bản thực sự đã cài/kiểm thử trên Python 3.11 ARM64.
Có thể cài gọn cho sim bằng `.venv/bin/python -m pip install '.[test]'`;
thêm `'.[hardware]'` khi cần cảm biến thật. Trong repo CLI chạy bằng `python -m`
không cần cài chính package RoboNose. Tệp `.so` phải biên dịch lại trên kiến trúc đích.
Compiler `cc` và Linux I2C headers đã có trên Pi này. Chỉ nếu máy mới thiếu:
người dùng tự chạy `sudo apt install build-essential linux-libc-dev` để biên dịch,
hoặc `sudo apt install python3-venv` nếu không tạo được venv. Không cần BSEC.

`doctor` chỉ kiểm tra phiên bản package, cấu hình và sự tồn tại đường dẫn thiết bị.
Nó **không import GPIO, không mở I2C**, không kiểm tra điện áp, wiring hay quyền mở thiết bị.
Trong môi trường triển khai hiện tại `/dev/i2c-1` không hiện diện theo doctor;
chưa xác minh I2C đã được bật trên môi trường chạy phần cứng. Khi tự chạy thật,
nếu đường dẫn còn thiếu, người dùng kiểm tra I2C bằng `sudo raspi-config`
(Interface Options → I2C). Nếu lỗi quyền, kiểm tra quyền `/dev/i2c-1` và nhóm
`i2c` của tài khoản trước khi thay đổi; chỉ khi cần, tự thêm bằng
`sudo usermod -aG i2c pi` rồi đăng nhập lại. Bơm vẫn disabled trong bước này.

## Mô phỏng

Một lượt tự động ngắn để kiểm tra file, không dùng phần cứng:

```bash
.venv/bin/python -m robonose collect --sim --pump-disabled --auto \
  --sample-hz 10 --baseline 1 --exposure 1 --recovery 1 \
  --auto-warmup 1 --auto-wait 0.5
```

`--auto` chỉ được phép trong sim. `--sim-fail-every 7` mô phỏng lỗi BME mỗi 7 vòng.
Sim dùng seed cố định, tái lập chuỗi giá trị với cùng chuỗi pha và số phép đọc;
timestamp/thời gian thực không cố định. Đây là đáp ứng minh họa, không phải mô hình
vật lý hoặc hiệu chuẩn cảm biến.

Một lượt tương tác mặc định 30–60–60:

```bash
.venv/bin/python -m robonose collect --sim --pump-disabled \
  --sample-description "mẫu tùy chọn" --sampling-method "mở nắp đặt bông"
```

1. `MONITOR`: dữ liệu được ghi ngay. Chờ warmup theo cảm biến thực tế; baseline
   không thay thế warmup. Có thể dùng `durations 30 60 60` để đổi thời lượng trước lượt.
2. Gõ `start` khi muốn bắt đầu BASELINE. Hết 30 s chuyển WAIT_EXPOSURE, vẫn ghi.
3. Gõ `expose` đồng thời đưa mẫu/thực hiện tiếp xúc. EXPOSURE kéo dài 60 s.
4. Đến WAIT_RECOVERY, gõ `recover` đồng thời bỏ mẫu/xả buồng theo cách bạn chọn.
5. Hết RECOVERY 60 s, chương trình ở WAIT_FINISH và tiếp tục ghi. Gõ `finish`
   để hoàn thành, hoặc `extend 30`, `extend 60`, `extend 90.5` để thêm một đoạn hồi phục.
   Hết đoạn thêm lại chờ quyết định. Không mặc định 60 s nghĩa là đã sạch.
6. Sau thu: `name tên tùy ý` rồi `notes ghi chú`; dùng `skip` hoặc Enter ở mỗi câu
   hỏi để giữ tên tự động/bỏ ghi chú. Gõ `next` để mở lượt MONITOR mới trong cùng phiên;
   cảm biến không bị khởi tạo lại. Gõ `quit` để kết thúc phiên.

Terminal tương tác dùng `prompt-toolkit` (`PromptSession` và `patch_stdout`): một bộ dựng màn hình giữ dòng đang gõ, hỗ trợ Backspace và Unicode, đưa trạng thái lên phía trên prompt. Dependency đã nằm trong `requirements-lock.txt`; `pyte` dùng cho kiểm thử màn hình PTY. Nhập lệnh không chặn vòng đọc/lưu. Khi chờ tên/ghi chú hoặc giữa lượt, session log
vẫn thu ở WAIT_NAME/WAIT_NOTES/BETWEEN_RUNS. Phân tích chạy ở worker riêng.
Pha có timer kết thúc ở deadline monotonic; worker gắn nhãn WAIT ngay từ deadline,
kể cả khi giao diện in thông báo trễ. Thời điểm đưa/bỏ mẫu vẫn do bạn thao tác và
đánh dấu, chương trình không xác nhận chuyển khí vật lý.

| Lệnh trong phiên | Tác dụng |
|---|---|
| `help`, `status` | Trợ giúp, pha/thời gian còn lại/giá trị và lệnh bơm |
| `mark văn bản` | Đánh dấu thao tác, trạng thái buồng hay sự kiện tùy ý |
| `info sampling_method văn bản` | Đổi mô tả trước baseline |
| `info sample_description ...` | Mô tả mẫu tự do |
| `info source/person_code/purge_method/lid_state/distance_cm ...` | Dùng **một tên trường** mỗi lệnh, ví dụ `info source áo` |
| `durations 30 60 60` | Đổi thời lượng trước baseline hoặc giữa lượt |
| `pump on`, `pump off` | Chỉ dùng khi hardware và bơm đã enable đầy đủ |
| `abort` | Kết thúc sớm, giữ dữ liệu và trạng thái ABORTED |
| `finish` | COMPLETE chỉ ở WAIT_FINISH; dùng sớm sẽ ABORTED |
| `quit`, Ctrl+C, SIGTERM, EOF stdin | Thoát có xử lý; lượt đang thu ABORTED |

Các trường mô tả đều tùy chọn, văn bản tự do; không bắt class, số trial hay mã người.
Khoảng cách lưu theo khai báo của người dùng, không tự đo hoặc suy ra.

## Cấu hình và hardware

`config.example.toml` là cấu hình pump-disabled chạy được. Khi cần chỉnh, sao chép
thành file riêng, ví dụ `config.toml`, rồi dùng `--config config.toml`. Tên khóa lạ
bị từ chối để tránh lỗi gõ. `--pump-disabled` ghi đè việc enable bơm trong file.

Thông số khởi điểm: BME688 `0x77`; heater mục tiêu 320°C/150 ms;
oversampling T×8/H×2/P×4, filter OFF, FORCED mode. ADS1115 `0x48`, gain=1,
128 SPS, single-shot, A0 MQ135/A1 MQ3. Cấu hình địa chỉ/kênh/heater/oversampling/gain/SPS được.
`sample_hz=1` là tốc độ vòng ghi mục tiêu, **khác** 128 SPS của conversion ADC.
Phép đọc BME và hai kênh tuần tự có độ trễ; tốc độ quá cao sẽ giảm tốc độ đạt được,
không lặp lại giá trị cũ hoặc tạo burst bù. Dữ liệu lưu interval, duration và lag.

Driver BME: [Bosch BME68x SensorAPI v4.4.8](https://github.com/boschsensortec/BME68x_SensorAPI),
vendored nguyên bản, giấy phép BSD-3-Clause. Bridge Linux I2C kiểm tra chip ID
và biến thể gas-high; từ chối gas-low BME680. Dùng API `bme68x_set_conf`,
`bme68x_get_conf`, `bme68x_set_heatr_conf`, `bme68x_set_op_mode`, `bme68x_get_data`.
Pressure Pa đổi sang hPa; gas đã là Ω; humidity của nhánh FPU là %RH
(đối chiếu phép tính trong code, không dùng chú thích x1000 của struct).
Các mask trạng thái Bosch 0x80 new-data, 0x20 gas-valid, 0x10 heater-stable được lưu.
Heater 150 ms có thể lượng tử hóa; metadata ghi cả yêu cầu và thời gian đã lập trình
(mặc định register mã hóa 148 ms), không khẳng định đo được nhiệt độ heater.
Ambient dùng cho tính heater là 25°C, được ghi rõ trong metadata.

ADS1115 đọc thanh ghi theo [datasheet TI](https://www.ti.com/lit/ds/symlink/ads1115.pdf),
kiểm tra config readback và ready với timeout; đọc conversion đúng một lần cho
mỗi kênh, rồi tính `voltage = signed_count × full_scale / 32768`.
Không dùng hai property gây hai phép chuyển đổi để ghép count/voltage.
ADS không có chip ID để tự chứng minh model: cần xác nhận module đúng ADS1115.

Monitor thật, bơm disabled — **bạn tự chạy**, sau khi xác nhận nguồn/đường tín hiệu:

```bash
.venv/bin/python -m robonose monitor --hardware --pump-disabled --config config.example.toml
```

`monitor` ghi liên tục đến `quit`/Ctrl+C hoặc EOF (Ctrl+D khi dòng trống); có thể thêm `--duration 60` để giới hạn theo dõi trước khi bắt đầu lượt. Gõ `start` ngay trong MONITOR để chuyển sang BASELINE và thu 30–60–60, giữ nguyên reader và heater đang chạy. Giới hạn monitor không cắt lượt đã bắt đầu. Chương trình yêu cầu reader/vòng thu hoạt động; hiện không có ngưỡng warmup tự động, bạn tự quyết định thời điểm đủ warmup. Nếu vòng thu chưa sẵn sàng, thông báo nêu rõ điều kiện còn thiếu.
Không coi số đọc hợp lệ là bằng chứng wiring/hiệu chuẩn hoàn chỉnh. Đối chiếu
đơn vị, cờ chất lượng, các kênh, điện áp và timestamps trong raw.

Thu thật 30–60–60, thao tác terminal giống mô phỏng:

```bash
.venv/bin/python -m robonose collect --hardware --pump-disabled \
  --config config.example.toml --baseline 30 --exposure 60 --recovery 60 \
  --sample-description "mô tả mẫu" --sampling-method "cách lấy khí" \
  --purge-method "cách xả buồng" --lid-state "trạng thái nắp"
```

JZ-MOS: TRIG/PWM nối BCM17 (chân vật lý 11); GND điều khiển nối GND Pi,
nguồn bơm 12 V riêng. v1.0 chỉ bật/tắt, không PWM. Cực tính TRIG chưa được xác nhận:
template giữ enabled=false, confirmed=false và không có active_high.
Bơm mặc định OFF khi được enable, OFF khi kết thúc lượt/abort/thoát có xử lý.
Sim và --pump-disabled không mở GPIO. pump_command là lệnh đã gửi, trạng thái vật lý
và lưu lượng **chưa đo được**. Code không bảo đảm OFF khi Pi chưa khởi động,
mất điện hoặc bị kill cưỡng bức; phải kiểm tra chân/module trên hardware.

Tạo cấu hình riêng, không ghi đè file có sẵn, rồi khai báo cực tính sau khi đã xác nhận:

```bash
cp --no-clobber config.example.toml config.jz-mos.toml
nano config.jz-mos.toml
```

Trong [pump], giữ gpio_bcm=17; đặt confirmed=true và thêm active_high=true nếu đã
xác nhận HIGH bật, hoặc active_high=false nếu LOW bật. Giữ enabled=false để chỉ
bật điều khiển qua --enable-pump. Nếu chưa xác nhận, giữ disabled và không chạy thử thật.

Lệnh thử ngắn độc lập, không mở cảm biến:

```bash
.venv/bin/python -m robonose pump-test --sim --seconds 2
# Bạn tự chạy sau kiểm tra nguồn/dây/cực tính:
.venv/bin/python -m robonose pump-test --hardware --enable-pump \
  --config config.jz-mos.toml --seconds 2
```

pump-test gửi OFF → ON 2 giây theo monotonic → OFF, cuối cùng cleanup OFF.
Có giới hạn thử <=10 giây. Sim chỉ diễn tập trình tự, mọi pump_command=DISABLED.
Log riêng kind=pump_test chứa raw/events/metadata/summary; không có phép đo
cảm biến và không có đồ thị cảm biến. Lệnh thu có --enable-pump cho phép pump on/off
thủ công trong terminal, giữ reader và ghi lệnh bơm trong CSV/events.

Cần xác nhận điện áp cấp MQ/ADS, AO lớn nhất và chia áp ở A0/A1.
Gain đo không thay thế giới hạn điện áp chân ADC. Khi chưa có hệ số chia áp,
chỉ lưu điện áp tại ADS; trường AO để trống. Cần ghi thời gian warmup/hiệu chuẩn,
thể tích buồng, hướng khí/vị trí bơm, lưu lượng nếu biết và cách xả thực tế.

## Độ ổn định và chất lượng phép đo

Trong MONITOR/BASELINE, dòng ổn định hiển thị xu hướng gas (%/phút), T (°C/phút),
H (điểm %RH/phút) trên cửa sổ [stability]. Gas phải có status/fresh và các flag hợp lệ;
T/H dùng status/fresh. Tiêu chí kết hợp slope hồi quy theo elapsed_s và range,
số mẫu tối thiểu, độ phủ cửa sổ, tỷ lệ thiếu và gap/mẫu cũ. Không chỉ xét heater_stable.
Mặc định cửa sổ 30 s, tối thiểu 5 mẫu và 80% độ phủ; đây là tiêu chí quan sát,
**không phải thời gian warmup bắt buộc**. Chỉnh các ngưỡng trong config theo khảo sát.

start luôn cho người dùng chủ động bắt đầu khi vòng thu hoạt động; đang trôi hoặc
chưa đủ dữ liệu sẽ cảnh báo, ghi pre_baseline_quality và baseline_started_without_stability.
Sau lượt, baseline_quality/baseline_unstable ghi chất lượng toàn BASELINE;
summary có measurement_quality. stable/baseline_unstable=null khi chưa đánh giá đủ
hoặc pha thiếu. Nhiệt độ vượt temperature_warning_c (mặc định 35°C) là cảnh báo
riêng; không tự bù nhiệt hay kết luận nguồn nhiệt. Nền đang trôi khiến đáp ứng tương đối
khó diễn giải; summary và cả hai PNG ghi cảnh báo. Các thống kê vẫn là thay đổi
tín hiệu, không phải bằng chứng mùi/ppm/IAQ. Raw giữ nguyên.

Ở hai kênh, khai báo divider_description đúng thực tế. Nếu đã xác nhận 10 kΩ/10 kΩ,
mỗi kênh cần divider_factor=2.0 riêng và description “Đã xác nhận 10 kΩ/10 kΩ”.
Khi chưa xác nhận, description nói rõ dự kiến, factor không đặt và AO để null.
Metadata adc_inputs ghi vị trí đo ADS, kênh, mô tả chia áp và hệ số đã xác nhận.
Giá trị voltage_v luôn là điện áp tại ADS cùng conversion với count; ao_voltage_v
là ước lượng tính riêng, không phải phép đo AO độc lập.

## File và phân tích

Mỗi lượt là thư mục riêng theo ngày: `data/simulation/YYYY-MM-DD/...` hoặc
`data/exploration/YYYY-MM-DD/...`. Tên tự động chứa ngày giờ + run_id UUID,
được tạo trước khi thu. Tên tùy ý sau thu giữ UUID, không ghi đè hay đi ra ngoài output.
Đổi tên lỗi giữ đường dẫn cũ và báo lỗi. Metadata giữ tên nguyên văn và ghi chú.

- `raw.csv`: dữ liệu gốc, ghi tăng dần, flush mỗi dòng.
- `events.csv`: chuyển pha, marker, bơm, lỗi, kết thúc.
- `metadata.json`: cấu hình yêu cầu/đã áp dụng, mẫu, phiên bản, thời lượng, trạng thái.
- `summary.json`: thống kê, quy tắc lọc, lý do null và cảnh báo.
- `signals.png`: gas, MQ135, MQ3, T/H/P, vùng pha và mốc sự kiện.
- `normalized.png`: phần trăm thay đổi so với nền hợp lệ; không thay đổi raw.

Phiên collect còn có **session log** riêng (`kind=session` trong metadata), ghi
liên tục kể cả đặt tên/giữa lượt; raw của lượt và session có thể trùng mẫu.
Không ghép hai raw đó như dữ liệu độc lập. Mỗi lượt có thời gian/run_id riêng;
`sensor_uptime_s` liên tục trong phiên. Monitor độc lập có `kind=monitor`.
Session/monitor chỉ có đồ thị liên tục; thống kê đáp ứng nền trả null với lý do,
tránh gộp baseline nhiều lượt thành một nền.

Raw/events fsync định kỳ (mặc định 5 s), đồng bộ khi đóng; metadata ghi atomic.
Ctrl+C/SIGTERM/exception cố gắng OFF bơm, giữ raw và đánh dấu trạng thái.
Hủy nhập tên sau COMPLETE không đổi lượt thành lỗi. Không bảo đảm mọi dữ liệu
khi mất điện, SIGKILL, filesystem lỗi hoặc bơm không nhận lệnh OFF.

Phân tích lọc status OK + fresh; gas thêm gas_valid/heater_stable/new_data.
Giá trị có flag không hợp lệ vẫn còn trong raw. Các pha chờ không vào baseline,
exposure/recovery chính. Nền thiếu/chưa đủ hoặc pha chưa hoàn thành cho metrics
liên quan null và lý do; % nền gần zero là null. AUC có dấu theo thời gian thực,
không nối qua dòng lỗi, hai đoạn recovery khác nhau (kể cả khoảng chờ không có mẫu)
hoặc khoảng cách vượt `analysis.max_gap_s`; ghi thời gian
được tích phân. Cảnh báo không xóa mẫu. Các ngưỡng có trong `[analysis]`.

Phân tích lại offline, thay đường dẫn bằng thư mục lượt in trên terminal:

```bash
.venv/bin/python -m robonose analyze "data/simulation/YYYY-MM-DD/THU_MUC_LUOT"
```

Lệnh này chỉ cập nhật summary/PNG, không sửa raw/events/metadata. PNG dùng Agg,
không cần desktop. Nếu phân tích lỗi, raw vẫn giữ và tiến trình báo mã thoát khác 0.
Schema chi tiết: [docs/schema.md](docs/schema.md). Thiết kế: [docs/design.md](docs/design.md).

## Kiểm thử và giới hạn đã biết

Test tập trung vào timer/pha chờ, extension, nhập lệnh không chặn thu,
sim không import hardware, lỗi/null/flag, conversion count-voltage,
lưu khi thoát sớm/exception/SIGINT/SIGTERM, tên trùng/path traversal,
OFF best-effort bằng thiết bị giả, thống kê/AUC/PNG và giữ raw.

Lặp lại kiểm tra tương tác ngắn có chứng cứ số dòng tăng khi chờ nhập lệnh:

```bash
.venv/bin/python scripts/verify_interactive.py
```

Script giữ stdin mở, gửi một phần lệnh tiếng Việt chưa có newline, quan sát CSV
tăng trong MONITOR/WAIT_EXPOSURE/WAIT_RECOVERY/WAIT_FINISH và session WAIT_NAME/
WAIT_NOTES; có guard chặn import/mở thiết bị phần cứng. Nó tạo dữ liệu sim mới và
report/console riêng trong `logs/`, không ghi đè lượt cũ. Kết quả rà soát nằm ở
[docs/review.md](docs/review.md).

Trong lượt hoàn thiện này chỉ test sim/mock; đã đọc lượt hardware COMPLETE do người dùng thu, không tự chạy hardware. Chưa xác nhận
điện áp, calibration, heater thực tế, lưu lượng hoặc hoạt động MOSFET/bơm.
Không tự commit/push. `.gitignore` loại `.venv`, `data`, `logs`, cache,
binary build và secrets `.env`; sao lưu dữ liệu thu bằng cách riêng.

## Checklist một lượt thử tích hợp

1. Chạy doctor và monitor hardware với pump-disabled. Đối chiếu gas/T/H,
   cờ chất lượng, điện áp ADS và xu hướng; ghi mark cho trạng thái nắp/nguồn bơm.
   Nếu gas tiếp tục tăng hoặc T cao, ghi nhận chất lượng và khảo sát warmup/vị trí
   cảm biến, không gọi đó là phản ứng mùi. Xác nhận nguồn MQ, ADS và chia áp thực tế.
2. Xác nhận cực tính JZ-MOS, chân BCM17/physical11, GND và nguồn 12 V riêng.
   Bạn tự cấp nguồn, kiểm tra OFF trước ứng dụng/khởi động Pi; chạy pump-test thật
   OFF → ON 2 s → OFF. Đối chiếu bơm thực tế với events; chưa đạt thì không thu với bơm.
3. Thu 30–60–60. Chọn thu bằng ống hoặc mở nắp, khai báo sampling_method/purge_method
   và lid_state, đánh dấu thao tác thực tế bằng mark. Phân biệt MONITOR/warmup với
   BASELINE, dùng expose/recover đúng lúc đưa/bỏ mẫu. Chỉ dùng pump on/off khi
   đã enable rõ ràng; chương trình không tự chuyển đường khí.
4. Sau RECOVERY chọn finish hoặc extend; đặt tên/ghi chú hoặc skip. Kiểm tra đủ file,
   COMPLETE chỉ là hoàn thành pipeline, không xác nhận baseline ổn định hay buồng sạch.
   analyze lại offline và xem measurement_quality/raw/% thay đổi. next cho lượt kế tiếp.

```bash
.venv/bin/python -m robonose collect --hardware --enable-pump \
  --config config.jz-mos.toml --baseline 30 --exposure 60 --recovery 60 \
  --sample-description "mẫu tự chọn" --sampling-method "bằng ống hoặc mở nắp" \
  --purge-method "cách xả thực tế" --lid-state "trạng thái nắp"
.venv/bin/python -m robonose analyze "data/exploration/YYYY-MM-DD/THU_MUC_LUOT"
```

Nếu chưa xác nhận bơm, thay --enable-pump bằng --pump-disabled; vẫn thu bằng thao tác tay.

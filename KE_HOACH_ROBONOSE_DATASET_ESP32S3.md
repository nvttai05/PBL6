# Kế hoạch RoboNose: thu dataset bằng ESP32-S3 và laptop USB

Ngày: 06/11/2026, múi giờ Asia/Ho_Chi_Minh. Trạng thái: kế hoạch để thống nhất trước khi cài môi trường và triển khai với Codex trên Windows. Tài liệu này chưa phải source đã triển khai hoặc kết quả nghiệm thu.

Cập nhật theo yêu cầu mới nhất: chương trình thu hardware tự bật bơm PWM 80% và vào warm-up; điều khiển từng pha bằng lệnh terminal `start`, `expose`, `recover`, `finish`, `name Mau1`, `next`, `quit`. Thời gian hết chỉ đưa pha vào trạng thái WAIT; không tự bắt đầu pha tiếp theo.

## 1. Căn cứ và các quyết định đã chốt

Đã đọc toàn bộ 19 mục, 421 dòng của `BAN_GIAO_ROBONOSE_ESP32S3.md`. SHA-256 bản đầu vào: `068fb3f01259597e9ff66b330c804e286e0ea918db1a8324c8656bf82564f99b`.

Bản bàn giao là đặc tả và mô tả source Pi; chưa có repository Pi trong tệp đính kèm. Các thuật toán, tên file và thông số của hệ Pi dưới đây được hiểu theo bản bàn giao, chưa được xác minh bằng việc chạy source Pi. Khi triển khai, Codex cần đọc working tree thực tế, gồm các thay đổi chưa commit và các test, để tái sử dụng chính xác.

Các quyết định của người dùng trong cuộc trao đổi hiện tại được ưu tiên so với đề xuất trong bản bàn giao:

| Nội dung | Đích triển khai |
| --- | --- |
| Thu và lưu | ESP32-S3 đọc/điều khiển; laptop Windows luôn kết nối USB, lưu và hiển thị |
| Cảm biến thay mới | TGS2602 thay **MQ135 #1 tại A0**, không phải A2 |
| Thời lượng mặc định | Baseline 60 s → Exposure 120 s → Recovery 60 s |
| Chuyển pha | Lệnh terminal bắt đầu từng pha; hết thời lượng tự sang WAIT tương ứng |
| Chuyển van | Phần mềm tự đặt theo pha đã được lệnh chấp nhận; không cần gõ lệnh van riêng |
| Warm-up/MONITOR | Đầu lấy mẫu; van B/ON |
| Baseline | Đầu lấy mẫu; van B/ON |
| Exposure | Đầu lấy mẫu; van B/ON |
| Recovery và giữa các lượt | Bộ lọc khí; van A/OFF |
| Theo dõi | Giá trị hiện tại, biểu đồ, pha/countdown, lỗi, độ ổn định và chất lượng lượt ngay khi thu |
| Bơm | Chạy chương trình thu hardware → tự bật PWM **80%**, chạy liên tục qua warm-up/pha/WAIT/đặt tên/next; `quit` hoặc lỗi dừng |
| Triển khai | Thống nhất kế hoạch trước, sau đó hướng dẫn từng bước dùng Codex trong VS Code |

Từ “warm up(motor)” được hiểu là warm-up/MONITOR với bơm chạy. Việc chạy chương trình thu hardware là thao tác bắt đầu phiên đã được người dùng yêu cầu: sau khi kết nối đúng firmware, kiểm cấu hình/controller và khởi tạo log thành công, phần mềm tự bật bơm 80% rồi vào warm-up. Không thêm nút Start Session hoặc yêu cầu xác nhận bật bơm mỗi lần. Lệnh `start` chỉ bắt đầu baseline. Demo và kiểm thử không tác động tải thật; bo lúc boot/reset trước khi app kết nối vẫn OFF.

Những đề xuất cũ về microSD, ESP tự thu khi rút laptop, không có van hoặc không có bộ lọc không áp dụng cho bản USB này. Mất laptop/USB là lỗi của phiên đang thu; dữ liệu chỉ đã lưu trên laptop mới là dữ liệu bền vững của hệ này.

## 2. Phần cứng đích

### 2.1 Kênh analog sau khi thay

| ADS1115 | Cảm biến | ID dữ liệu đề xuất | Nguồn module |
| --- | --- | --- | --- |
| A0 | TGS2602 module VCC/GND/AOUT/DOUT | `tgs2602` | 5 V ngoài |
| A1 | MQ3 #1 | `mq3_1` | 5 V ngoài |
| A2 | MQ135 #2 | `mq135_2` | 5 V ngoài |
| A3 | MQ3 #2 | `mq3_2` | 5 V ngoài |

Ngắt nguồn, tháo MQ135 #1 và nối TGS2602: VCC→5 V ngoài, GND→GND chung, AOUT→A0, DOUT để trống. Đấu theo nhãn trên PCB, không suy thứ tự chân từ module MQ. Kiểm tra điện áp tại ADS và AOUT thực tế khi bring-up.

Bộ ControlTest 2.1 đã gửi trước đây gán TGS2602 tại A2. Bản dataset mới phải sửa đồng bộ firmware, hello/channel map, parser, CSV, giao diện, demo, test và analyzer sang A0. Chỉ đổi nhãn hiển thị sẽ tạo dữ liệu sai danh tính cảm biến. Dữ liệu lịch sử giữ nguyên danh tính và vị trí khi đã thu.

### 2.2 Chân và đường đo hiện tại

| Chức năng | Chân/kết nối |
| --- | --- |
| BME688 SDA/SCL | GPIO8 / GPIO9, bus riêng, nguồn 3,3 V, ưu tiên 0x77 |
| ADS1115 SDA/SCL | GPIO10 / GPIO11 qua BSS138, bus riêng, địa chỉ 0x48 |
| ADS1115 VDD | 5 V ngoài; không dùng cầu chia áp hiện tại |
| BSS138 | HV 5 V, LV 3,3 V, GND chung; cặp HV/LV tương ứng |
| Bơm PWM | GPIO5 qua MOSFET D4184, tải 12 V |
| Van | GPIO4 qua kênh MOSFET riêng, cuộn van 12 V |
| Van A/OFF | Ngắt điện cuộn van; buồng thông với bộ lọc khí |
| Van B/ON | Cấp điện cuộn van; buồng thông với đầu lấy mẫu |
| Laptop | USB Serial, phân biệt native USB CDC với USB–UART theo bo thực tế |

ADS giữ gain 2/3, FSR ±6,144 V, 128 SPS, single-shot, đọc A0→A3; một bộ cảm biến khoảng 1 Hz. Điện áp trực tiếp = count × 0,0001875 V; không nhân 2. Đầu vào phải nằm trong giới hạn hoạt động GND–VDD, kể cả khi chọn FSR ±6,144 V. Cấp/ngắt nguồn module analog và ADS theo cùng nhánh để tránh AOUT còn điện khi ADS mất nguồn.

Đối chiếu model board/flash/PSRAM và chân thực trước build/nạp. Giữ cách cấp nguồn và MOSFET đã thử; kiểm lại mức OFF khi reset, diode cho tải cảm, sụt nguồn khi bơm chạy và đường hồi dòng. Đây là các kiểm tra điện thực tế, không thể kết luận từ mock test.

## 3. Kiến trúc đề xuất và công nghệ

| Nơi chạy | Trách nhiệm |
| --- | --- |
| ESP32-S3 | Một owner đọc cảm biến; timing từng phép đọc; trạng thái/đồng hồ pha; PWM/van; ACK; watchdog; phát telemetry |
| Laptop: Serial worker | Một owner COM, đóng khung/kiểm dữ liệu, request ID, ACK, phát hiện reset/mất seq |
| Laptop: session và writer | UUID phiên/lượt, metadata, lưu raw/events/checkpoint, liên kết trial với session, health của việc ghi |
| Laptop: quality/analysis | Độ ổn định, độ phủ, lỗi, đặc trưng baseline/response/recovery, thống kê và hình xuất |
| Laptop: giao diện | Snapshot số đo/pha/ghi file, biểu đồ và thao tác; không tự đọc I2C hoặc ghi file dài trong UI handler |
| Laptop: terminal | Đọc lệnh người dùng không chặn acquisition/writer/UI; gửi lệnh qua cùng Serial worker và in trạng thái/lệnh hợp lệ tiếp theo |

Đề xuất firmware C/C++ trên Arduino-ESP32, kế thừa driver ADS, Bosch và bộ điều khiển đầu ra của bản test đã dùng. Tách logic thành module có test; `.ino` chỉ làm entry point rõ ràng. Giữ cách nạp bằng Arduino IDE và thêm Arduino CLI để Codex build có log tái lập. Chọn/khóa core sau khi ghi nhận cấu hình đang nạp thành công và build thử thật trên máy người dùng.

Đề xuất ứng dụng Windows bằng Python 3.11 x64 + PySide6/Qt Widgets + pyqtgraph; pyserial cho USB; NumPy cho tính toán và Matplotlib cho hình báo cáo offline. Dùng `.venv` riêng, khóa phiên bản sau smoke test. PySide6 cài qua pip có Qt đi kèm, không yêu cầu cài cả Qt SDK. Đây là lựa chọn thiết kế đề xuất, chưa được cài trong lượt lập kế hoạch.

ESP là owner duy nhất của phase/deadline khi lệnh đã được chấp nhận. Laptop chuyển các lệnh terminal qua Serial worker; MCU kiểm đúng trạng thái rồi bắt đầu pha hoặc đưa về WAIT khi hết thời gian. Không có hai bộ đếm độc lập cùng tự đổi pha. Đồng hồ giao diện suy ra từ telemetry/monotonic; UI chậm không được kéo dài pha mà không ghi nhận. Chờ người dùng gõ lệnh là thời gian WAIT có chủ đích, không phải phần kéo dài của pha trước hoặc pha sau.

Sensor acquisition và xử lý lệnh/đầu ra được tách để thời gian chờ BME/ADS và USB không chặn OFF hoặc chuyển pha. Dùng owner/mutex/queue hữu hạn theo nhu cầu, không nhân đôi reader hoặc giữ toàn bộ phiên trong RAM. Không tối ưu đọc chồng lấp trước khi lịch tuần tự, timing và nhãn pha đã đúng.

## 4. Quy trình thu theo đường khí người dùng chọn

### 4.1 Bảng trạng thái và lệnh terminal

| Trạng thái | Đường khí | Cuộn van | Bơm | Điều kiện chuyển tiếp |
| --- | --- | --- | --- | --- |
| Khởi tạo kết nối/log | Khí lọc | OFF | OFF | Tự kiểm điều kiện khởi tạo rồi tự bật 80% |
| WARMUP/MONITOR | Đầu lấy mẫu | ON | 80% | Gõ `start` |
| BASELINE | Đầu lấy mẫu | ON | 80% | Hết 60 s → WAIT_EXPOSURE |
| WAIT_EXPOSURE | Đầu lấy mẫu | ON | 80% | Đặt mẫu/vị trí đầu lấy mẫu rồi gõ `expose` |
| EXPOSURE | Đầu lấy mẫu | ON | 80% | Hết 120 s → WAIT_RECOVERY |
| WAIT_RECOVERY | Đầu lấy mẫu | ON | 80% | Gõ `recover` |
| RECOVERY | Khí lọc | OFF | 80% | Hết 60 s → WAIT_FINISH |
| WAIT_FINISH | Khí lọc | OFF | 80% | Gõ `finish` hoặc `extend <s>` |
| WAIT_NAME / BETWEEN_RUNS | Khí lọc | OFF | 80% | Gõ `name Mau1`, notes tùy chọn, rồi `next` |
| `next` → MONITOR | Đầu lấy mẫu | ON | Giữ 80% | Quan sát/chuẩn bị rồi gõ `start` cho lượt mới |
| `quit` / thoát chương trình / lỗi phiên | Khí lọc | OFF | OFF | Đóng/sync log; không tự bật lại sau lỗi |

Lệnh hợp lệ mới bắt đầu pha; thời lượng không tự kích hoạt pha tiếp theo. Hết baseline chỉ dừng bộ đếm baseline và chờ `expose`. Hết exposure vẫn giữ đầu lấy mẫu ở WAIT_RECOVERY; chỉ khi `recover` được chấp nhận mới đổi van về khí lọc và bắt đầu đếm recovery. Hết recovery chờ `finish`, không tự đóng lượt. Phần mềm tự điều khiển van theo bảng; người dùng không phải gõ VALVE ON/OFF riêng.

Terminal và đồ thị cùng chạy. Mọi WAIT, lúc gõ tên/notes và giữa lượt vẫn đọc và lưu session raw, với nhãn trạng thái riêng. Không cộng thời gian WAIT vào 60/120/60 s của các pha chính. `finish`, `name` và `next` không phát lệnh bật bơm lại hoặc khởi tạo lại reader/heater.

Tên mặc định có thể để trống cho tới sau `finish`: `name Mau1` cập nhật metadata của lượt vừa kết thúc. Không bắt nhập tên trước `start`. Giữ UUID làm ID/thư mục lưu chính; tên tiếng Việt hoặc trùng tên không ghi đè dữ liệu. Ghi chú tùy chọn; `next` không bị chặn chỉ vì chưa có notes. Khi bỏ qua tên, giữ trạng thái chưa đặt tên và UUID.

### 4.2 Ví dụ một phiên và thao tác vật lý

```text
Mở chương trình → kết nối/log sẵn sàng → bơm 80% → WARMUP/MONITOR
start
  [BASELINE 60 s → WAIT_EXPOSURE; tiếp tục đọc/lưu]
expose
  [EXPOSURE 120 s → WAIT_RECOVERY; tiếp tục đọc/lưu]
recover
  [van về khí lọc; RECOVERY 60 s → WAIT_FINISH]
finish
name Mau1
next
  [MONITOR qua đầu lấy mẫu; bơm vẫn 80%]
start
  [lặp chu trình cho lượt tiếp theo]
quit
  [bơm OFF, van khí lọc, lưu/đóng phiên]
```

Baseline là điều kiện nền đã khai báo đi qua đầu lấy mẫu. Tới WAIT_EXPOSURE người dùng chủ động đặt mẫu/đầu hút ổn định về vị trí rồi gõ `expose`; không có đồng hồ ép phải đặt mẫu đúng một thời điểm chuyển pha tự động. Lệnh là mốc bắt đầu pha theo phần mềm, không chứng minh thời điểm khí thực đến cảm biến. Nếu đã có đáp ứng trong WAIT_EXPOSURE trước lệnh, raw đó vẫn được giữ để kiểm tra; không sửa nhãn hồi tố hoặc gộp WAIT vào pha chính.

Giữ `mark <nội dung>` làm tùy chọn khi cần ghi thêm thời điểm thao tác. Lưu thời điểm ứng dụng nhận lệnh, thời điểm MCU chấp nhận/áp dụng và context mẫu. `recover` gắn với việc đổi đường khí sang lọc; không cần người dùng tự đấu/chuyển ống cho thao tác này. UI/terminal báo rõ pha hiện tại, thời gian còn lại hoặc “Đang chờ lệnh expose/recover/finish”.

### 4.3 Recovery và các điều kiện nền

Baseline qua đầu lấy mẫu và recovery qua bộ lọc có thể khác nhiệt/ẩm và thành phần khí. Lưu route trong mọi mẫu, cùng T/RH/P và PWM. Chỉ số quay về baseline được trình bày có ngữ cảnh; không tự coi nó chứng minh buồng sạch.

Thêm lượt blank sau warm-up và khi bắt đầu buổi: chạy cùng pipeline/bơm/van nhưng không đưa nguồn mùi vào. Dùng blank để quan sát tác động do đường lọc, bơm, nhiệt/ẩm và thao tác. Mọi loại mẫu phải dùng cùng cách vận hành; không để một nhãn chỉ xuất hiện ở một mức PWM hoặc một cấu hình heater.

### 4.4 Kéo dài, kết thúc và hủy

Giữ `extend <s>` ở WAIT_FINISH: mỗi lần tạo đoạn recovery có ID/thời gian riêng; không cộng AUC xuyên khoảng chờ. `finish` sau đủ pha tạo COMPLETE rồi cho đặt tên; kết thúc sớm/hủy lượt giữ ABORTED và dữ liệu đã ghi. Hủy lượt đưa van về khí lọc, bơm vẫn 80% trong phiên nếu không có lỗi. `quit`, Ctrl+C hoặc đóng chương trình dừng bơm, đưa van về khí lọc và hoàn tất file. OFF do lỗi được ưu tiên và không tự chạy lại; các lệnh sai trạng thái không làm thay đổi pha.

COMPLETE là hoàn thành quy trình; chất lượng GOOD/WARN/INSUFFICIENT được lưu độc lập. Thao tác thay PWM/route ngoài lịch khi đang thu phải bị khóa hoặc ghi protocol deviation rõ ràng; tab chẩn đoán cho phép thử đầu ra khi không có lượt đang chạy. OFF ưu tiên luôn khả dụng.

## 5. Hợp đồng đo và cấu hình

### 5.1 BME688

- Giữ Bosch BME68x SensorAPI và giấy phép/provenance; driver vendor không chỉnh để che lỗi.
- Forced mode; lưu requested và applied/readback: heater, thời gian heater lượng tử hóa, OS T/H/P, filter, chip/variant và các status/index cần thiết.
- Chờ theo thời gian đo Bosch và heater đã lập trình, không dùng một delay tùy ý làm chuẩn deadline pha.
- Phân biệt new_data/fresh với gas_valid/heater_stable và ổn định nền. Mẫu không mới là STALE/null; gas không hợp lệ vẫn có thể giữ raw với cờ.
- Áp suất đổi Pa→hPa một lần; khí lưu Ω, chỉ đổi kΩ trên màn hình.

Có hai cấu hình cần nhận diện trước khi triển khai: bản Pi trong bàn giao là 320 °C/150 ms, T8/H2/P4; bản ControlTest S3 trước là 300 °C/100 ms, T2/H2/P4. Đề xuất giữ cấu hình S3 đang dùng làm profile bring-up ban đầu, có profile Pi_reference để khảo sát đối chiếu. Mỗi profile có ID/config hash; chốt một profile thu chính sau phép thử nền và đáp ứng thực tế. Không tự trộn hai profile như cùng điều kiện, không tự giảm heater chỉ để đồ thị phẳng hơn.

### 5.2 ADS1115 và module analog

- Single-shot, gain 2/3, 128 SPS, single-ended; chỉ một owner bus/ADC.
- Mỗi count và voltage lấy từ cùng một conversion. Kiểm MUX/PGA/rate/mode readback trước/sau, timeout hữu hạn; lỗi một kênh vẫn đọc các kênh khác.
- Giữ signed count, điện áp và timing từng kênh. Không clamp số âm thành 0, không điền mẫu cũ, không tạo dòng bù giả khi chậm lịch.
- Giữ cờ NEGATIVE/ADC_LIMIT/config mismatch và các cảnh báo suspect; lưu thuật toán/ngưỡng/version nếu port anomaly guard.
- SUSPECT_JUMP hoặc tương quan giống kênh khác là cảnh báo heuristic. TGS2602 có thể có đáp ứng nhanh thật; không tự sửa/xóa đỉnh hoặc mặc định coi mọi SUSPECT là I2C hỏng. Tách hard invalid khỏi soft suspect; công khai chính sách dùng trong thống kê.
- TGS2602 trước mắt chỉ thu AOUT; chưa suy Rs/ppm khi chưa biết RL, mạch module và hiệu chuẩn. Heater của module cấp liên tục; PWM bơm không điều khiển heater.

## 6. Màn hình giám sát và chất lượng trực tiếp

### 6.1 Các vùng chính

| Vùng | Nội dung |
| --- | --- |
| Trạng thái phiên | Session/trial ID, mã mẫu, pha, đếm ngược, thời gian warm-up, preset và profile |
| Số đo hiện tại | TGS2602 A0, MQ3 #1 A1, MQ135 #2 A2, MQ3 #2 A3: V/count; BME: Ω/kΩ, °C, %RH, hPa |
| Biểu đồ | 4 analog, gas, T, RH, P; cửa sổ 2/10/30 phút, zoom; nền màu pha, marker và gap thực |
| Đầu ra | PWM yêu cầu/báo lại, van ON/OFF, đường khí theo cấu hình; không gọi là lưu lượng/vị trí cơ khí đã đo |
| Sức khỏe ghi dữ liệu | Samples/seq/gap/reset, tuổi mẫu, hàng đợi, lỗi COM, tiến độ write/sync, vị trí file |
| Chất lượng | Từng kênh và toàn lượt; nguyên nhân cảnh báo cụ thể, không chỉ một đèn xanh |
| Thao tác | Terminal là giao diện điều khiển chính: `start`, `expose`, `recover`, `finish`, `name`, `notes`, `next`, `extend`, `mark`, `status`, `quit`; đồ thị hiển thị song song |

UI đọc snapshot; refresh không tạo conversion mới. Có chế độ pause/zoom đồ thị trong khi acquisition/writer vẫn chạy; nút Pause hiển thị phải phân biệt với dừng thu. Bộ đệm đồ thị hữu hạn, log raw tiếp tục đầy đủ. Dữ liệu stale/lỗi hiện “--” và lý do; đường biểu đồ đứt ở gap. Smoothing chỉ là lựa chọn hiển thị, raw giữ nguyên.

Terminal input chạy qua worker/queue riêng để việc chưa gõ Enter không chặn đọc/lưu/vẽ/heartbeat. Màn hình Qt giữ event loop riêng đúng vai trò. Chỉ một Serial worker sở hữu COM, cả CLI và UI dùng chung controller. Terminal in mốc chuyển pha, prompt và lệnh tiếp theo, hạn chế spam số đo làm khó nhập. Nếu bổ sung nút GUI, nút phải gọi cùng đường xử lý/kiểm trạng thái như lệnh terminal, không tạo một state machine khác.

### 6.2 Độ ổn định trước khi thu

Cửa sổ ban đầu 30 s, thêm trend dài hơn khi xem warm-up. Kiểm số mẫu hợp lệ, độ phủ theo thời gian, gap lớn nhất, invalid fraction, slope, range và độ nhiễu. Với khoảng 1 Hz, yêu cầu số mẫu theo kỳ vọng của cửa sổ (ví dụ ít nhất khoảng 80% số mẫu mong đợi), thay vì dùng riêng min_samples=5 để gọi cửa sổ 30 s là đủ. Ngưỡng và quy tắc được ghi trong config/version.

Ngưỡng BME trong bàn giao được giữ làm điểm tham chiếu khảo sát: gas slope 5%/phút, range 5%; T slope 0,3 °C/phút, range 0,2 °C; RH slope 1 điểm %RH/phút, range 1 điểm %RH; gap 3 s, invalid fraction 0,2, coverage 0,8; T>35 °C là advisory. Kiểm lại cách tính thật trong quality.py trước khi port; các số này không phải tiêu chuẩn chất lượng cảm biến.

Bổ sung slope/range/noise cho cả bốn analog, đặc biệt TGS2602 mới. Ngưỡng analog cần khảo sát trên phần cứng; chưa có ngưỡng thì hiển thị số đo và “chưa cấu hình tiêu chí”, không giả định stable. Dùng cả đơn vị mV và chỉ số tương đối; nền gần 0 làm chỉ số % không xác định thì trả null + reason.

Lệnh `start` được phép dùng khi có cảnh báo nền chưa ổn định theo chủ ý người dùng; lưu `baseline_started_without_stability` và nguyên nhân. Không bắt chờ hệ thống tự kết luận stable mới cho gõ lệnh. Lỗi cấu hình, thiếu đường ghi hoặc giao tiếp không khỏe là nhóm chặn chạy khác với cảnh báo drift. Không dùng heater_stable thay cho kết luận ổn định nền.

### 6.3 Chất lượng từng lượt

Hiển thị trực tiếp: số mẫu hợp lệ/mong đợi mỗi pha, thời lượng thực, lỗi/gap, drift baseline từng sensor, mốc lệnh/ACK, đáp ứng đã xuất hiện trong WAIT nếu có, thay PWM ngoài lịch và cấu hình/route. Marker bổ sung là tùy chọn; không tự chấm mẫu kém chỉ vì không dùng `mark`. Trạng thái lượt: đủ thông tin/đang thu/cần xem lại/không đủ dữ liệu, kèm lý do.

Khi baseline đã kết thúc hợp lệ có thể xem đường dẫn xuất theo baseline. Giữ giá trị có dấu và định nghĩa rõ nền tham chiếu; thiếu/gần zero thì không tạo tỷ lệ giả. Khi Finish, tính summary baseline n/mean/median/std mẫu/min/max/slope, delta có dấu, % theo abs(baseline), AUC theo thời gian thực và phục hồi. Không nối AUC qua gap, WAIT/review hoặc các đoạn extension rời nhau.

## 7. Dữ liệu và khả năng truy vết

Đề xuất schema mới `robonose.dataset.v1`; đây là phiên bản hợp đồng dataset, khác schema Pi 2.0 và ControlTest 2.x. Analyzer có adapter cho từng schema; không đổi nhãn bản mới thành 2.0 khi ý nghĩa khác. Nếu source cũ không được cung cấp, chưa cam kết tương thích chính xác với analyzer cũ.

Một log session là nguồn raw chính, có session_id/boot_id/seq và context trial/phase chụp tại đầu vòng. Trial có index/metadata/phase intervals và bản export raw tương ứng khi đóng. Cách này giữ dữ liệu lúc đặt tên và giữa lượt, đồng thời tránh coi hai log trùng thời gian là hai thí nghiệm độc lập. Export có nguồn/seq/checksum; analyzer không sửa raw.

| Đường dẫn trong session | Ý nghĩa |
| --- | --- |
| `session/raw.csv` | Dữ liệu chuẩn hóa schema: raw count/V, BME/status, timing, context, route và đầu ra |
| `session/events.jsonl` | Lệnh/ACK, phase transitions, marker, lỗi, start/end, checkpoint |
| `session/metadata.json` | Cấu hình requested/applied, board/firmware/toolchain, mapping, mẫu và chính sách ghi |
| `session/wire.jsonl` hoặc `serial_bytes.bin` | Dữ liệu truyền nhận gốc phục vụ chẩn đoán; định dạng cụ thể chốt khi viết protocol |
| `trials/<run_id>/metadata.json` | Mã mẫu/notes, config, trạng thái, index/pha và liên kết nguồn |
| `trials/<run_id>/raw.csv` | Export theo context gốc; không đổi nhãn theo thời điểm dữ liệu tới laptop |
| `trials/<run_id>/summary.json` | Thống kê và quality/reasons |
| `trials/<run_id>/signals.png`, `normalized.png` | Hình đối chiếu sau lượt |
| `manifest.json` | Checksum các file đã đóng và thông tin export |

Nhóm trường tối thiểu: sensor count/V; BME gas/T/RH/P/raw status/index/fresh/valid; thời điểm bắt đầu/thời lượng đọc từng thiết bị; cycle start/end; schedule lag/skipped; device seq/boot; thời gian nhận của laptop; run/phase/segment/context epoch; pump PWM và valve_energized; `air_path_commanded`; quality/error/reasons; config/profile ID.

Tách thời gian MCU monotonic, thời gian nhận và wall-clock +07:00. Đồng bộ ánh xạ giờ với laptop có event/độ không chắc; không lấy thời gian nhận gói làm thời điểm đo vật lý. Nhảy giờ Windows không đổi deadline pha. Reset MCU tạo boot mới; không nối như một lượt liên tục.

Ghi UTF-8 đúng CSV quoting, JSON null, ô trống cho thiếu; không NaN/Infinity hoặc chuỗi None_V. Mỗi lần ghi có ID/tên mới; không ghi đè dữ liệu cũ. Bản phần mềm/cấu hình/mapping được snapshot để luôn biết A0 là cảm biến nào tại lần thu đó.

## 8. Ghi bền vững và dừng khi lỗi

- Chỉ một tiến trình sở hữu COM và một writer sở hữu log; đóng Arduino Serial Monitor trước khi chạy app.
- Raw đi qua hàng đợi hữu hạn, log đủ mọi trạng thái. Tách hàng đợi/snapshot UI; UI vẽ chậm không được kéo writer chậm theo.
- Flush liên tục và fsync/checkpoint định kỳ, ban đầu tham chiếu 5 s; đo latency thực trên Windows trước chốt. Ghi checkpoint đã sync riêng với seq chỉ mới nhận/append. Không hứa tuyệt đối không mất dữ liệu khi máy mất điện.
- Heartbeat không được gia hạn chỉ vì thread còn sống. Health phải xét dữ liệu mới, tiến độ writer/sync và sức khỏe UI/control. Chạy dài không cần màn hình còn sáng nhưng Windows phải không sleep trong phiên đang thu.
- Mở chương trình thu hardware: đọc/preflight → mở log và ghi được mẫu mới → xác nhận controller ready/OFF → đặt route MONITOR và tự bật bơm PWM 80%. Không thêm thao tác bật bơm hoặc Start Session; ghi sự kiện auto-start và ACK. Trong demo/test không mở tải thật.
- Dùng watchdog 15 s của bản test làm mốc ban đầu cần kiểm lại trong phiên mới; đo thời gian OFF thật khi mất USB. Laptop phát hiện lỗi phải gửi OFF ngay nếu còn liên lạc. Timeout yêu cầu MCU còn nguồn/firmware còn chạy.
- Mất USB, MCU reset, writer/sync lỗi, queue đầy, toàn luồng dữ liệu stale hoặc lỗi cảm biến bắt buộc kéo dài: fault latch, bơm OFF, van về khí lọc, giữ dữ liệu ERROR/PARTIAL. Cảnh báo drift hoặc một lần gas-invalid không tự bị coi như lỗi nguồn/Serial; phân loại mức độ và số lần liên tiếp trong config.
- OFF ưu tiên không phải đợi hàng đợi ghi log còn chỗ. Không tự bật lại sau reset/reconnect/phục hồi ổ đĩa.
- MCU boot giữ đầu ra OFF. Khởi chạy lại chương trình thu hardware tạo phiên mới và thực hiện quy trình tự bật 80% sau preflight; reconnect trong một phiên đã lỗi không tự bật lại. Phát hiện phiên chưa đóng và xuất báo cáo phục hồi, không tự gán COMPLETE. Phục hồi tạo bản sao, lưu checksum/những dòng bị cắt và lý do.
- Lệnh có request ID, ACK/reason/state và chính sách chống lặp. START lặp cùng ID không tạo lượt trùng. Session/trial context có epoch; khi đóng phải xử lý mẫu in-flight theo context gốc.

Đường khí từ trạng thái cuộn van là thông tin điều khiển dựa trên cách đấu đã xác nhận; hệ chưa có cảm biến đo lưu lượng hoặc phản hồi vị trí van. ALL OFF nghĩa là bơm dừng, van về lọc, không có nghĩa đóng kín buồng.

## 9. Những cải tiến so với bàn giao và bản test

| Điểm cần xử lý | Cách triển khai/kiểm chứng |
| --- | --- |
| Bản bàn giao và mạch hiện tại khác điện áp/van/lưu trữ | Một pin map + hardware profile có version; handshake kiểm đúng mapping, gain và route |
| TGS đang ở A2 trong test, yêu cầu mới ở A0 | Test giá trị biết trước ở A0, CSV/card/analyzer đều mang tên TGS; từ chối profile cũ khi thu cấu hình mới |
| Chỉ theo dõi BME chưa đủ để biết cả cụm ổn định | Bổ sung quality theo từng analog và đủ số mẫu/cửa sổ |
| Đếm đủ thời gian dễ bị hiểu là mẫu tốt | Tách pipeline status khỏi quality và thao tác vật lý |
| Cần thời gian chủ động chuẩn bị mẫu giữa pha | Giữ lệnh terminal và WAIT như hệ cũ; phần mềm tự đổi van theo pha, raw vẫn liên tục |
| Đặt tên/đợi giữa lượt dễ làm đứt dòng thu | Session log liên tục, trial UUID và metadata nhập không chặn reader |
| UI/analysis có thể chặn tác vụ quan trọng | Workers riêng, bounded queues, analysis sau lượt ngoài đường thu |
| MUX/readback/anomaly có thể che hoặc nhầm đáp ứng | Kiểm phần cứng đo; giữ raw và lý do; tách soft suspect khỏi hard invalid |
| Heartbeat chưa chứng minh dữ liệu đã lưu | Health dựa trên acquisition + writer + sync, OFF/fault latch |
| So sánh nền đầu mẫu với phục hồi qua lọc dễ hiểu sai | Lưu route/T/RH/P, thêm blank và ghi bối cảnh chỉ số phục hồi |
| Đổi gain/heater/sensor nhưng trộn dataset | Config/profile hash và schema adapter; phân tách điều kiện phần cứng |

## 10. Lộ trình triển khai từng bước với Codex

Mỗi bước phải giao source/tài liệu cần thiết và bằng chứng tương ứng; chỉ đi tiếp khi phần phụ thuộc đã rõ. Các bước dưới đây là kế hoạch sau khi thống nhất, chưa có bước cài đặt/nạp/đọc thiết bị nào được thực hiện trong lượt này.

| Bước | Codex thực hiện trên máy người dùng | Bạn kiểm tra/thao tác | Đầu ra/điều kiện qua bước |
| --- | --- | --- | --- |
| 0. Kiểm kê | Đọc bàn giao, source Pi working tree, source S3 test, bản kế hoạch; kiểm Python/Arduino/COM và dependency hiện có | Cung cấp model bo, vị trí source và cấu hình IDE đã nạp thành công | Source/environment inventory; danh sách thiếu thật; không suy SDK/PSRAM |
| 1. Dựng workspace | Tạo dự án mới riêng, Git nếu dùng, docs/config/tests, hướng dẫn AGENTS cho phạm vi dự án | Mở đúng thư mục trong VS Code | Dự án Pi và dữ liệu cũ giữ nguyên; tên và vị trí mới rõ ràng |
| 2. Môi trường | Tạo `.venv` Python 3.11; cài/khóa GUI/serial/analysis; thiết lập Arduino CLI/core hoặc dùng cấu hình IDE đã xác nhận | Chạy smoke GUI và nhận diện cổng, gửi output nếu lỗi | Dependency lock, environment report và lệnh chạy bằng PowerShell; không dùng BAT/đổi ExecutionPolicy |
| 3. Hợp đồng + mô phỏng | Viết schema/protocol, state machine/fake clock, mapping A0 TGS, CLI không chặn, config validator và logger | Gõ chuỗi lệnh trên demo có nhãn SIMULATED, xem đường van đúng bảng | Test đủ pha/WAIT; chờ không tự sang pha mới; gap/null, session/2 trial, export và fault mock |
| 4. Firmware cảm biến | Tích hợp driver, timing/readback, schema/mapping handshake; build đúng board và USB | Nạp theo hướng dẫn, kiểm bốn kênh và BME trên monitor/app | Build log thật, không chỉ object compile; file đo thử có đủ count/V/status/timing |
| 5. Phiên + bơm/van | Tích hợp tự bật 80% lúc chạy chương trình, lệnh pha, preflight, watchdog/ACK và route theo pha | Thử ngắn tại đường khí thực; xác nhận OFF, route và bơm chạy được ở 80% | Chờ expose/recover không tự tiến; recover mới đổi van OFF; finish/name/next giữ 80%; quit/lỗi OFF |
| 6. GUI + quality | Kết nối màn hình thật, phase shading/countdown/beep, markers, lưu/summary/review | So sensor live và file; pause/zoom/notes không làm mất mẫu | Đủ 8 đại lượng; lỗi có nguyên nhân; số liệu file khớp; worker không bị UI chặn |
| 7. Chạy pilot | Cung cấp quy trình warm-up/blank, 2–3 lượt theo lệnh, kéo dài/hủy, phiên 30–60 phút và báo cáo | Thực hiện trên dữ liệu test ở PWM mặc định 80%, theo dõi đường khí và mốc đưa mẫu | Biết drift từng kênh, gap/jitter/write latency và ảnh hưởng chuyển route; chốt profile heater/quality, báo nếu 80% có vấn đề |
| 8. Thu dataset | Khóa cấu hình đã chọn, SOP, naming/metadata và checklist thu hàng ngày; kiểm export/backup | Thu chính thức theo quy trình đã nghiệm thu | Source + config lock + build/run guide + data validator + report; mọi giới hạn còn lại được ghi rõ |

Đường dẫn Windows đề xuất để dễ hướng dẫn: `D:\HocTap\PBL6\RoboNose_Dataset_S3`. Đây là đường dẫn dự kiến, chưa có xác nhận tồn tại. Lệnh cụ thể sẽ dùng đường dẫn thực và đúng Python trong môi trường đã tạo.

Khi hướng dẫn bằng Codex: mỗi lượt giao một giai đoạn có tiêu chí hoàn thành; yêu cầu đọc code/test liên quan, chạy kiểm tra phù hợp và ghi kết quả thật. Không yêu cầu Codex viết toàn hệ thống trong một prompt rồi nạp ngay. Setup không phụ thuộc file BAT; chạy trực tiếp `python.exe` trong `.venv` và Arduino CLI/IDE đã chọn.

## 11. Kiểm thử và nghiệm thu dự kiến

### 11.1 Trước tải thật

1. Mapping A0 TGS/A1 MQ3_1/A2 MQ135_2/A3 MQ3_2; khác cấu hình phải bị phát hiện, không chỉ đổi nhãn.
2. Fake clock kiểm 60–120–60 và lệnh sai trạng thái: sau 60 s baseline chờ bao lâu cũng không tự exposure; sau 120 s exposure chờ bao lâu cũng không tự recovery/đổi van. `expose`/`recover` mới bắt đầu bộ đếm tương ứng. `finish`/`name`/`next` không bật lại bơm hoặc reset reader; `quit`/lỗi OFF. Tự bật bơm đúng 80% sau startup và giữ trong mọi WAIT, demo không tác động tải.
3. Mẫu bắt đầu trước ranh giới giữ context gốc; có read timing và cờ straddle/control change khi cần. Mẫu chờ trong queue không đổi trial theo lúc nhận.
4. ADS readback, signed count/scale, lỗi từng kênh và timeout; BME units/new-data/valid/stale/readback. Không mở thiết bị thật trong test mặc định.
5. Hai trial cùng tên không đè, raw giữ qua review/notes/between, export tái tạo đúng index/context.
6. Lỗi COM, ACK timeout, reset, frame cắt, seq mất/trùng, queue full, disk full/write/sync fail; OFF ưu tiên và không tự bật lại.
7. UI zoom/pause/resize/notes/export và terminal chưa gõ Enter không làm chặn acquisition/writer/heartbeat. Thời gian WAIT không cộng vào pha chính; raw vẫn đủ. Demo/real không lẫn dữ liệu.
8. Quality/công thức so fixture tính tay và fixture Pi khi có source; thiếu pha/gap/nền gần zero trả null+reason; AUC không bắc cầu sai.
9. Recovery/analysis không sửa raw, kiểm checksum trước/sau; thử file cắt trên bản dữ liệu test.

### 11.2 Trên hệ thật

Chạy ít nhất một phiên 30–60 phút sau warm-up, có blank và nhiều trial. Mục tiêu khảo sát ban đầu: không mất seq do phần mềm, không parse error, không reset ngoài ý muốn; đọc/lưu trung bình đúng 1 Hz. Báo tỷ lệ valid riêng từng sensor, lag/jitter p95/p99/max, hàng đợi, write/sync latency và thời gian OFF thực. Đây là mục tiêu nghiệm thu đề xuất, chưa phải kết quả đã đạt.

Kiểm nguồn/AOUT, mức OFF lúc boot/reset, đúng van và bơm, tác động bật tải đến I2C/T/RH/P. Dùng các lượt test để kiểm mất USB/đóng app, không làm thử mất nguồn trên bản dữ liệu duy nhất. Nếu mẫu đầy đủ nhưng nền drift hoặc thao tác sai, vẫn đánh dấu chất lượng cần xem lại.

## 12. Thông tin cần có trước bước cài thực tế

Đã chốt kiến trúc USB, TGS2602 tại A0, tự bật bơm 80% khi chạy chương trình, thao tác terminal có WAIT giữa các pha, van tự theo pha và thời lượng 60–120–60. Không cần hỏi lại các mục đó.

Cần bổ sung khi bắt đầu setup:

1. Model bo ESP32-S3 và ký hiệu flash/PSRAM nếu có; tên board cùng USB CDC/Flash/PSRAM đang chọn trong Arduino IDE đã chạy thành công. Có thể gửi ảnh bo/Tools nếu không biết tên chính xác.
2. Đường dẫn dự án Pi cũ và source test S3 trên laptop, hoặc gói source/config/tests để Codex đọc. Giữ các thay đổi chưa commit. Không cần gửi `.venv`, file build hoặc toàn bộ dataset. Có 1–2 lượt dữ liệu cũ kèm raw/events/meta sẽ giúp kiểm analyzer/compatibility.

Ở bước pilot chốt profile BME và ngưỡng analog từ phép thử; PWM mặc định đã được người dùng chọn là 80%. Kiểm bơm vận hành được ở mức này; nếu có vấn đề phải báo, không tự thay đổi hoặc thêm mức khởi động khác mà không ghi nhận.

## 13. Nguồn kỹ thuật đối chiếu

- Tài liệu bàn giao người dùng cung cấp: `BAN_GIAO_ROBONOSE_ESP32S3.md`, đủ 19 mục.
- Espressif Arduino-ESP32 installation: https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html
- Espressif I2C: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/i2c.html
- Espressif LEDC: https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html
- Arduino CLI: https://arduino.github.io/arduino-cli/1.5/installation/
- Qt for Python: https://doc.qt.io/qtforpython-6/gettingstarted.html
- pyqtgraph: https://pyqtgraph.readthedocs.io/en/latest/getting_started/index.html
- Bosch BME68x SensorAPI: https://github.com/boschsensortec/BME68x_SensorAPI
- TI ADS1115: https://www.ti.com/lit/ds/symlink/ads1115.pdf
- Figaro TGS2602: https://www.figarosensor.com/product/entry/tgs2602.html

SDK/dependency cụ thể phải được khóa bằng version đã kiểm trên máy/bo đích. Chỉ ghi build/test passed khi có lệnh thực chạy thành công cho bản mới; không lấy kết quả ControlTest hay báo cáo Pi làm nghiệm thu hệ dataset này.

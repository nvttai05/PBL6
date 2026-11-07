# RoboNose Control Test v2.1 — TGS2602 tại A2

Đọc/lưu liên tục MQ135 + 2 MQ3 + TGS2602 + BME688, đồng thời điều khiển PWM bơm và cuộn van 3/2 trên cùng USB. Thay MQ135 #2 tại ADS1115 A2 bằng module TGS2602 có VCC/GND/AOUT/DOUT. Dùng cả firmware và Python 2.1 đi kèm; nạp lại ESP để đổi tên trường A2. Bản 2.0 cũ bị từ chối để tránh ghi MQ135 thành TGS2602.

Hướng dẫn thay cảm biến và chạy nhanh: [docs/THAY_TGS2602_VI.md](docs/THAY_TGS2602_VI.md).

Ảnh giao diện với dữ liệu mô phỏng: [docs/DEMO_preview.png](docs/DEMO_preview.png).

## 1. Chân và phần cứng áp dụng

| Chức năng | Kết nối |
| --- | --- |
| Bơm | GPIO5 → tín hiệu kênh MOSFET D4184 của bơm |
| Van | GPIO4 → tín hiệu kênh MOSFET D4184 của van |
| BME688 | SDA GPIO8, SCL GPIO9; nguồn 3,3 V; ưu tiên 0x77, thử 0x76 |
| ADS1115 | SDA GPIO10, SCL GPIO11 qua BSS138; VDD 5 V; địa chỉ 0x48 |
| A0/A1/A2/A3 | MQ135 #1 / MQ3 #1 / TGS2602 AOUT / MQ3 #2 |
| Tải | Bơm và cuộn van dùng nguồn 12 V qua hai kênh công suất độc lập |
| GND | Nguồn 12 V, 5 V, ESP và cảm biến có tham chiếu chung |

Áp dụng cho bơm DC 12 V hai dây phù hợp PWM nguồn qua MOSFET, và van 3/2 DC 12 V một cuộn điện hồi về khi ngắt điện. Nếu bơm có driver điện tử/ngõ PWM riêng hoặc van hai cuộn, phải kiểm tra cách điều khiển trước khi dùng cấu hình này.

Giữ cách đấu D4184 đã thử đúng. Không nối 12 V vào GPIO. Giữ diode flyback phù hợp cho từng tải nếu module chưa có; dòng hồi của motor/heater đi riêng, không chạy xuyên qua dây GND nhỏ của ADS/BME.

`config.h` mặc định HIGH là bật cho cả hai kênh. Nếu module tác động LOW, chỉnh `PUMP_ACTIVE_HIGH` / `VALVE_ACTIVE_HIGH` theo mạch thực tế và kiểm tra mức OFF trước khi cấp nguồn tải. Phần mềm đưa đầu ra OFF khi bắt đầu chạy; mức chân trước lúc firmware chạy/reset cần mạch kéo về OFF.

## 2. Hiểu đúng tốc độ và chiều van

- **Pump PWM 0–100%** là duty PWM được yêu cầu, không phải RPM hoặc lưu lượng đã đo.
- PWM mặc định **1 kHz, 10 bit**, chỉnh tần số trong `config.h` nếu bơm/mạch công suất yêu cầu. Đây là thông số thử ban đầu, chưa xác nhận tối ưu với bơm thực tế.
- **Khí lọc — A/OFF** ngắt điện cuộn van; buồng thông với bộ lọc khí.
- **Lấy mẫu — B/ON** cấp điện cuộn van; buồng thông với đầu lấy mẫu.
- Đường khí trên đã được người dùng kiểm tra thực tế và xác nhận ngày 06/11/2026. A/B là hai trạng thái của cùng một van một cuộn, không phải hai van riêng.
- **ALL OFF** dừng bơm và ngắt cuộn van, đưa van về đường khí lọc; không có nghĩa đóng kín mọi đường khí.
- Phản hồi firmware xác nhận PWM/GPIO đã được ra lệnh; không phải xác nhận bơm quay hay van đã dịch chuyển cơ khí.

## 3. Nạp firmware mới

1. Giải nén toàn bộ bộ mã mới.
2. Mở `firmware/RoboNose_SensorTest/RoboNose_SensorTest.ino`. File này có `setup()`/`loop()` gọi chương trình chính ở `sensor_test.cpp`; giữ toàn bộ `.c/.cpp/.h` trong cùng thư mục.
3. Cài/chọn **esp32 by Espressif Systems** và đúng bo ESP32-S3. Nếu cần Boards Manager URL: `https://espressif.github.io/arduino-esp32/package_esp32_index.json`.
4. Chọn COM và Flash/PSRAM theo đúng bo. Native USB: **USB CDC On Boot = Enabled**; qua USB–UART CH340/CH343/CP210x: thường **Disabled**.
5. Verify rồi Upload. Ngõ ra bắt đầu OFF, không tự chạy bơm sau nạp.
6. Serial Monitor chẩn đoán dùng **115200 baud, Newline**. Đóng monitor trước khi mở Python.

Driver Bosch đã đi kèm, không cần Adafruit ADS/BME hoặc ArduinoJson. PWM có nhánh API Arduino-ESP32 2.x và 3.x; xem `VALIDATION.md` về phạm vi đã kiểm tra.

## 4. Chạy bằng PowerShell trên Windows

Máy của bạn chặn BAT, nên dùng Python trực tiếp. Không cần file BAT hoặc thay đổi ExecutionPolicy.

Mở thư mục gốc có `requirements.txt` và `pc`. Gõ `powershell` trên thanh địa chỉ File Explorer rồi Enter. Lần đầu:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pc\monitor.py --list-ports
.\.venv\Scripts\python.exe pc\monitor.py --port COM5
```

Thay COM5 bằng cổng thật. Các lần sau chỉ cần lệnh cuối. Bỏ `--port` nếu muốn chọn COM từ danh sách trong terminal.

Thử giao diện và nút điều khiển bằng mô phỏng:

```powershell
.\.venv\Scripts\python.exe pc\monitor.py --demo
```

Màn hình và metadata ghi **DEMO - SIMULATED**. Nút trong chế độ này chỉ thay đổi mô hình mô phỏng, không tác động GPIO thật.

## 5. Sử dụng các nút

Khi kết nối, chương trình gửi ALL OFF và đợi ESP xác nhận trước khi cho bật tải. Các cảm biến vẫn được đọc liên tục mặc định 1 bộ/giây.

| Thành phần | Tác dụng |
| --- | --- |
| Thanh Pump PWM % | Chọn mức mong muốn; kéo thanh chưa tự gửi lệnh |
| Apply Pump | Gửi mức PWM đã chọn; xem ACK và phần Firmware state |
| Pump OFF | Bơm về 0%, giữ nguyên van |
| Khí lọc / A OFF | Ngắt điện cuộn van, buồng nối bộ lọc; giữ nguyên mức bơm |
| Lấy mẫu / B ON | Cấp điện cuộn van, buồng nối đầu lấy mẫu; giữ nguyên mức bơm |
| ALL OFF | Ưu tiên dừng cả hai, hủy các lệnh bật còn chờ gửi |
| Stop & Save / đóng cửa sổ / Ctrl+C | Gửi ALL OFF, đợi xác nhận rồi hoàn tất file |

Thanh trượt là mức đang chọn; phần Firmware state là trạng thái thiết bị báo lại. Xem ACK để biết lệnh đã được chấp nhận. Sau ALL OFF, muốn bật lại phải chủ động Apply/ON; không tự khôi phục giá trị cũ.

Biểu đồ đầu ra lấy trạng thái theo từng mẫu 1 Hz, nên thao tác rất ngắn có thể không xuất hiện. Thời điểm lệnh/ACK vẫn được giữ trong `control_events.csv` và log gốc.

## 6. Trình tự thử thực tế

1. Khởi động PWM 0%, van OFF/khí lọc; kiểm tra ACK ban đầu và dữ liệu 3 MQ + TGS2602 + BME688.
2. Giữ bơm OFF, thử nút Lấy mẫu rồi Khí lọc theo đường khí đã xác nhận.
3. Đặt đường khí thông, chọn PWM 100% rồi Apply Pump để thử khởi động. Không có kick-start/tăng tốc ẩn trong code.
4. Giảm từng mức, ví dụ 80 → 60 → 40%, mỗi mức quan sát vài giây. Nếu mức thấp làm bơm đứng, đưa OFF hoặc về mức vận hành phù hợp; không coi mọi mức thấp là tốc độ làm việc hợp lệ.
5. Khi đã biết đường khí, thử kết hợp đổi van và các mức bơm; xem đáp ứng cảm biến cùng lỗi I²C/reset khi bật tải.
6. Thử ALL OFF, rồi chạy 10–30 phút để xem độ ổn định. Chốt mức dùng thu dataset sau phép thử thật.

Firmware giữ nguyên mức bơm khi chuyển van. Trong lần đầu xác minh cổng, chủ động Pump OFF trước khi đổi.

## 7. Timeout và đóng chương trình

- PC gửi PING khoảng 2 giây/lần. Nếu firmware vẫn chạy mà không nhận heartbeat/lệnh hợp lệ quá **15 giây**, bơm về 0 và ngắt cuộn van.
- Giao diện hoặc chiều nhận dữ liệu treo khoảng 4 giây: PC yêu cầu ALL OFF và ngừng duy trì heartbeat.
- Lệnh đổi đầu ra thiếu ACK khoảng 3 giây: báo lỗi và yêu cầu ALL OFF; không tự gửi lại lệnh bật.
- Reset/reconnect không khôi phục mức cũ. Sau reset/timeout, dùng ALL OFF để đồng bộ rồi chủ động Apply mức mới.
- Khi đóng, chờ lưu xong. `shutdown_all_off_acknowledged=true` nghĩa là firmware đã xác nhận lệnh OFF. Nếu không xác nhận được, chương trình báo rõ; ngắt nguồn 12 V khi cần dừng tải chắc chắn.
- Timeout chỉ thực hiện khi ESP còn nguồn và firmware còn chạy; không có phản hồi RPM/lưu lượng/vị trí van.

## 8. Dữ liệu lưu

Mỗi lần chạy tạo thư mục mới dưới `data/YYYY-MM-DD/sensor_test_<thoi_gian>_<id>/`, không ghi đè.

| File | Nội dung |
| --- | --- |
| `samples.csv` | Số ADC, điện áp, gas/T/RH/P, lỗi, **tgs2602_count**, **tgs2602_voltage_v**, **pump_pwm_pct**, **valve_energized**, **valve_air_path_commanded**, duty/revision/watchdog |
| `control_events.csv` | Thời gian gửi lệnh, request ID, giá trị yêu cầu, ACK/lỗi và trạng thái firmware |
| `metadata.json` | Chân, PWM frequency/resolution, cực tính, heater và phiên bản |
| `summary.json` | Số mẫu, chất lượng, thiếu seq/reset và xác nhận OFF khi đóng |
| `events.jsonl` | Sự kiện thiết bị, timeout, lỗi parser, heartbeat và reset |
| `raw_serial.jsonl` / `serial_bytes.bin` | Dữ liệu nhận gốc |
| `dashboard.png` | Ảnh biểu đồ cuối, nếu xuất ảnh được |

Mẫu hỏng giữ null/ô trống, không thay bằng 0 hoặc lấy số cũ làm số mới. Gas chưa hợp lệ vẫn được giữ gốc cùng cờ, nhưng không vẽ/tính thống kê như gas hợp lệ. MQ/TGS dùng gain 2/3, điện áp AO trực tiếp, không nhân 2. Chưa quy đổi TGS2602 sang ppm hoặc Rs vì chưa xác định RL/mạch module và hiệu chuẩn. CSV gas BME tính ohm; giao diện tính kΩ. Nhiệt độ BME có thể chịu tự nóng.

`valve_air_path_commanded` ghi `FILTERED_AIR` khi cuộn van OFF và `SAMPLE` khi ON, theo cách đấu đã xác nhận. Cột này suy ra từ trạng thái cuộn điện do firmware báo, không phải phản hồi cơ khí hay lưu lượng. `control_events.csv` cũng có cột tương ứng cho ACK; hàng lệnh gửi chưa có trạng thái báo về để trống.

Dữ liệu cũ không được đổi tên hoặc chuyển đổi. Chương trình xem lại bản 2.1 từ chối CSV thiếu trường TGS2602; dùng chương trình 2.0 cũ để xem phiên MQ135 trước đây.

Đọc lại biểu đồ sau khi dừng:

```powershell
.\.venv\Scripts\python.exe pc\plot_saved.py "D:\duong_dan_lan_chay\samples.csv" --window 600
```

Lệnh tạo `review.png` cạnh CSV. Đây là dữ liệu chẩn đoán, chưa có nhãn người/cà phê và pha thu chính thức.

## 9. Khi có lỗi

- **Wrong firmware/schema:** nạp firmware 2.1 cùng bộ, đúng CDC/UART, baud 115200. Schema mới là `robonose.control_test.v2.1`.
- **Access denied:** đóng Serial Monitor/Plotter hoặc tiến trình khác giữ COM.
- **Nút bị mờ:** đợi ACK đồng bộ ALL OFF; kiểm tra trạng thái firmware/PWM initialization.
- **Không thấy dữ liệu native USB:** kiểm tra CDC On Boot và cổng. Python mặc định DTR on; `--dtr off` chỉ dùng thử cho USB–UART nếu cần.
- **Lỗi MQ/TGS/BME khi bật bơm:** kiểm tra sụt nguồn, GND, dòng hồi/chống xung, và đối chiếu lỗi/seq/reset.
- **Van có tiếng nhưng khí không đổi:** ACK chỉ xác nhận điện; kiểm tra cổng thật và yêu cầu chênh áp/lưu lượng của van.
- **Không có đồ thị:** `--headless` vẫn ghi dữ liệu, nhưng không có nút bật tải; vẫn đồng bộ/kết thúc bằng ALL OFF.

## 10. Nguồn và kiểm tra

Xem `VALIDATION.md`. Người dùng đã chạy bản 2.0 và xác nhận đường van; thay TGS2602 và bản 2.1 cần kiểm tra trên phần cứng sau nạp.

- [Espressif LEDC/PWM](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ledc.html).
- [Thay đổi API 2.x → 3.x](https://docs.espressif.com/projects/arduino-esp32/en/latest/migration_guides/2.x_to_3.0.html).
- [USB CDC](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/cdc_dfu_flash.html).
- [TI ADS1115](https://www.ti.com/lit/ds/symlink/ads1115.pdf).
- [Figaro TGS2602 — tài liệu hãng](https://www.figarosensor.com/product/entry/tgs2602.html).
- [Bosch BME68x Sensor API](https://github.com/boschsensortec/BME68x_SensorAPI): driver đi kèm giữ nguyên BSD-3-Clause; nguồn/checksum trong `BOSCH_UPSTREAM.json`.

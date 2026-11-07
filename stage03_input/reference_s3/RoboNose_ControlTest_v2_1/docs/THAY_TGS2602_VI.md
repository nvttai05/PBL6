# Thay MQ135 #2 bằng module TGS2602 — RoboNose 2.1

Cấu hình dùng module TGS2602 có bốn chân VCC, GND, AOUT, DOUT bạn đã mua. Thay tại A2; cảm biến rời không có mạch tải không áp dụng trực tiếp bảng dưới.

## 1. Ý nghĩa van đã xác nhận

| Nút trên giao diện mới | Cuộn điện | Đường khí thông với buồng |
| --- | --- | --- |
| Khí lọc / A OFF | Ngắt điện | Bộ lọc khí |
| Lấy mẫu / B ON | Cấp điện | Đầu lấy mẫu |
| ALL OFF | Ngắt điện, bơm về 0% | Van về đường bộ lọc khí |

Đó là hai trạng thái của một van một cuộn. Bơm vẫn giữ mức PWM khi chỉ bấm đổi van. Chọn Khí lọc và chạy bơm để hút khí qua bộ lọc; chọn Lấy mẫu để hút khí từ đầu lấy mẫu. Nếu bơm đang OFF, chọn van chỉ đổi đường thông, không tự tạo lưu lượng hút.

## 2. Đấu TGS2602

1. Bấm Stop & Save, chờ lưu xong. Ngắt nguồn trước khi thay dây.
2. Tháo MQ135 #2 hiện nối A2, gồm dây nguồn và dây AO của cảm biến cũ. Giữ MQ135 #1 ở A0.
3. Đấu theo chữ in trên module TGS2602; không suy thứ tự chân từ vị trí của module MQ.

| Chân module TGS2602 | Nối đến |
| --- | --- |
| VCC | +5 V nguồn ngoài, cùng nhánh cấp ADS1115 |
| GND | GND chung với ADS1115 và ESP32-S3 |
| AOUT / AO | ADS1115 A2 |
| DOUT / DO | Không nối |

| ADS1115 | Cảm biến sau khi thay |
| --- | --- |
| A0 | MQ135 #1 |
| A1 | MQ3 #1 |
| A2 | TGS2602 |
| A3 | MQ3 #2 |

ADS1115 vẫn cấp 5 V, qua BSS138 trên bus GPIO10/11; BME688 vẫn bus GPIO8/9. Không đưa AOUT 5 V vào GPIO ESP32. Không thêm chia áp khi AOUT nằm từ GND đến VDD của ADS và hai thiết bị dùng đúng cùng nguồn 5 V. Gain ±6,144 V không cho phép vượt VDD. Cấp/ngắt nguồn module và ADS cùng nhau để tránh AOUT còn có điện khi ADS mất nguồn.

TGS2602 dùng heater khoảng 5,0 V theo tài liệu hãng. Cấp nguồn heater liên tục qua module; thanh PWM trên giao diện chỉ điều khiển bơm. Chưa có sơ đồ/RL của module nên chỉ thu điện áp AOUT, không tính ppm hoặc điện trở cảm biến Rs từ một RL giả định.

## 3. Nạp lại firmware

1. Giải nén bản 2.1 vào thư mục mới; giữ thư mục bản 2.0 và các phiên dữ liệu cũ để đối chiếu.
2. Arduino IDE mở `firmware/RoboNose_SensorTest/RoboNose_SensorTest.ino` trong bộ mới.
3. Giữ nguyên đúng board, COM, Flash/PSRAM và USB CDC đã dùng thành công. Giữ toàn bộ các file C/C++ cùng sketch.
4. Verify → Upload. Nếu mở Serial Monitor: 115200 baud, Newline; gửi `INFO` sẽ có `firmware_version: 2.1.0`, schema `robonose.control_test.v2.1`, `A2=tgs2602`.
5. Đóng Serial Monitor/Plotter trước khi mở Python.

Không cần thư viện Arduino mới; driver ADS và Bosch đã đi kèm.

## 4. Mở giao diện trên Windows, không dùng BAT

Trong File Explorer, mở thư mục có `requirements.txt` và `pc` của bộ 2.1. Gõ `powershell` trên thanh địa chỉ rồi Enter. Chạy lần đầu:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pc\monitor.py --list-ports
.\.venv\Scripts\python.exe pc\monitor.py --port COM5
```

Thay COM5 bằng cổng ESP thực tế. Không cần kích hoạt venv, chạy BAT, hoặc sửa ExecutionPolicy. Các lần sau chạy lệnh cuối trong đúng thư mục.

Giao diện có ô **TGS2602 / A2**, nút **Khí lọc / A OFF** và **Lấy mẫu / B ON**. Chương trình yêu cầu ALL OFF khi kết nối và đợi ACK trước khi cho bật tải. Firmware 2.0 cũ sẽ báo Wrong firmware/schema: phải nạp lại ESP và dùng Python cùng bộ.

## 5. Kiểm tra một phiên mới

1. Xem A2 có điện áp và raw count, `ads_a2_error` trống. A2 là số đo trực tiếp, không nhân đôi.
2. Chọn Khí lọc; chạy bơm ở mức bạn đã xác nhận vận hành được để quan sát nền. TGS2602 mới có thể trôi nền khi bắt đầu cấp nguồn; theo dõi đến khi ổn định trước phiên thu dùng so sánh.
3. Chọn Lấy mẫu với mức bơm nhất quán, xem đáp ứng rồi trở lại Khí lọc để theo dõi hồi phục. Chưa coi điện áp là nồng độ ppm.
4. Bấm Stop & Save. Trong `samples.csv` phải có `tgs2602_count`, `tgs2602_voltage_v`, `valve_air_path_commanded`; A2 không còn tên MQ135 #2. Metadata ghi bản đồ cảm biến và đường khí.

Figaro ghi thời gian conditioning 7 ngày cho điều kiện thử chuẩn trong product information. Điều này khác với thời gian cần chờ mỗi lần bật nguồn; có thể đọc thử ngay để quan sát, nhưng không coi vài phút đầu của cảm biến mới là nền đã ổn định. Lưu thời gian cấp nguồn/note phiên khi kiểm tra drift.

File dữ liệu cũ giữ nguyên. Không ghép cột MQ135 #2 cũ với TGS2602 như cùng một cảm biến.

## Tài liệu đối chiếu

- Figaro: https://www.figarosensor.com/product/entry/tgs2602.html
- Figaro product information: https://www.figarosensor.com/product/docs/tgs2602_product%20infomation%28en%29_rev03.pdf
- TI ADS1115, Recommended Operating Conditions: https://www.ti.com/lit/ds/symlink/ads1115.pdf

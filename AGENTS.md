
# Robonose v1.0

## Bối cảnh
- Raspberry Pi 4, buồng thủy tinh, BME688, MQ135, MQ3,
  ADS1115 và bơm 12V điều khiển qua MOSFET.
- Chưa có van 3 chiều và lọc than hoạt tính.
- Mục tiêu hiện tại là khảo sát dữ liệu thu mẫu linh hoạt.
- Pipeline mặc định: BASELINE 30s, EXPOSURE 60s, RECOVERY 60s.
- Lưu đầy đủ dữ liệu cảm biến và thông tin thời gian, pha thu mẫu.

## Quy tắc làm việc
- Trả lời và giải thích bằng tiếng Việt.
- Thực hiện đúng phạm vi được yêu cầu trong mỗi lượt.
- Khi được yêu cầu lên kế hoạch thì chỉ lên kế hoạch.
- Cài thư viện Python trong .venv của dự án.
- Không tự thay đổi hệ điều hành, mạng hoặc dự án khác.
- Không xóa hay ghi đè dữ liệu thu mẫu có sẵn.
- Chỉ chạy phần cứng thật hoặc bật bơm khi được yêu cầu rõ.
- Khi sửa code, báo các file đã sửa và cách kiểm tra.

## Triển khai hiện tại
- CLI: `.venv/bin/python -m robonose`; sim mặc định, `--hardware` là lựa chọn rõ ràng.
- Sim và pump-disabled không được khởi tạo GPIO bơm; doctor chỉ đọc metadata/đường dẫn.
- JZ-MOS TRIG/PWM dùng BCM17 (chân vật lý 11); cực tính còn phải xác nhận: giữ pump disabled đến khi confirmed=true và active_high được khai báo.
- Không suy ra ppm/IAQ; giữ raw, cờ chất lượng và lỗi đọc. Count/voltage phải cùng conversion.
- Chạy `.venv/bin/python -m pytest -q -k "not pump_test"` khi sửa logic thu/lưu/phân tích trong giai đoạn này; chỉ test mô phỏng/mock.
- Đánh giá ổn định gas/T/H là cảnh báo, không chặn start; không diễn giải baseline đang trôi là phản ứng mùi.
- pump-test chỉ mở GPIO với --hardware --enable-pump và cấu hình đã xác nhận; sim không mở GPIO/I2C.
- Schema ở `docs/schema.md`; driver Bosch vendored giữ nguyên mã và giấy phép BSD-3-Clause.


## Giai đoạn thăm dò hiện tại
- Không điều khiển bơm bằng Pi, không chạy pump-test. Hardware thu với --pump-disabled.
- Bơm ngoài bật/tắt thủ công; external-pump và mark chỉ ghi nhận thao tác.
- DISABLED là GPIO control disabled, không khẳng định bơm ngoài OFF.
- Hướng dẫn hiện hành: docs/huong_dan_thu_mau.md.
- Khi test giai đoạn này dùng pytest -q -k 'not pump_test'; không chạy test pump-test.

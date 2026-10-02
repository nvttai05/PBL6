# Thiết kế tối thiểu

`cli.py` đọc cấu hình/lệnh; `config.py` kiểm tra và từ chối cấu hình không biết.
`readers.py` chứa SimReader, BoschBME và ADS1115; driver phần cứng chỉ nạp trong
constructor hardware. `pump.py` chỉ khởi tạo gpiozero/LGPIOFactory khi hardware
và enabled, có OFF best-effort. `state.py` độc lập clock cụ thể, nhận monotonic
time từ caller. `writer.py` quản lý file/UUID/fsync/atomic JSON/rename không đè.
`analysis.py` chỉ đọc raw và viết sản phẩm phân tích.

`session.py`: worker acquisition liên tục dùng reader đã khởi tạo một lần;
main poll stdin bằng selectors/os.read, xử lý timer và lưu queue; worker analysis
riêng vẽ PNG. Queue bounded dùng backpressure, không silent drop. Drain có time
budget để không làm stdin/timer đói khi người dùng chọn sample_hz quá cao.
Mỗi mẫu chụp context run/phase/since/command ở đầu acquisition; main không gán
lại pha theo lúc xử lý queue. Khi kết thúc lượt, đổi context và chờ phép đọc đang
chạy trước khi đóng file. Điều khiển OFF thực hiện trước barrier.
Context chứa deadline: worker chuyển nhãn timed → WAIT tại deadline độc lập với
UI; state machine đóng đoạn ở deadline khi UI poll muộn. Lượt đang finalize được
giữ tham chiếu đến khi đóng thành công, để lỗi reader trong barrier vẫn giữ dữ liệu
và cập nhật ERROR. Input dùng incremental UTF-8 decoder cho lệnh bị chia nhiều chunk.

Collect có log toàn phiên và raw từng lượt. Kết thúc lượt không đóng reader;
đặt tên/ghi chú/giữa lượt vẫn được lưu vào session log. Lượt mới có MONITOR và
run_id riêng. Không reset heater khi chuyển pha/đổi tên. Driver BME dùng forced
conversion mỗi lần đọc; trạng thái hardware không được suy ra từ mô phỏng.

Bosch bridge gồm `native/bridge.c` và SensorAPI upstream nguyên bản dưới
`native/vendor`, giữ giấy phép. `build_driver.py` chỉ compile shared library.
Chỉ `rn_open` mở `/dev/i2c-*`. Native ABI dùng struct kết quả nhỏ, không ánh xạ
struct nội bộ Bosch sang ctypes. `docs/vendor-provenance.json` ghi hash nguồn.

Giới hạn: đây là công cụ khảo sát raw, không calibration/ML. GPIO OFF best-effort
không thay thế trạng thái an toàn điện khi Pi mất nguồn. Linux scheduling và
conversion tạo sai lệch thời gian, đã lưu duration/lag/timestamp để phân tích.

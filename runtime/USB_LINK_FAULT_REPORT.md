# Phiên 22:11:49 dừng do Short serial write

Ghi chú phiên bản: phân tích dưới đây mô tả host trước bản sửa recovery.
Host hiện đã giữ COM để thử OFF/đọc ACK có giới hạn sau write fault và firmware
có đường USB mới; xem [USB_RECOVERY_REPORT.md](USB_RECOVERY_REPORT.md).

Phiên: [Phien_221149_2026-11-06_26258fa9c7ed/session/metadata.json](../data/hardware/2026-11-06/Phien_221149_2026-11-06_26258fa9c7ed/session/metadata.json).

Nguyên nhân kết thúc do host ghi nhận: **`Short serial write` trên COM8**.

Cập nhật từ người dùng sau chẩn đoán: **bơm thực tế đã tắt**. Đây là quan sát
do người dùng xác nhận, không phải OFF ACK hoặc phép đo do agent thực hiện.
Chưa xác định bơm dừng do ALL_OFF hay watchdog, cũng chưa đo độ trễ dừng.
Giữ nguyên `shutdown_off_acknowledged=false` trong dataset gốc vì host không
nhận được ACK trong phiên.

Thao tác ghi ra serial trả về số byte ít hơn yêu cầu. Log host cũ chưa ghi
số byte của lần thất bại nên không biết lần này gửi được 0 hay một phần lệnh.
Chưa xác định được nguyên nhân gốc là USB vật lý/nguồn, driver Windows hay
đường truyền từ firmware. Không kết luận rằng chỉ cần đổi cáp hoặc nạp lại
firmware là khắc phục được.

## Bằng chứng

- Mở lúc `22:11:49.131753+07:00`, đóng lúc `22:25:31.928753+07:00` ngày 06/11.
- Firmware đã có revision `usb_watchdog_time_order.v1`.
- Phiên chỉ có OFF/preflight rồi MONITOR; `trials=[]`, không có START/name.
  Chưa có lượt mẫu được tạo hoặc đổi folder trong phiên.
- Lưu được **818 dòng raw**, seq 158 đến 980; thiếu seq
  **920, 922, 953, 954, 978**. Giữ nguyên các gap, không tạo dữ liệu bù.
- Có 4 dòng JSON lỗi trong khi đang MONITOR, đều có phần đầu mẫu bị cắt rồi
  ghép với khung kế tiếp. Dòng cắt lúc mở COM thuộc phần pre-handshake được
  ghi riêng; không tính nó là bằng chứng lỗi sau khi chạy ổn định.
- Cuối cùng vẫn nhận mẫu seq 980: MONITOR/PWM80, cả năm device status OK.
  Các frame có cùng boot ID `bd9a4bb4090d6df6`; không có frame MCU ERROR
  hoặc thông báo reboot mới trước thời điểm host kết thúc log.
- Sau lỗi, wire ghi được lệnh best-effort `ALL_OFF`. Host không nhận OFF ACK.

[USB_LINK_FAULT_EVIDENCE.json](USB_LINK_FAULT_EVIDENCE.json) lưu các sự kiện,
lệnh cuối, seq gap và hash file gốc. Chỉ đọc, không đổi nội dung dataset.

## Ý nghĩa dòng cuối

`Session ERROR`: phiên gặp lỗi, không đóng sạch.

`last reported PWM 80%`: giá trị cuối MCU đã báo; không xác nhận bơm hiện tại
còn chạy 80%. Sau lỗi truyền thông, trạng thái vật lý chưa biết.

`commanded OFF acknowledged: False`: chưa có xác nhận OFF từ MCU. Với lỗi
ghi transport, nhánh ngoại lệ hiện tại gửi `ALL_OFF` rồi đóng COM; đây là best
effort, không đọc một OFF ACK có tương quan như nhánh shutdown bình thường.
Ngay cả khi bơm đã tắt, host vẫn phải báo chưa xác nhận. Cũng không thể suy
từ lệnh đã gửi rằng MCU đã nhận hoặc bơm đã dừng.

Firmware có lease 15 s và watchdog task; log phiên này chưa đo được việc các
bảo vệ đó đã dừng tải ngoài mạch. Cần quan sát bơm thật; nếu còn chạy thì tắt
nguồn bơm trước khi thao tác kết nối/reset.

## Thay đổi để lần sau thấy nguyên nhân ngay

- Dòng kết thúc terminal thêm `reason`, ví dụ
  `Short serial write on COM8: <đã ghi>/<yêu cầu> bytes`.
- Ghi best-effort cả lần write lỗi vào wire: byte yêu cầu và prefix mà driver
  xác nhận được tách riêng; exception không biết số byte thì dùng null.
- Giữ nguyên chính sách fault/OFF, không tự nối lại hoặc bật bơm sau lỗi.
  Các thay đổi này cải thiện chẩn đoán, chưa chứng minh đường USB thật ổn định.

Test phần mềm: **118 passed, 1 skipped**, 25.86 s;
[log](USB_LINK_TEST_RESULTS.txt), [JUnit](USB_LINK_TEST_RESULTS.xml).
5 test mới kiểm partial write, exception với số byte chưa biết, recorder lỗi
không che lỗi transport/không ngăn emergency write và wire hợp đồng cũ.
Skip C++ native do chưa có compiler native. Chưa mở COM, nạp firmware hoặc
thử lại bơm/USB thật trong đợt chẩn đoán này.

## Bước kiểm tra tiếp theo

Sau khi đã xác nhận bơm dừng, kiểm tra kết nối USB, tránh tiếp xúc lỏng; đóng
Serial Monitor/app khác dùng COM8 và reset/kết nối lại thiết bị trước phiên
mới. Cần đối chiếu thời điểm lỗi với việc rút/cắm cáp, máy ngủ hoặc thao tác
trên cổng serial. Nếu tiếp tục có JSON bị cắt ở cùng đoạn, cần kiểm riêng
đường gửi USB của firmware/driver bằng log mới và cấu hình USB board đã xác
minh. Phiên lỗi cũ được giữ lại để đối chiếu, không tự resume.

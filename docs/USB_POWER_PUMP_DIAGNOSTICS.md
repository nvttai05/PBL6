# Phân biệt lỗi USB với tải bơm/nguồn/nhiệt

Người dùng xác nhận **bơm có nguồn riêng**. Model, điện áp định mức, cách nối
mass và nhiệt độ thực tế của bơm/MOSFET vẫn chưa được cung cấp hoặc đo.

**Cập nhật 07/11:** người dùng báo đã hàn chắc dây nguồn bơm và bơm ngắt khi
chưa nóng. Phiên `Phien_235935_2026-11-06_8df0399528dc` có panic
`Interrupt wdt timeout on CPU1` trong ISR USB và reset lặp trước timeout PING.
Đã đối chiếu đúng ELF và sửa ngắt BUS_RESET kế thừa ở revision v3; xem
[USB_ISR_REPORT.md](../runtime/USB_ISR_REPORT.md). Với sự cố này đã có bằng
chứng lỗi phần mềm USB; chưa có bằng chứng quá nhiệt hoặc lỏng dây gây dừng.
Nguồn gốc sự kiện USB bus reset vẫn chưa được đo. Ưu tiên nạp bản sửa và kiểm
lại trước khi tiếp tục các phép đối chiếu phần điện bên dưới.

Nguồn bơm riêng giảm khả năng dòng bơm kéo trực tiếp sụt nguồn USB của ESP32.
Nếu dùng chung đường mass, nhiễu hoặc tiếp xúc xấu vẫn có thể ảnh hưởng tín
hiệu/mạch điều khiển. Dây lỏng hoặc tải nóng là giả thuyết cần đo; chương trình
không có dòng bơm, lưu lượng, nhiệt bơm hoặc phản hồi đầu ra để tự kết luận.
Nhiệt BME688 không thay nhiệt vỏ bơm/MOSFET.

Espressif yêu cầu thiết kế nguồn/khử nhiễu và reset phù hợp cho ESP32-S3:
[Hardware Design Guidelines](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html).
Nguồn 3.3 V nói trong tài liệu là nguồn chip, không phải điện áp cấp trực tiếp
vào bất kỳ chân đầu vào nào của board phát triển chưa xác định model.

## Bằng chứng đã có

Hai phiên cũ lúc 22:11:49 và 22:35:33 có cùng boot ID trong phần dữ liệu nhận được của từng phiên;
chưa có frame reboot/brownout ngay trước lỗi. Sau khi USB đứt có thể mất luôn
thông tin reset, nên không dùng việc thiếu frame reboot để loại trừ lỗi nguồn.

HELLO đầu phiên 22:11:49 có reset_reason=11 (USB); HELLO đầu phiên 22:35:33
có reset_reason=1 (power-on). Đây là nguyên nhân boot **trước khi thu**, không
phải nguyên nhân dừng cuối phiên. Giá trị được đối chiếu enum trong SDK đang
cài; tham khảo [ESP-IDF Reset Reason](https://docs.espressif.com/projects/esp-idf/en/v5.5.1/esp32s3/api-reference/system/misc_system_api.html#reset-reason).

BME ở cuối hai phiên khoảng 32.3°C và 32.2°C. Đây là vị trí BME, không phải
chứng cứ bơm mát hay nóng. Năm status cảm biến cuối đều OK. Log Windows System
trong cửa sổ ±2 phút không có sự kiện USB/Kernel-PnP liên quan tìm được; đây
không phải phép đo nguồn và không chứng minh đường USB ổn định.

## Quy trình kiểm tra thực tế tiếp theo

1. Tắt nguồn trước khi siết lại đầu nối bơm, MOSFET và nguồn/mass. Xem đầu nối
   có lỏng, đổi màu, nóng cục bộ hoặc dây đứt ngầm không; tránh chạm/rút dây
   tải khi đang chạy để tạo lỗi thử.
2. Ghi model/điện áp định mức bơm, nguồn đang dùng và cách nối mass. Đo điện áp
   ngay tại đầu bơm khi PWM80 và tại nguồn ESP32 theo sơ đồ board. Đo dòng bơm
   đúng cách, so với thông số nhà sản xuất; không đưa chân đo dòng ngang nguồn.
   Đồng hồ có thể bỏ lỡ xung sụt ngắn; oscilloscope phù hợp mới thấy được chúng.
3. Đo nhiệt vỏ bơm, MOSFET và đầu nối bằng cảm biến/thiết bị đo phù hợp; so với
   datasheet của đúng model. Chưa có model thì không tự đặt ngưỡng quá nhiệt.
4. Sau khi nạp revision mới và kiểm `info`, làm hai phiên chẩn đoán cùng cáp,
   cổng USB và điều kiện laptop: một phiên phần công suất bơm đã ngắt nguồn
   từ trước khi bật hệ, một phiên có tải bơm đúng định mức. Giữ thao tác setup
   trong trạng thái đã tắt nguồn. Không đổi logic thu/PWM80 của chương trình.
   Đánh dấu bằng `mark diagnostic_pump_power_off` hoặc
   `mark diagnostic_pump_power_on` trong MONITOR. Không trộn các phiên không
   tải này vào dataset mẫu chuẩn.
5. Lỗi trước từng xuất hiện sau khoảng 13.7 và 26.2 phút; thử so sánh đủ dài
   (ví dụ 30 phút mỗi điều kiện) thay vì kết luận từ một lần chạy vài giây.
   Đây là đề xuất thực nghiệm, không phải bảo đảm thống kê hoặc bài test đã chạy.

Nếu chỉ có tải bơm mới gây đứt USB, ưu tiên kiểm dây/nguồn/mass/MOSFET/nhiễu.
Nếu cả phiên không tải vẫn đứt, tiếp tục kiểm cáp USB, cổng/driver, nguồn board
và đường USB firmware. So sánh này định hướng kiểm tra, chưa tự chứng minh
linh kiện nào hỏng. Không tự tăng timeout hoặc bỏ điều kiện OFF để giữ phiên
thu chạy tiếp qua lỗi.

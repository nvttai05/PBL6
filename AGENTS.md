# RoboNose Dataset S3 — hướng dẫn cho Codex

Đây là dự án PBL6. Người dùng đã duyệt kế hoạch và yêu cầu triển khai từng giai đoạn trên Windows, dùng VS Code + Codex. Đọc tài liệu trong workspace; không giả định có toàn bộ lịch sử chat.

## Thứ tự căn cứ

1. Yêu cầu mới nhất của người dùng trong phiên làm việc.
2. File này và `configs/project_target.json`.
3. `docs/KE_HOACH_ROBONOSE_DATASET_ESP32S3.md` đã cập nhật yêu cầu terminal/PWM 80%.
4. `docs/BAN_GIAO_ROBONOSE_ESP32S3.md` là đặc tả hệ Pi cũ. Source Pi và test S3 là tài liệu đối chiếu; các thông số cũ không tự trở thành cấu hình đích.

Nếu thấy thông tin mâu thuẫn, giữ yêu cầu mới và ghi chênh lệch trong báo cáo. Không tự chuyển sang thu độc lập/microSD hoặc tự chạy các pha liền nhau theo giờ.

## Yêu cầu đích đã chốt

- ESP32-S3 trực tiếp đọc cảm biến, điều khiển bơm/van và thời gian pha. Laptop Windows luôn kết nối USB, ghi dữ liệu và hiện số đo/biểu đồ/quality.
- A0 **TGS2602** thay MQ135 #1; A1 MQ3 #1; A2 MQ135 #2; A3 MQ3 #2. BME688 là cảm biến thứ năm.
- ADS1115: VDD 5 V, 0x48, single-shot single-ended, gain 2/3 FSR ±6.144 V, 128 SPS, count ×0.0001875 V; không có chia áp, không nhân đôi AO.
- ADS dùng bus GPIO10 SDA/GPIO11 SCL qua BSS138; BME bus GPIO8 SDA/GPIO9 SCL, 3.3 V, ưu tiên 0x77.
- GPIO5 PWM bơm, GPIO4 cuộn van; kênh HIGH là bật theo test hiện tại, kiểm lại board trước phần hardware.
- Van OFF/A → khí lọc. Van ON/B → đầu lấy mẫu. Đây là mapping đường ống người dùng đã xác nhận; không có đo lưu lượng/phản hồi vị trí van.
- Chạy chương trình thu hardware → khởi tạo kết nối/log → **tự bật bơm PWM 80%** → WARMUP/MONITOR. Không thêm nút Start Session hoặc opt-in bật bơm riêng mỗi lần. Demo/test không tác động tải.
- Bơm giữ 80% qua warm-up, tất cả các pha, WAIT, đặt tên và giữa lượt. Chỉ dừng khi quit/thoát chương trình hoặc lỗi cần dừng. Boot MCU/reset khi chưa có app vẫn OFF; reconnect trong phiên đã lỗi không tự chạy lại.
- Điều khiển bằng terminal; đồ thị live chạy song song. Input/Enter/notes không được chặn acquisition, writer, UI hoặc heartbeat.

## Chuỗi pha bắt buộc

| Trạng thái | Chuyển tiếp | Đường khí |
| --- | --- | --- |
| MONITOR | `start` → BASELINE | Đầu lấy mẫu |
| BASELINE | Hết 60 s → WAIT_EXPOSURE | Đầu lấy mẫu |
| WAIT_EXPOSURE | Chờ đặt mẫu rồi `expose` → EXPOSURE | Đầu lấy mẫu |
| EXPOSURE | Hết 120 s → WAIT_RECOVERY | Đầu lấy mẫu |
| WAIT_RECOVERY | `recover` → RECOVERY | Đầu lấy mẫu cho tới lúc nhận recover |
| RECOVERY | Đổi sang khí lọc, đếm 60 s → WAIT_FINISH | Khí lọc |
| WAIT_FINISH | `finish`, hoặc `extend <s>` | Khí lọc |
| Sau finish | `name Mau1`, notes tùy chọn, `next` → MONITOR | Khí lọc cho tới next |
| MONITOR sau next | Chờ `start` cho lượt mới | Đầu lấy mẫu |
| Bất kỳ | `quit` → OFF và đóng phiên | Khí lọc |

Mọi WAIT vẫn ghi raw với nhãn riêng, không cộng vào thời gian pha chính. Hết giờ không tự sang exposure/recovery. `finish`/`next` không reinit sensor hoặc phát ON bơm lại. Giữ lệnh mark/status/help/info/durations/abort theo đặc tả phù hợp. Lệnh sai trạng thái phải có lý do và không đổi trạng thái.

Tên có thể nhập sau finish bằng `name Mau1`; không bắt nhập trước start. UUID bất biến, trùng tên không ghi đè. COMPLETE chỉ nói quy trình đủ pha; chất lượng dữ liệu là trường đánh giá riêng.

Theo yêu cầu mới về tìm mẫu bằng folder: layout v2 dùng folder phiên
`Phien_HHMMSS_YYYY-MM-DD_<ID12>` và folder lượt
`Ten_mau_HHMMSS_YYYY-MM-DD_<ID12>`; UUID đầy đủ vẫn bất biến trong raw/metadata.
Chưa đặt tên dùng `Chua_dat_ten`; writer đổi folder khi nhận name, giữ raw và
thu liên tục. Chuyển folder dữ liệu cũ chỉ khi offline, có journal và kiểm hash;
không đổi nội dung file dữ liệu cũ. Không dùng tên folder để thay UUID trong protocol.

## Dữ liệu và kỹ thuật

- Giữ raw count/V/Ω, timing theo từng device, monotonic/boot ID/seq, pha/context, lỗi/null và cờ hợp lệ. Không fill lỗi thành 0 hoặc forward-fill. Không sửa/xóa đỉnh chỉ vì heuristic suspect.
- Dùng schema dataset mới và adapter nếu đọc dữ liệu Pi/ControlTest. Không đổi tên cột MQ135 cũ thành TGS để trộn dataset.
- Phân biệt baseline qua đầu lấy mẫu với recovery qua lọc. Log route, T/RH/P và PWM; có blank để khảo sát hiệu ứng đường khí.
- BME profile S3 test (300°C/100 ms, T2/H2/P4) khác profile Pi (320°C/150 ms, T8/H2/P4). Ghi rõ requested/applied/profile; chọn cấu hình thu chính sau pilot, không âm thầm trộn.
- TGS2602 chỉ thu AOUT; chưa có RL/mạch module/hiệu chuẩn để quy đổi ppm hoặc Rs.
- Một owner COM, một owner ADC/I2C, một writer. UI/analysis không khóa đường thu. Queue hữu hạn, checkpoint/flush/sync và OFF khi lỗi theo kế hoạch.
- Không dùng file BAT hoặc đổi ExecutionPolicy. Gọi trực tiếp `.venv\Scripts\python.exe` trên Windows.
- Giữ source Pi/test S3 làm tài liệu tham chiếu, không sửa dữ liệu thu cũ. Source S3 test trước gán TGS ở A2; đích mới ở A0.
- Không khẳng định build/test/hardware passed nếu chưa có lệnh và kết quả thật. Tách kiểm thử mock khỏi đo thực tế.

## Giai đoạn hiện tại

Giai đoạn `firmware_usb_serial_device`: thực hiện `stage03_input/PROMPT_03_FIRMWARE_USB.md`. Giữ demo và suite bước 02; dùng `python_exe`/Arduino CLI trong `configs/paths.local.json`. Source S3 chỉ đọc tại `stage03_input/reference_s3/RoboNose_ControlTest_v2_1`. Triển khai firmware dataset riêng, SerialDevice, protocol, mock tests và compile; xuất `runtime/STAGE03_REPORT.md`.

Trong bước 03 chưa mở serial thật, chạy chương trình cũ, nạp firmware hoặc bật tải. Có thể build/link generic S3 với profile PROVISIONAL_COMPILE_ONLY khi board thật chưa xác định; không suy board/flash/PSRAM/USB thật từ profile này. Không đổi môi trường/core. Chương trình hardware được viết ở bước này phải tự bật bơm 80% sau startup hợp lệ khi người dùng chạy thu thật sau này.

Nếu thiếu model board/source cũ, tiếp tục các phần chuẩn bị không phụ thuộc chúng, ghi UNKNOWN/NEEDS_INPUT. Không đoán PSRAM/flash/USB từ tên chung ESP32-S3.

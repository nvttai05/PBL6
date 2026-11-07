# RoboNose — bước 03: firmware dataset và USB thật

Báo cáo bước 02 cho biết 47 test phần mềm đạt, demo đúng quy trình và dữ liệu mô phỏng đã được đối chiếu. Mốc tiếp theo là viết firmware dataset và backend SerialDevice, giữ nguyên demo để kiểm hồi quy.

Gói này cung cấp source S3 tham chiếu đã có và prompt triển khai. Chưa có firmware dataset mới hoặc kết quả build/hardware mới trong gói này.

## 1. Đặt gói vào workspace

Giải nén tại:

```text
D:\HocTap\PBL6\Robonose_Esp32S3_CollectData
```

Kết quả có thư mục `stage03_input` bên cạnh `robonose_s3`, `configs`, `runtime`, `docs`. Gói không chứa file đè `.venv`, AGENTS hoặc code bước 02.

## 2. Kiểm demo trên màn hình khi tiện

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo
```

Quan sát dashboard thật, thử start, đợi WAIT_EXPOSURE rồi expose, đợi WAIT_RECOVERY rồi recover; finish/name/next/quit theo hướng dẫn bước 02. Nếu giao diện hoặc input có lỗi thì ghi lại cho Codex sửa trong cùng bước; offscreen PASS không thay cho quan sát này.

## 3. Giao Codex bước 03

Trong cùng workspace VS Code, gửi:

```text
Đọc AGENTS.md, runtime/STAGE02_REPORT.md và thực hiện toàn bộ
stage03_input/PROMPT_03_FIRMWARE_USB.md.
Source S3 tham chiếu đã nằm trong stage03_input/reference_s3.
Tiếp tục phần code, mock và compile không phụ thuộc board chưa biết;
ghi rõ giới hạn, không đoán thông số board để nạp.
```

## 4. Thông tin bo cần bổ sung trước nạp

- Ảnh rõ chữ trên bo/module ESP32-S3, đặc biệt mã flash/PSRAM nếu có.
- Ảnh Tools trong Arduino IDE ở cấu hình đã từng Upload thành công: board, USB mode/CDC, flash/PSRAM và port.
- Cắm lại ESP bằng cáp data để nhận diện cổng; COM3 Intel SOL trong inventory cũ không phải ESP đã xác nhận.

Chưa có thông tin này vẫn viết backend, firmware và compile kiểm thử bằng profile generic có nhãn PROVISIONAL. Không dùng kết quả generic để khẳng định thông số bo thật.

## 5. Kết quả cần gửi lại

`runtime/STAGE03_REPORT.md`, gồm source mới, test và build thực đã chạy, profile build, những điểm còn thiếu và hướng dẫn nạp/chạy tương ứng mức đã xác minh. Median summary, delta, AUC, recovery metrics và ngưỡng analog còn thiếu từ bước 02 phải tiếp tục được theo dõi trước nghiệm thu dataset chính thức.

## Source tham chiếu

`reference_s3/RoboNose_ControlTest_v2_1` là bản ControlTest 2.1 nguyên trạng, gồm firmware, Bosch C + LICENSE/provenance, app test và test cũ. Checksum nguồn nằm trong `REFERENCE_SOURCE.json` và manifest gốc đi kèm.

**Bản tham chiếu dùng TGS2602 tại A2; đích dataset mới dùng A0.** Không nạp nguyên bản tham chiếu như thể nó là firmware dataset; không lấy PASS lịch sử của nó làm kết quả bước 03.

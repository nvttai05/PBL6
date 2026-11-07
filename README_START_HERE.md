# Bước đầu RoboNose Dataset S3

Bộ này là workspace khởi tạo để triển khai với Codex: có kế hoạch đã chốt, bàn giao cũ, đặc tả phần cứng/quy trình và prompt chuẩn bị môi trường. Firmware và ứng dụng thu dataset sẽ được viết ở các bước tiếp theo.

## 1. Giải nén và mở thư mục

Giải nén tới một thư mục mới, ví dụ `D:\HocTap\PBL6\RoboNose_Dataset_S3`. Trong VS Code chọn File → Open Folder, mở đúng thư mục có `AGENTS.md`, `requirements.in`, `configs`, `docs` và `prompts`. Không lồng thêm một lớp thư mục cùng tên khi mở workspace.

## 2. Đưa source tham chiếu cho Codex

Chọn cách tiện nhất:

- Chép source Pi vào `legacy/pi`, source S3 test đang dùng vào `legacy/s3`; giữ đầy đủ cấu trúc source/config/tests/docs và các thay đổi chưa commit.
- Hoặc ghi đường dẫn tuyệt đối tới hai thư mục hiện có trong tin nhắn cho Codex. Codex sẽ lưu vào `configs/paths.local.json` và đọc tại chỗ.

Không phải chép `.venv`, cache/build và toàn bộ dataset. Có thể thêm 1–2 lượt cũ kèm raw/events/meta vào `legacy/samples` khi cần đối chiếu analyzer. Nếu chưa lấy được source Pi, vẫn làm kiểm môi trường; báo rõ phần đối chiếu source còn thiếu.

## 3. Cho Codex làm bước đầu

Mở Codex ngay trong VS Code, làm việc trên workspace cục bộ này. Mở `prompts/01_KIEM_KE_VA_MOI_TRUONG.txt`, chép toàn bộ nội dung gửi cho Codex; hoặc gửi:

```text
Đọc AGENTS.md rồi thực hiện toàn bộ prompts/01_KIEM_KE_VA_MOI_TRUONG.txt.
Source tham chiếu tôi đã đặt trong legacy; nếu thiếu thì báo rõ và tiếp tục phần môi trường độc lập.
```

Nếu source để nơi khác, thêm đường dẫn thật vào tin nhắn. Không cần cài lại Codex nếu bạn đã dùng được extension.

## 4. Kết quả cần nhận

Codex sẽ kiểm Python/công cụ hiện có, đọc source tìm thấy, tạo `.venv`, cài dependency host, kiểm import/Qt và xuất:

- `configs/paths.local.json` — Python/công cụ/source đang dùng, thông tin board đã biết.
- `runtime/environment_report.json` — kết quả môi trường thật.
- `runtime/source_inventory.json` — source tìm thấy và phần còn thiếu.
- `runtime/gui_smoke_report.json` — Qt/pyqtgraph khởi tạo được hay lỗi gì.
- `requirements-lock.txt` — dependency sau khi cài thành công.
- `runtime/SETUP_REPORT.md` — báo cáo ngắn để gửi lại người hướng dẫn.

Nếu máy chưa có Python 3.11 x64, Codex báo đúng thiếu gì và đưa hướng dẫn phù hợp; không đánh dấu cài thành công hoặc chọn Python khác một cách im lặng. Board chưa rõ không ngăn việc dựng môi trường Python.

## 5. Sau bước này

Gửi lại `runtime/SETUP_REPORT.md`. Bổ sung model bo hoặc ảnh bo/cấu hình Tools trong Arduino IDE trước bước build/nạp. Mốc tiếp theo là schema/state machine/logger + demo, sau đó mới tích hợp firmware cảm biến và phần hardware.

Toàn bộ điều khiển thu chính vẫn là: mở app → bơm 80% + warm-up → start → chờ expose → chờ recover → chờ finish → name Mau1 → next → start; quit dừng.

Tham khảo thao tác mở Codex trong IDE: https://learn.chatgpt.com/docs/codex/ide

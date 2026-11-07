# RoboNose Dataset S3 — báo cáo chuẩn bị môi trường

Ngày kiểm tra: **06/11/2026, Asia/Saigon (UTC+07:00)**.
Workspace: `D:\HocTap\PBL6\Robonose_Esp32S3_CollectData`.

**Đã hoàn thành phần chuẩn bị host:** tạo `.venv` Python 3.11 x64, cài dependency, kiểm import, kiểm tính nhất quán dependency và GUI offscreen. **Source Pi/S3 và thông tin board vẫn NEEDS_INPUT.** Các phần thiếu này không chặn việc cài host.

## 1. Phạm vi và tài liệu

Đã đọc `AGENTS.md`, `configs/project_target.json`, prompt bước 01, kế hoạch trong `docs/` và bản bàn giao Pi. SHA-256 của các tài liệu được lưu trong [source_inventory.json](source_inventory.json). Bản kế hoạch ở root và trong `docs/` có cùng SHA-256.

Chỉ liệt kê COM bằng `serial.tools.list_ports.comports()`. Không mở serial, chạy entry point/test Pi hay S3 cũ, nạp firmware hoặc bật bơm/van. Không cài/đổi Arduino core, Python mặc định, ExecutionPolicy; không dùng BAT. Chưa triển khai schema, state machine, logger hoặc dashboard. **Firmware build và kiểm thử hardware: NOT_EXECUTED.**

## 2. Python và dependency

- Launcher `C:\Windows\py.exe` liệt kê Python 3.11 và 3.8.
- Bản được chọn: **Python 3.11.9, 64 bit AMD64**.
- Python gốc: `C:\Users\nvtva\AppData\Local\Programs\Python\Python311\python.exe`.
- Python của dự án: `D:\HocTap\PBL6\Robonose_Esp32S3_CollectData\.venv\Scripts\python.exe`.
- `.venv` chưa tồn tại khi bắt đầu; đã tạo bằng `py -3.11 -m venv .venv`. `include-system-site-packages = false`.
- `python` trên PATH vẫn trỏ tới Python 3.8; dùng trực tiếp interpreter trong `.venv` cho mọi lệnh cài/kiểm sau khi tạo môi trường. Không cần activate.

| Import | Phiên bản thực đã cài | Kết quả |
| --- | --- | --- |
| PySide6 / Qt | 6.12.0 / 6.12.0 | PASS |
| pyqtgraph | 0.14.0 | PASS |
| serial (pyserial) | 3.5 | PASS |
| numpy | 2.4.6 | PASS |
| matplotlib | 3.10.8 | PASS |
| pytest | 9.2.0 | PASS import; chưa có suite mới để chạy |

Đã cài theo `requirements.in`, giữ nguyên các pin pyserial/matplotlib. `pip check` trả `No broken requirements found.` (exit 0). [requirements-lock.txt](../requirements-lock.txt) là kết quả `pip freeze` từ chính `.venv`, gồm 24 package trực tiếp/gián tiếp. Không cài package vào Python global. Cache cấu hình Matplotlib dùng `runtime/mplconfig`.

Lần cài trong sandbox thất bại với `No matching distribution found for PySide6`. Chạy lại sau khi được cấp quyền truy cập ngoài sandbox đã cài thành công (exit 0). Log hai lần được giữ riêng: [lần đầu](logs/pip-install.log), [lần thành công](logs/pip-install-escalated.log). Không cần cài lại trên máy hiện tại. Nếu cần phục hồi một `.venv` Python 3.11 x64 tương ứng, dùng:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
```

## 3. Source tham chiếu và Git

Tại thời điểm kiểm kê, **`legacy` chỉ có `README.md` (628 byte)**. Không thấy `legacy/pi`, `legacy/s3` hoặc `legacy/samples`; không có `configs/paths.local.json` ban đầu để lấy đường dẫn thay thế. Không quét ổ đĩa để tìm dự án khác.

| Mục | Trạng thái | Hệ quả |
| --- | --- | --- |
| Source Pi, config, tests và vendor Bosch | NEEDS_INPUT | Chưa xác minh code, thuật toán, license/provenance từ source |
| Source S3 test/ControlTest | NEEDS_INPUT | Chưa kiểm mapping, PWM, USB, ACK/watchdog hoặc driver thực |
| Raw/events/meta lịch sử | NOT_PROVIDED | Chưa đối chiếu schema/analyzer; có thể bổ sung sau |
| Git của workspace | Không có repository | `git status --short` exit 128; commit/diff không có, không tự tạo |

Các tên source và thông số lịch sử trong bàn giao là mô tả tài liệu, không được ghi thành source hoặc kết quả đã xác minh. `legacy_pi_source`, `legacy_s3_source` để `null`; `legacy_sample_dirs` để `[]` trong cấu hình cục bộ.

## 4. Arduino, board và COM

| Công cụ | Kết quả chỉ đọc |
| --- | --- |
| Arduino IDE | **2.3.10**, xác nhận bằng executable metadata và `resources/app/package.json` |
| Vị trí IDE | `C:\Users\nvtva\AppData\Local\Programs\Arduino IDE` |
| Arduino CLI kèm IDE | **1.5.1**, commit `01f3d4f2b`; lệnh `version` exit 0 |
| CLI executable | `C:\Users\nvtva\AppData\Local\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe` |
| ESP32 Arduino core đã có | **3.3.12**, đọc thư mục và `platform.txt` tại `C:\Users\nvtva\AppData\Local\Arduino15\packages\esp32\hardware\esp32\3.3.12` |
| CLI trên PATH | Không thấy; dùng đường dẫn CLI tuyệt đối đã xác minh |

Phiên bản core đang cài không chứng minh đây là cấu hình đã nạp thành công cho board của dự án. Không cài hoặc chọn core khác; không build/upload trong bước này.

COM được liệt kê: **COM3 — Intel(R) Active Management Technology - SOL (COM3)**, manufacturer Intel, không có USB VID/PID. Không chọn COM3 làm cổng ESP32. Trong kết quả enumeration này chưa nhận diện được cổng USB của board; không kết luận board hỏng hoặc thiếu driver từ kết quả đó.

Model board, FQBN, flash, PSRAM, USB CDC on boot và cổng board: **UNKNOWN/NEEDS_INPUT**, tất cả để `null` trong [paths.local.json](../configs/paths.local.json). Chưa có thông tin đủ để xác nhận cấu hình Tools từng nạp thành công; không suy các giá trị từ tên ESP32-S3.

## 5. GUI smoke

Đã tạo [scripts/gui_smoke.py](../scripts/gui_smoke.py): một cửa sổ Qt, đồ thị pyqtgraph sóng sin có nhãn **SIMULATED DATA**, nhãn nhịp event loop và nút đóng. Script không có đường truy cập serial/GPIO.

Lệnh kiểm tự động đã chạy:

```powershell
.\.venv\Scripts\python.exe scripts/gui_smoke.py --offscreen --auto-close-ms 2000 --report runtime/gui_smoke_report.json --snapshot runtime/gui_smoke_offscreen.png
```

Kết quả cuối: **PASS, Qt platform `offscreen`**, event loop exit 0, **18 nhịp timer**, chạy 2.016 s, nhận `closeEvent` và `aboutToQuit`, cửa sổ được đóng bình thường. Ảnh [gui_smoke_offscreen.png](gui_smoke_offscreen.png) đã được xem: đồ thị và nhãn SIMULATED đọc được. Lần đầu font hiện ô vuông trong offscreen; đã bổ sung nạp font Segoe UI từ `C:\Windows\Fonts\segoeui.ttf` và chạy lại. Báo cáo/log GUI hiện chứa lần kiểm cuối.

**Chưa mở hoặc kiểm cửa sổ Windows native:** hiển thị trên màn hình thật, DPI/multi-monitor và thao tác chuột/bàn phím bằng người dùng chưa được kiểm. Offscreen không chứng minh các phần đó.

Tại PowerShell ở root workspace, mở cửa sổ thật bằng một lệnh:

```powershell
.\.venv\Scripts\python.exe scripts/gui_smoke.py
```

Đồ thị sẽ chạy tới khi bấm **Close smoke window** hoặc nút X. Lần chạy này ghi riêng `runtime/gui_smoke_manual_report.json`, giữ nguyên bằng chứng kiểm offscreen.

## 6. Chênh lệch với tài liệu lịch sử

Áp dụng AGENTS và `configs/project_target.json`; không chuyển thông số Pi thành cấu hình đích:

| Nội dung lịch sử | Đích đã chốt |
| --- | --- |
| Pi A0 MQ135 #1; tài liệu test S3 ghi TGS tại A2 | TGS2602 A0; MQ3 #1 A1; MQ135 #2 A2; MQ3 #2 A3 |
| ADS Pi 3.3 V, gain 1, FSR ±4.096 V, chia áp | ADS 5 V, gain 2/3, FSR ±6.144 V, 128 SPS, count × 0.0001875 V; không chia áp/nhân đôi AO |
| Pi chưa có van/lọc; đề xuất thu độc lập microSD/ESP-IDF | ESP32-S3 đọc/điều khiển, laptop USB luôn kết nối và lưu; hướng bring-up Arduino; van GPIO4, bơm GPIO5 |
| Tham chiếu có preset 30–60–60 và opt-in bơm | 60–120–60 s, lệnh terminal có WAIT; app hardware tự bật 80% sau khởi tạo; giữ qua mọi WAIT/name/next |
| Recovery thao tác đường khí bằng tay | Van ON/B là đầu lấy mẫu; `recover` mới đổi OFF/A về khí lọc; giữ lọc tới `next` |
| BME Pi 320°C/150 ms, T8/H2/P4 | Bring-up S3 300°C/100 ms, T2/H2/P4; profile thu chính còn null, chốt sau pilot |

Các khác biệt S3 test chỉ biết từ tài liệu vì chưa có source thực. Không sửa source/dataset cũ, không đổi nhãn MQ135 thành TGS, không suy ppm/Rs của TGS. Hành vi tự bật bơm 80% thuộc chương trình thu hardware giai đoạn sau; smoke hiện tại chỉ dùng dữ liệu giả.

## 7. Bằng chứng lệnh và đầu ra

| Lệnh/kiểm tra | Kết quả |
| --- | --- |
| `py -0p`; kiểm interpreter/architecture | Thành công, chọn 3.11.9 x64 |
| Probe JSON inline Python ban đầu | Lỗi `NameError` do quoting PowerShell; đã kiểm lại thành công bằng probe đơn giản và script |
| `py -3.11 -m venv .venv` | Exit 0 |
| `pip install -r requirements.in` trong sandbox | Exit 1; đã xử lý bằng lần chạy có quyền ngoài sandbox |
| `pip install -r requirements.in` lần sau | Exit 0, dependency đã cài |
| `pip check`; `pip freeze`; 6 import | Exit 0 / PASS |
| `git status --short` | Exit 128 vì workspace không có Git |
| CLI `version` | Exit 0 |
| `scripts/inspect_setup.py` | Exit 0; chỉ đọc công cụ/liệt kê COM và xuất báo cáo |
| GUI offscreen lần cuối | Exit 0; PASS trong phạm vi nêu trên |

Chi tiết: [setup_commands.json](setup_commands.json), [environment_report.json](environment_report.json), [source_inventory.json](source_inventory.json), [gui_smoke_report.json](gui_smoke_report.json) và thư mục [logs](logs/). Đường dẫn Python/công cụ/source/board nằm trong [configs/paths.local.json](../configs/paths.local.json).

## 8. Thông tin còn cần bổ sung

1. Source Pi và source S3 test thực, gồm config/tests và thay đổi chưa commit: đặt vào `legacy/pi`, `legacy/s3` hoặc cung cấp đường dẫn thật. Hiện cả hai chưa có trong workspace.
2. Model/ký hiệu board và cấu hình Tools từng nạp thành công: board/FQBN, flash, PSRAM, USB CDC/USB mode, core dùng khi nạp. Có thể bổ sung bằng ảnh bo và ảnh Tools ở lượt sau.
3. Tùy chọn: 1–2 lượt raw/events/meta lịch sử để kiểm adapter/analyzer.

**Dừng tại mốc chuẩn bị để người dùng xem báo cáo.** Chưa chuyển sang triển khai schema/state machine/logger, firmware hay kiểm hardware.

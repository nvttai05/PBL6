# RoboNose — báo cáo bước 02

Ngày: **06/11/2026, Asia/Saigon (UTC+07:00)**. Mode: **SIMULATED DATA**.

**Đã triển khai demo chạy được**, gồm schema `robonose.dataset.v1`, state machine, logger, terminal và dashboard Qt/pyqtgraph. Kiểm cuối: **47 test đạt, 0 lỗi, 0 bỏ qua; pytest báo 2.19 s**. Đây là kiểm thử phần mềm/mô phỏng, chưa phải nghiệm thu ADC/BME, firmware hoặc phần cứng.

## 1. Chạy thử

Từ root workspace trong PowerShell:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo
```

Demo mở dashboard tám đại lượng và nhận lệnh ở terminal. Sau khi log sẵn sàng, đầu ra **mô phỏng** tự vào PWM 80%, SAMPLE/MONITOR. Không có bước bật bơm riêng. Preset thật của demo vẫn **60/120/60 s**, không bị rút ngắn để chạy test.

```text
start
[đợi BASELINE 60 s → WAIT_EXPOSURE]
expose
[đợi EXPOSURE 120 s → WAIT_RECOVERY]
recover
[van mô phỏng về lọc; đợi RECOVERY 60 s → WAIT_FINISH]
finish
name Mẫu thử 1
notes Ghi chú tùy chọn
next
[MONITOR, có thể start lượt mới]
quit
```

Chỉ `expose`/`recover` được chấp nhận mới bắt đầu pha tiếp; WAIT vẫn ghi raw. `extend 10` ở WAIT_FINISH tạo đoạn recovery mới. `finish` sớm/`abort` giữ ABORTED và dữ liệu. Tên/notes có thể bỏ qua; UUID bất biến. `quit`, Ctrl+C, đóng cửa sổ hoặc EOF dừng sạch; lỗi latch OFF và không tự chạy lại.

Lệnh đầy đủ và quy tắc từng trạng thái: [COMMANDS_AND_STATES.md](../docs/COMMANDS_AND_STATES.md). Schema, cột/đơn vị, timing, null và ghi file: [SCHEMA_DATASET_V1.md](../docs/SCHEMA_DATASET_V1.md).

## 2. Những thay đổi đã thực hiện

- Package [robonose_s3](../robonose_s3/): `config`, `schema`, `clock`, `state`, `device`, `simulated`, `session`, `recorder`, `quality`, `analysis`, `terminal`, `dashboard`, entry point `__main__`.
- `AGENTS.md` và `configs/project_target.json`: chỉ chuyển mốc sang `schema_state_machine_sim_logger`; giữ nguyên yêu cầu phần cứng, A0 TGS, PWM 80%, USB/laptop và terminal/WAIT.
- Logic thuần không import Qt. Một simulation engine sở hữu phase/deadline; GUI đọc snapshot. Chưa có SerialDevice thực; không có mô phỏng làm fallback cho phần cứng.
- Queue command 64, queue writer 256, buffer UI 1800 mẫu; writer riêng. Cửa sổ/terminal không sở hữu sensor hay file raw. Input chưa Enter và việc pause/zoom/resize không chặn thu/ghi.
- Raw session liên tục; export theo trial UUID giữ nguyên context/seq. Trial export vẫn nhận raw WAIT_NAME sau finish, được đóng ở next/quit. **Summary cuối tạo sau next/quit** trên file export đã đóng; analysis ở worker riêng, writer ghi kết quả.
- Một lần khởi tạo SimDevice và một lần PWM ON/session; finish/name/next không phát ON lại. OFF không phải đợi writer queue còn chỗ.
- Flush sau mẫu/event, fsync/checkpoint mặc định 5 s và lúc đóng. Theo dõi riêng seq đã ghi/đã sync. Metadata dùng temp + replace. Phiên cũ PARTIAL/ERROR giữ nguyên, không tự resume hoặc gán COMPLETE.
- Dashboard có count/V cho bốn analog, gas kΩ và T/RH/P, phase/countdown, UUID/tên, quality, lỗi/gap/stale, trạng thái ghi, PWM/van/route và heartbeat mô phỏng theo tiến độ dữ liệu/writer/sync. Có vạch phase/WAIT/marker, zoom, pause hiển thị và khoảng thời gian hữu hạn. Ảnh [STAGE02_DASHBOARD.png](STAGE02_DASHBOARD.png) đã được xem sau khi render offscreen.

## 3. Môi trường được sử dụng

Đã đọc các báo cáo bước 01 và cấu hình cục bộ, xác minh `python_exe` vẫn là:

```text
D:\HocTap\PBL6\Robonose_Esp32S3_CollectData\.venv\Scripts\python.exe
Python 3.11.9, x64 AMD64
```

Các lệnh Python/pytest/fixture trong bước này dùng interpreter trên, lấy từ `configs/paths.local.json`. Không gọi Python 3.8 trên PATH, không cài lại dependency, đổi Python global/Arduino core hoặc ExecutionPolicy. `requirements.in`, `requirements-lock.txt` và báo cáo môi trường bước 01 được giữ nguyên làm bằng chứng lịch sử.

## 4. Kiểm thử thực đã chạy

Lệnh cuối đã chạy thành công, exit 0:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=runtime/STAGE02_TEST_RESULTS.xml
```

Kết quả: **47 passed in 2.19s**. Log: [STAGE02_TEST_RESULTS.txt](STAGE02_TEST_RESULTS.txt), [JUnit XML](STAGE02_TEST_RESULTS.xml). Tests dùng FakeClock cho deadline, không đợi các pha vài phút thật và không mở serial/GPIO.

| Nhóm kiểm | Bằng chứng |
| --- | --- |
| Startup, hai lượt, UUID/tên trùng | 80%/SAMPLE; hai UUID khác; đủ pha; next không reset sensor/PWM; tên tiếng Việt, dấu phẩy/nháy và notes newline giữ đúng |
| Deadline và WAIT | Nhảy clock xa vẫn WAIT; mốc hiệu lực 60/120/60 đúng; WAIT không cộng pha; recover mới về lọc |
| Command validation/idempotence | Lệnh sai pha/thừa đối số, request ID lặp/đổi nội dung, extend 0/âm/NaN/Inf/quá giới hạn bị từ chối; extension đúng tách segment |
| Raw/context/null | Mẫu đọc qua deadline giữ nhãn đầu vòng; A0 TGS/header/scale đúng; device ERROR/STALE thành null, không thành 0; SUSPECT giữ raw |
| Writer và fault | Disk-full giả lập, queue đầy → ERROR/OFF; không chờ writer bị chặn để OFF; checkpoint phân biệt written/synced; đóng một lần |
| Vòng đời | Quit, policy Ctrl+C, GUI-close khi input đang dở, pipe EOF; không bị stdin worker giữ tiến trình; PARTIAL cũ không bị sửa |
| Qt offscreen tích hợp | Dòng `sta` chưa Enter vẫn thu/ghi; Enter hoàn tất start qua cùng queue; phase tiếp tục, resize/zoom/pause không ngăn writer; notes đang gõ vẫn có raw; tám plot và marker |
| Quality/analysis | Coverage union không đếm trùng; slope/noise fixture tính tay; heater_stable không che drift; analog UNCONFIGURED; summary mean/std/slope/coverage đúng và hash raw không đổi |
| Phạm vi demo | Guard chặn mọi import serial trong đường chạy demo được kiểm; không có driver phần cứng |

Lần suite đầu có **41 passed, 1 failed**: kỳ vọng coverage trong test đã cộng sai mẫu trùng thời điểm. Đã sửa kỳ vọng union từ 4 s thành 3 s; implementation coverage không bị sửa để khớp số sai. Log đầu giữ ở [STAGE02_TEST_RESULTS_INITIAL.txt](STAGE02_TEST_RESULTS_INITIAL.txt); nhóm liên quan chạy lại đạt 15 test. Sau đó bổ sung kiểm checkpoint và kiểm lệnh có đối số thừa, chạy lại bộ cuối như trên.

Entry point thật cũng đã chạy:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo --offscreen --auto-close-s 3
```

Exit 0; session đóng CLOSED và PWM mô phỏng 0%. [STAGE02_DEMO_SMOKE.txt](STAGE02_DEMO_SMOKE.txt) ghi phiên cuối `196c45f3-0f22-45a1-831e-0997bc1845ea`. Đây là chạy Qt/ghi file thực trên host với dữ liệu giả, không phải cửa sổ Windows native hoặc kiểm hardware.

## 5. Session dữ liệu mẫu bàn giao

Tái tạo bằng:

```powershell
.\.venv\Scripts\python.exe scripts/stage02_demo_fixture.py
```

Fixture dùng clock ảo, origin cố định; giữ preset 60/120/60. Mỗi lần tạo UUID mới và giữ các session cũ. Manifest lần bàn giao: [STAGE02_FIXTURE.json](STAGE02_FIXTURE.json), log [STAGE02_FIXTURE_LOG.txt](STAGE02_FIXTURE_LOG.txt), kiểm đối chiếu [STAGE02_VALIDATION.json](STAGE02_VALIDATION.json).

Session: [0eeef183-01c3-4aec-ba92-8982c2591717](../data/simulation/2026-11-06/Phien_090000_2026-11-06_0eeef18301c3/).

| Hạng mục | Kết quả đối chiếu file thật |
| --- | --- |
| Session raw | 547 dòng, seq 1–547 liên tục; checkpoint synced_seq 547; session CLOSED |
| Các pha chính | BASELINE 120 dòng, EXPOSURE 240, RECOVERY 130 (gồm extension 10 s) |
| Ngoài pha chính | MONITOR 13; WAIT_EXPOSURE 10; WAIT_RECOVERY 10; WAIT_FINISH 14; WAIT_NAME 10 |
| Trial 1 | `d4e3d2c4-6aee-44c9-8140-e86f624c811d`: 260 dòng, COMPLETE |
| Trial 2 | `d7afa89b-a66d-4b68-86df-942b4e12bb62`: 274 dòng, COMPLETE, có extension |
| Tên hai lượt | Cùng `Mẫu mô phỏng trùng tên`; UUID/thư mục không trùng |
| Summary | Cả hai baseline 60 mẫu; coverage các pha chính/extension 100%; quality UNCONFIGURED, tách khỏi COMPLETE |
| Export | Bằng đúng subset session theo trial_id; hash export khớp summary; count × LSB khớp V ở toàn bộ 4 kênh |
| Vòng đời | SimDevice init 1 lần; PWM ON 1 lần; cuối phiên 0%, FILTERED_AIR |

Các lần smoke/fixture trong lúc phát triển cũng tạo session riêng và được giữ nguyên. Tất cả dữ liệu ở `data/simulation` có mode SIMULATED; không ghi đè dữ liệu thu cũ.

## 6. Giới hạn và phần còn thiếu

- **Source Pi/S3: NEEDS_INPUT.** `legacy` vẫn chỉ có README, hash giữ nguyên. Chưa đối chiếu/port driver, vendor Bosch, analyzer Pi/ControlTest; chưa có adapter legacy hoặc sample lịch sử. Không bịa source/commit/build.
- **Board: UNKNOWN/NEEDS_INPUT.** Model/FQBN/flash/PSRAM/USB/cổng ESP vẫn null trong cấu hình cục bộ. Không chọn COM3 Intel SOL. Cần source S3 và cấu hình board từng nạp thành công trước tích hợp firmware.
- **Native GUI: NOT_EXECUTED.** Đã kiểm offscreen và ảnh render; chưa có quan sát cửa sổ Windows thật, DPI, multi-monitor, chuột/bàn phím/console tiếng Việt thực. Ctrl+C được kiểm policy dừng trong session; chưa kiểm phím Ctrl+C trên console Windows thật.
- **Hardware/firmware/build: NOT_EXECUTED.** Không mở serial, chạy source cũ, upload, bật bơm/van hoặc đo sensor. Timing đọc/receive và heartbeat trong demo là mô phỏng; không suy thời gian OFF, latency ADC/BME hoặc lưu lượng thực.
- Quality live có cửa sổ 30 s, công thức/ngưỡng BME được version/snapshot trong config; analog/pressure còn UNCONFIGURED. Chưa có ngưỡng khảo sát, pilot/blank thật hoặc classifier chất lượng toàn lượt; COMPLETE không có nghĩa dữ liệu tốt.
- Summary tối thiểu streaming đã có n/valid/error/coverage/gap và baseline mean/std/min/max/slope. **Median summary, delta, AUC và recovery metrics chưa triển khai**, ghi lý do deferred thay vì số giả; median/noise của live window có triển khai và test riêng. Summary không tính xuyên WAIT hoặc gộp extension vì chưa thực hiện AUC.
- Chưa benchmark fsync/queue, soak 30–60 phút hoặc thử mất điện. Fsync định kỳ có giới hạn mất dữ liệu giữa checkpoint. Không cam kết báo cáo lỗi còn ghi được khi ổ đĩa không ghi được; session có thể còn PARTIAL.

**Hoàn thành mốc bước 02; dừng để người dùng chạy demo và xem báo cáo trước khi tích hợp phần cứng.**

## 7. Kiểm tra lại theo yêu cầu tiếp tục hoàn thành bước 02

Bước 02 đã hoàn thành trong phạm vi prompt: demo, schema/state machine, logger, terminal/dashboard và session mẫu nhiều lượt đều có. Sau khi tích hợp thêm USB ở bước 03, **47/47 test gốc của bước 02 vẫn đạt** trong suite mới nhất (86 passed, 1 skipped toàn bộ dự án). Test bị skip là C++ native của bước 03, không thuộc 47 test bước 02. Bằng chứng: [STAGE02_RECHECK.json](STAGE02_RECHECK.json), [JUnit mới nhất](STAGE03_TEST_RESULTS.xml).

Đã chạy lại entry point hiện tại bằng interpreter cấu hình với `--demo --offscreen --auto-close-s 2`: exit 0, session CLOSED, PWM mô phỏng cuối 0%; [log demo](stage03/DEMO_SMOKE.txt). File raw session mẫu gốc bước 02 vẫn nguyên hash. Lệnh dùng thử giữ nguyên:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo
```

Ở bản hiện tại app là 0.3.0, demo vẫn SIMULATED với preset 60/120/60, terminal/WAIT và không mở serial. Source S3 tham chiếu đã được cung cấp trong `stage03_input/reference_s3/RoboNose_ControlTest_v2_1`; nhận xét “S3 chưa có” ở mục 6 là tình trạng lịch sử khi hoàn tất bước 02 ban đầu. Source Pi/board thật vẫn thiếu. Native GUI, median summary/delta/AUC/recovery metrics và ngưỡng analog vẫn là giới hạn đã công khai; chúng không phải kết quả phần cứng đã đạt.

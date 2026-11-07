# RoboNose — bước 02: schema, quy trình thu, lưu dữ liệu và dashboard mô phỏng

Đầu vào: `runtime/SETUP_REPORT.md` ngày 06/11/2026. Đây là hướng dẫn cho Codex triển khai trên máy Windows của người dùng; chưa phải kết quả đã chạy của bước 02.

## 1. Môi trường đã chuẩn bị

Theo báo cáo được cung cấp:

- Workspace thực: `D:\HocTap\PBL6\Robonose_Esp32S3_CollectData`.
- Python dự án: `D:\HocTap\PBL6\Robonose_Esp32S3_CollectData\.venv\Scripts\python.exe`, Python 3.11.9 x64.
- Python trên PATH là 3.8. Mọi lệnh Python/pip/pytest phải dùng interpreter `.venv` đã xác minh; không gọi `python` trần.
- PySide6/Qt 6.12.0, pyqtgraph 0.14.0, pyserial 3.5, NumPy 2.4.6, Matplotlib 3.10.8, pytest 9.2.0 đã import được; pip check thành công.
- GUI offscreen PASS; cửa sổ Windows thật, DPI và thao tác người dùng chưa được kiểm.
- Source Pi/S3 chưa được đặt trong workspace; model board/flash/PSRAM/USB/COM ESP chưa rõ. COM3 là Intel SOL, không được mặc định chọn làm ESP.
- Arduino IDE 2.3.10, CLI 1.5.1, core 3.3.12 là thông tin inventory, chưa phải bằng chứng cấu hình build/upload đúng bo.

Không cài lại toàn bộ môi trường, đổi Python global hoặc đổi Arduino core. Đọc báo cáo/cấu hình hiện tại trước khi chạy; nếu khác với các dòng trên thì ghi sự khác biệt thực.

## 2. Kiểm cửa sổ thật khi tiện

Người dùng có thể chạy trong PowerShell:

```powershell
Set-Location 'D:\HocTap\PBL6\Robonose_Esp32S3_CollectData'
.\.venv\Scripts\python.exe scripts/gui_smoke.py
```

Nếu đồ thị hiện và cập nhật, bấm Close hoặc X để đóng bình thường. Việc này kiểm cửa sổ demo, không mở COM hay bật tải. Nếu chưa có quan sát thực, tiếp tục ghi trạng thái native GUI là chưa kiểm; offscreen không thay thế kết luận này.

## 3. Prompt triển khai gửi Codex

Thực hiện bước 02 của RoboNose trong workspace hiện tại. Người dùng đã duyệt kế hoạch và đã gửi báo cáo hoàn thành chuẩn bị host. Hãy viết phần mềm chạy được, kiểm bằng test/mô phỏng và giao lệnh dùng thử. Không chỉ viết thêm kế hoạch.

### A. Đọc đúng đầu vào và cập nhật mốc công việc

1. Đọc `AGENTS.md`, `configs/project_target.json`, `configs/paths.local.json`, kế hoạch đã chốt trong `docs/`, `runtime/SETUP_REPORT.md`, `runtime/environment_report.json`, `runtime/source_inventory.json`, `runtime/gui_smoke_report.json` và `requirements-lock.txt` nếu có.
2. Dùng `python_exe` trong cấu hình sau khi xác minh đúng `.venv` Python 3.11 x64. Giữ source và dữ liệu hiện có.
3. Chuyển ghi chú giai đoạn hiện tại trong AGENTS/target spec từ kiểm kê sang `schema_state_machine_sim_logger`. Chỉ cập nhật mốc/phạm vi cần thiết; giữ nguyên yêu cầu phần cứng và hành vi đã chốt.
4. Source Pi/S3 và model board còn thiếu không chặn bước này. Ghi NEEDS_INPUT cho việc đối chiếu/port/firmware, tiếp tục xây module từ đặc tả. Không bịa rằng đã đọc source legacy hoặc đã kiểm driver/board.
5. Giữ backend mô phỏng rõ ràng. Không mở Serial, chạy source thu cũ, nạp firmware hay bật tải trong bước 02. COM3 không phải cổng ESP đã được xác nhận.

### B. Giao diện chạy và phân chia module

Tạo package chạy được từ root, đề xuất `robonose_s3`, với entry point:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo
```

CLI và cửa sổ PySide6/pyqtgraph chạy song song. Terminal nhận lệnh; cửa sổ hiển thị số đo, đồ thị, pha và chất lượng. Giữ tên entry point này hoặc ghi rõ lý do/đường dẫn thực nếu phải dùng tên khác. Không thêm BAT hoặc yêu cầu activate môi trường.

Tách phần schema/config, trial state machine, device interface, simulated device, session/controller, recorder, quality, terminal và dashboard. Module Qt không được nhập ngược vào logic thuần/state machine. Chưa cần triển khai driver hardware; có thể định nghĩa interface SerialDevice tương lai nhưng không được dùng dữ liệu giả làm fallback cho hardware.

Ở DEMO chỉ SimDevice/engine là owner phase/deadline. Khi tích hợp hardware sau, MCU là owner phase/deadline và app chỉ gửi lệnh/nhận telemetry; không để hai bộ đếm cùng tự chuyển pha. Thiết kế interface và fixture để kiểm tính tương đương khi port sang firmware.

Input terminal phải qua worker/queue riêng; đang chờ Enter không ngăn đọc/ghi/vẽ/heartbeat giả lập. Qt GUI ở event loop phù hợp; cập nhật qua snapshot/signal. Chỉ một owner writer; không chạy tính thống kê/ghi file dài trong handler GUI. Nút GUI nếu có dùng chung đường xử lý với CLI.

### C. Hành vi thu phải đúng yêu cầu mới nhất

Mô phỏng đúng đầu ra đã ra lệnh, nhưng luôn ghi rõ SIMULATED; không coi đó là ACK/phản hồi phần cứng thật.

| Trạng thái | Lệnh hoặc deadline | Van/đường khí mô phỏng | PWM mô phỏng |
| --- | --- | --- | --- |
| Bắt đầu demo | Tạo log xong → WARMUP/MONITOR | ON/B, SAMPLE | 80% |
| MONITOR | `start` → BASELINE | SAMPLE | 80% |
| BASELINE | Hết 60 s → WAIT_EXPOSURE | SAMPLE | 80% |
| WAIT_EXPOSURE | Chờ `expose` → EXPOSURE | SAMPLE | 80% |
| EXPOSURE | Hết 120 s → WAIT_RECOVERY | SAMPLE | 80% |
| WAIT_RECOVERY | Chờ `recover` → RECOVERY | Vẫn SAMPLE cho tới lệnh recover | 80% |
| RECOVERY | Khi nhận recover: van về lọc, đếm 60 s → WAIT_FINISH | OFF/A, FILTERED_AIR | 80% |
| WAIT_FINISH | `finish` → hoàn tất lượt/đợi tên | FILTERED_AIR | 80% |
| Sau finish | `name Mau1`, notes tùy chọn; `next` → MONITOR | FILTERED_AIR tới next | 80% |
| MONITOR sau next | Chờ `start` cho lượt mới | SAMPLE | 80% |
| Bất kỳ | `quit`, Ctrl+C, đóng app hoặc lỗi phiên | FILTERED_AIR | 0% |

- Hết thời gian chỉ sang WAIT, không tự chạy pha tiếp. Chờ bao lâu cũng không tự bắt đầu exposure hoặc recovery. WAIT có nhãn riêng và vẫn lưu dữ liệu, không cộng vào thời lượng 60/120/60.
- `finish`, `name`, `next` không reset cảm biến/heater hoặc phát ON bơm lại. `next` chuẩn bị lượt mới, không tự baseline.
- Người dùng đặt mẫu ổn định về vị trí trong WAIT_EXPOSURE rồi gõ expose. Thời điểm lệnh không đồng nhất với thời điểm khí đến sensor. Raw trong WAIT được giữ, không đổi nhãn hồi tố.
- Lệnh sai trạng thái trả lý do, không tác động state/timer/van. Gửi lệnh lặp không tạo lượt hoặc mốc trùng không kiểm soát.
- Giữ `start`, `expose`, `recover`, `finish`, `name <tên>`, `notes <nội dung>`, `next`, `quit`, `status`, `help`, `mark <nội dung>`, `extend <s>` và `abort` phù hợp đặc tả.
- `extend <s>` ở WAIT_FINISH tạo đoạn recovery riêng, thời lượng hữu hạn/dương trong giới hạn cấu hình; hết lại về WAIT_FINISH. Không nối AUC xuyên khoảng chờ.
- Finish hợp lệ sau đủ pha: COMPLETE. Finish sớm/hủy lượt theo quy tắc đã mô tả: giữ ABORTED và dữ liệu đã có; đường khí về lọc, bơm phiên vẫn 80%. Quit/lỗi phiên mới dừng toàn phiên. Ghi rõ command-state table và kiểm bằng test.
- Đặt tên sau finish: `name Mau1`; hỗ trợ tiếng Việt và khoảng trắng. UUID không đổi, tên trùng không ghi đè, không bắt nhập tên trước start hoặc notes trước next. Lượt chưa đặt tên vẫn tìm được bằng UUID.

### D. Schema và logger

1. Dùng schema mới `robonose.dataset.v1` và mapping A0 `tgs2602`, A1 `mq3_1`, A2 `mq135_2`, A3 `mq3_2`. Không còn gán A0 là MQ135_1 hay A2 là TGS trong dữ liệu mới. Mọi count/V cùng một mẫu phải nhất quán với hệ số 0.0001875 V/count của ADS đích. DEMO chỉ sinh số mô phỏng, không phải kiểm ADC.
2. Lưu 4 kênh count/V, BME gas Ω/T/RH/P, new_data/gas_valid/heater_stable/status/error, timestamp và monotonic, boot/seq, thời điểm đọc/context trial/phase/segment, PWM/valve/air_path_commanded và cờ chất lượng. Metadata ghi đầy đủ SIMULATED, schema/app/config/profile, channel map và quy tắc route.
3. Một session raw liên tục qua warm-up, tất cả WAIT, đặt tên và giữa lượt. Trial UUID/index/metadata liên kết nguồn; export trial sau finish phải giữ context gốc. Không coi session và bản export trùng thời gian là hai thí nghiệm độc lập.
4. Tách thời điểm đo, nhận và áp dụng lệnh. Deadline dùng monotonic; nếu event loop xử lý muộn vẫn ghi mốc hiệu lực deadline đúng. Không gán pha mới cho mẫu đã bắt đầu ở pha cũ vì lúc writer ghi nó đã sang WAIT/next.
5. CSV UTF-8 quoting đúng, ô thiếu để trống; JSON null thay NaN/Infinity. Dữ liệu lỗi không thành 0, không forward-fill hoặc tạo mẫu bù giả. Raw không bị sửa bởi smoothing/analysis.
6. Có raw.csv, events.jsonl, metadata.json, index/metadata từng lượt và summary tối thiểu. Đặt dữ liệu demo dưới `data/simulation/...` và ghi rõ chế độ trong mọi metadata/report/ảnh. Dữ liệu cũ không bị ghi đè.
7. Flush/checkpoint/sync hữu hạn theo cấu hình. Lỗi writer/queue đầy là fault có báo cáo; dừng đầu ra mô phỏng và giữ ERROR/PARTIAL. Khi quit/close, không bị kẹt vì terminal input đang block; lưu/đóng file đúng một lần. Phiên chưa kết thúc không tự thành COMPLETE sau mở lại.
8. Ghi name/notes vào metadata của đúng lượt vừa kết thúc; không đổi ID hoặc sửa raw để đổi tên. Summary/ảnh là sản phẩm dẫn xuất.

### E. Dashboard và quality đầu tiên

- Hiện 8 đại lượng: TGS2602/A0, MQ3 #1/A1, MQ135 #2/A2, MQ3 #2/A3, BME gas, T, RH, P; analog có count và V. Gas CSV là Ω, màn hình có thể kΩ.
- Có phase/countdown hoặc “chờ expose/recover/finish”, tên/UUID lượt, số mẫu, gap/error/stale, trạng thái ghi, PWM 80% và đường van mô phỏng.
- Đồ thị theo thời gian, đánh dấu phase/WAIT và marker; cửa sổ dữ liệu hữu hạn. Zoom/pause hiển thị vẫn giữ đọc và ghi. Mẫu thiếu làm đứt đường; cửa sổ DEMO ghi SIMULATED DATA nổi bật.
- Quality ban đầu cho từng kênh: số mẫu/coverage/gap/invalid fraction, slope/range/noise trên cửa sổ 30 s; đủ số mẫu/tầm thời gian mới tính kết luận. Chưa đủ dữ liệu là INSUFFICIENT/WARMING_UP. Ngưỡng analog chưa khảo sát là UNCONFIGURED, không tự tô stable.
- Ngưỡng BME và công thức phải theo kế hoạch/config có version. heater_stable không thay kết luận nền ổn định. Cho start theo chủ ý khi có drift warning và lưu lý do, không thêm xác nhận bật bơm mỗi lượt.
- COMPLETE của quy trình tách khỏi quality. Mark thêm là tùy chọn; không chấm hỏng mẫu chỉ vì không dùng mark. Ghi được quan hệ đường mẫu/nền và lọc trong dữ liệu; không suy ppm/Rs.
- Summary tối thiểu theo pha có số mẫu/valid/coverage, lỗi, baseline statistics và lý do null nếu thiếu. Nếu làm delta/AUC ngay, dùng thời gian thật, giữ dấu, mẫu baseline gần zero trả null+reason; không bắc cầu qua WAIT/gap/đoạn recovery tách rời. Chỉ ghi phép phân tích đã kiểm bằng fixture; phần đối chiếu analyzer Pi còn NEEDS_INPUT khi chưa có source.

### F. Kiểm thử bắt buộc trước báo cáo

Chạy bằng `.venv\Scripts\python.exe -m pytest`; tests mặc định không mở Serial/GPIO và không cần chờ vài phút thật. Dùng fake clock và fixture deterministic cho logic thời gian:

1. Startup mô phỏng đúng 80%/SAMPLE, phần hardware không được tự mở từ đường demo.
2. Chuỗi hai lượt đầy đủ start → WAIT_EXPOSURE → expose → WAIT_RECOVERY → recover → WAIT_FINISH → finish → name → next → start. PWM không reset; UUID không trùng.
3. Đẩy fake clock xa qua deadline mà chưa gõ expose/recover: state vẫn WAIT, đúng route, không bắt đầu pha mới; thời gian chờ không cộng vào pha chính.
4. recover mới chuyển AIR/OFF; name/finish/between giữ lọc; next về SAMPLE. Timer hiệu lực đúng cả khi xử lý muộn.
5. Lệnh sai trạng thái, gõ lặp, extend sai/đúng, finish sớm/abort, bỏ notes, tên tiếng Việt/trùng tên đều giữ dữ liệu đúng.
6. Raw tiếp tục trong WAIT/notes/between; mẫu in-flight giữ context đầu vòng; schema/header/đơn vị/mapping A0 TGS đúng; null/flags không thành 0.
7. Quit/Ctrl+C/GUI-close/EOF theo chính sách được mô tả dừng sạch, không bị stdin worker giữ tiến trình; có lỗi ghi/queue đầy thì ERROR, output mô phỏng OFF và không tự phục hồi chạy lại.
8. Qt offscreen integration: terminal command queue có tác dụng, data/phase tiếp tục khi UI đọc snapshot, resize/zoom/notes không chặn writer; phân biệt với kiểm cửa sổ Windows thật.
9. Export và analysis không sửa hash raw; kết quả baseline/coverage/delta/AUC đã làm phải khớp fixture tính tay. Không ghi test mock là ADC/BME/hardware passed.

Nếu có lỗi, sửa trong phạm vi bước này và chạy lại nhóm liên quan; không lặp kiểm rộng khi đã pass mà không có thay đổi. Không copy PASS từ SETUP_REPORT hoặc suite lịch sử làm bằng chứng cho code mới.

### G. Đầu ra bàn giao của bước 02

Giao source package, schema/command-state table, test và hướng dẫn chạy ngắn. Tạo:

- `docs/SCHEMA_DATASET_V1.md`, `docs/COMMANDS_AND_STATES.md`.
- `runtime/STAGE02_REPORT.md`: thay đổi đã làm, entry point/lệnh thật, số test và kết quả thực, file demo được tạo, giới hạn và các phần chưa kiểm.
- `runtime/STAGE02_TEST_RESULTS.txt` hoặc log test tương đương.
- Một session dữ liệu mô phỏng nhiều lượt tái tạo được; test fake clock không thay đổi preset 60/120/60 của demo người dùng.

Kết thúc bằng lệnh mở demo đã thực sự tồn tại và chuỗi thao tác người dùng. Không báo đã có firmware/hardware khi chỉ mới xây mô phỏng. Không cần hỏi lại các quyết định A0 TGS, bơm 80%, USB laptop hay terminal/WAIT; chúng đã được chốt.

## 4. Mốc tiếp theo

Người dùng chạy demo, xem số đo/đồ thị và thử chuỗi lệnh; gửi lại `runtime/STAGE02_REPORT.md`. Trước tích hợp phần cứng cần source test S3 và model/cấu hình board/USB đã nạp thành công. Source Pi/sample cũ giúp đối chiếu algorithm/schema; việc chưa có chúng không làm mất giá trị của kiểm thử mô phỏng, nhưng phải giữ giới hạn tương thích rõ ràng.

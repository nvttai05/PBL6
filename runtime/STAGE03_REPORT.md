# RoboNose — báo cáo bước 03: firmware/USB/SerialDevice

Ngày **06/11/2026, Asia/Saigon (UTC+07:00)**. Mốc bàn giao: source mới, kiểm phần mềm/emulator và build/link profile tạm. **Chưa mở COM thật, upload hoặc đo hardware.**

**Kết quả cuối: 86 passed, 1 skipped trong 25.31 s. Hai profile CDC on/off đều build/link đầy đủ thành công và hash firmware hiện tại khớp source đã build.** Test skip là C++ native vì chưa tìm được compiler native trên PATH/các vị trí thường gặp; cross-compile mock thành công không được gọi là đã chạy C++/hardware.

## 1. Source và phạm vi

- Đã đọc prompt, AGENTS/target/paths, schema/command docs, implementation và tests bước 02; giữ demo và **47 test gốc**. Chuyển mốc AGENTS/target sang `firmware_usb_serial_device`.
- Reference đã xác minh: `stage03_input/reference_s3/RoboNose_ControlTest_v2_1`. Manifest gói 47 entry, manifest reference 43 entry, bốn file Bosch/provenance/license đều khớp SHA-256. [Inventory nguồn](stage03/source_inventory.json). Hash kiểm lại cuối xác nhận reference nguyên trạng; không chạy app/firmware cũ.
- `configs/paths.local.json` đã ghi `legacy_s3_source` tuyệt đối và vai trò historical reference vì trước đó null. Source Pi vẫn NEEDS_INPUT; không bịa commit/source/board.
- Firmware mới [RoboNose_Dataset_S3](../firmware/RoboNose_Dataset_S3/) dùng A0 TGS2602; A1 MQ3 #1; A2 MQ135 #2; A3 MQ3 #2. Bản ControlTest 2.1 vẫn A2 TGS và schema riêng, bị host mới từ chối trước BEGIN.
- Bosch vendor được copy nguyên hash cùng LICENSE_BOSCH.txt/BOSCH_UPSTREAM.json. ADS/output/parser tham khảo bản cũ rồi tách phần mới; không sửa source reference hoặc dữ liệu lịch sử.
- Host app 0.3.0, firmware 3.0.0, protocol `robonose.usb.v1`, CSV giữ `robonose.dataset.v1`. Không đổi cột/đơn vị v1 để trộn dữ liệu cũ.

## 2. Implementation

Firmware có entry setup/loop thật, module config, trial engine C++ thuần, sensor policy, ADS reader, Bosch adapter, output hardware, JSON frame và runtime/task/mailbox.

Control owner giữ phase/deadline/lease/output. Một sensor task sở hữu hai I2C bus. RX/TX task riêng; normal RX queue 8, OFF mailbox riêng; TX queue 4 frame <8192 byte. Control không gọi USB read/write: UART core có shared mutex, nên task USB bị chặn không được giữ tick/OFF. Full-frame staging ở static storage, không đặt frame 8 KiB lên stack loop 8 KiB của profile tạm. Không tự pin core. Giới hạn thời gian/stack này chưa được đo trên phần cứng.

ADS single-shot single-ended, PGA 0/FSR ±6.144 V, 128 SPS, count × 0.0001875. Một conversion cho count/V, config trước/sau, timeout hữu hạn, signed count và bus/address/stage/Wire code khi lỗi. ADC_LIMIT giữ raw/invalid; không clamp số âm hoặc sửa peak suspect. BME forced 300°C/100 ms T2/H2/P4, get_conf/register readback, gas wait lượng tử hóa, status/index/fresh tách gas_valid; no-new-data null, Pa→hPa một lần. Pi 320°C/150 ms T8/H2/P4 vẫn là profile khác, production null.

Boot/reset OFF trước USB/sensor. Mở Serial Monitor không ON. HELLO/version/map/config/OFF được xác minh; host nhận mẫu preflight mới, writer ghi và sync thành công rồi **tự BEGIN 80%/SAMPLE/MONITOR**. Không thêm Start Session hoặc opt-in bơm. Một-use ticket/session UUID chống phát lại BEGIN cũ; retry cùng ID không pulse ON/lặp trial. Quit sạch có thể tạo session mới; MCU fault latch cần reset/readiness và không tự hồi bởi heartbeat/reconnect.

60/120/60 và mọi WAIT giữ nguyên. MCU quyết định start/expose/recover/extend/finish/abort/next; hết giờ chỉ vào WAIT. Name/notes là host metadata trong MCU WAIT_NAME. Finish/name/next không reinit sensor/heater hoặc bật PWM lại. OFF ưu tiên không chờ TX/writer queue; PING chỉ do host khỏe receive/write/sync/control/UI gia hạn lease 15 s, invalid command không gia hạn.

Host mới: [usb_protocol.py](../robonose_s3/usb_protocol.py), [serial_device.py](../robonose_s3/serial_device.py), [hardware.py](../robonose_s3/hardware.py), [emulator.py](../robonose_s3/emulator.py). Một worker sở hữu transport; serial chỉ import/open trong backend hardware được chọn rõ ràng. Hardware không chạy StateMachine Python hoặc fallback sang SimDevice.

Logger/quality/dashboard dùng pipeline cũ, thêm mode HARDWARE/EMULATED, wire.jsonl và snapshot HELLO/readback/clock mapping. Sample context là context MCU đầu scan; epoch cũ không kéo UI lùi sau ACK mới. NEXT/OFF có barrier_seq, host chờ mẫu in-flight trước finalize export/analysis. Seq gap không backfill; duplicate/reordered giữ wire/parser log nhưng không nhân đôi canonical. OFF ACK thiếu được báo unconfirmed/ERROR, không giả thành feedback cơ khí.

Đặc tả đầy đủ: [USB_PROTOCOL.md](../docs/USB_PROTOCOL.md), [FIRMWARE_BUILD_AND_RUN.md](../docs/FIRMWARE_BUILD_AND_RUN.md). Schema/command docs đã cập nhật phần hardware/time bases.

## 3. Môi trường và build thực

Dùng đúng `python_exe` trong paths.local: Python 3.11.9 x64 của `.venv`; không gọi Python 3.8 trên PATH, cài lại dependency/core, đổi ExecutionPolicy hay dùng BAT/PlatformIO.

CLI 1.5.1/core 3.3.12 hiện có. `board listall` và `board details` xác nhận generic `esp32:esp32:esp32s3` và options có thật. Cả hai profile dùng USBMode=hwcdc, FlashSize=4M, PSRAM=disabled, PartitionScheme=default. **Đây là PROVISIONAL_COMPILE_ONLY, không xác nhận board/flash/PSRAM/USB thật.**

| Profile cuối | CDCOnBoot | Full compile/link | Program storage | Static RAM theo linker | Thời gian |
| --- | --- | --- | --- | --- | --- |
| cdc_on | cdc | Exit 0 / LINK_PASS | 352,597 byte / max 1,310,720 | 35,376 byte / max 327,680 | 17.234 s |
| cdc_off | default | Exit 0 / LINK_PASS | 357,273 byte / max 1,310,720 | 35,184 byte / max 327,680 | 19.875 s |

Đây là số linker của profile generic; không phải RAM/heap/stack đo trên board, chưa gồm các cấp phát task/queue runtime. Compiler thực: **xtensa-esp-elf-g++ 14.2.0, crosstool-NG esp-14.2.0_20260121**, tool esp-x32/2601.

Log/profile/source hash: [CDC on](stage03/profile_cdc_on.json), [log on](stage03/build_cdc_on.log), [CDC off](stage03/profile_cdc_off.json), [log off](stage03/build_cdc_off.log). ELF/BIN: [artifacts](stage03/artifacts/). [VALIDATION.json](stage03/VALIDATION.json) đối chiếu hash source cuối với profile đã build và hash artifact.

Lệnh thực:

```powershell
.\.venv\Scripts\python.exe scripts/build_stage03.py --profile cdc_on
.\.venv\Scripts\python.exe scripts/build_stage03.py --profile cdc_off
```

Script lưu argv CLI chính xác, không có --port/--upload/-u. Lần đầu trong sandbox bị build helper từ chối giải nén VCRUNTIME140.dll vào temp; chạy lại sau khi được cấp quyền ngoài sandbox đã thành công. Không đổi core để né lỗi. Cross-compile thuần ban đầu lộ phụ thuộc strtok_r trong strict C++17; đã thay tokenizer ASCII portable và compile lại thành công.

## 4. Test cuối và giới hạn chứng cứ

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=runtime/STAGE03_TEST_RESULTS.xml
.\.venv\Scripts\python.exe scripts/check_firmware_tests.py
```

Suite: **86 passed, 1 skipped in 25.31s**. [Log](STAGE03_TEST_RESULTS.txt), [JUnit](STAGE03_TEST_RESULTS.xml). 47 test bước 02 vẫn nằm trong suite và đạt; [regression ban đầu](stage03/STAGE02_REGRESSION.txt).

| Nhóm mới | Đã kiểm bằng software/fake transport |
| --- | --- |
| Handshake | Sai firmware/protocol/schema/A2 map/FSR/LSB/divider/pins/heater/applied profile/ON/fault → từ chối trước BEGIN |
| Framing | Split frames, oversize/resync, boot chatter, duplicate JSON keys, NaN, malformed object |
| Integrity | Gap/trùng/reordered/old snapshot, boot reset, foreign session, signed/null/count-V/timing; current snapshot không lùi |
| Request | Retry cùng byte/ID không tạo trial thứ hai, consumed BEGIN ticket/old session replay, ACK sai state, timeout, missing OFF ACK |
| Fault/close | Writer lỗi vẫn gửi và parse priority OFF, OFF không giả physical feedback, quit trong handshake không auto BEGIN, không resume sau lỗi |
| Pipeline | Hai lượt emulator qua SerialDevice + Qt/logger, name/notes tiếng Việt/trùng tên, raw WAIT, pause/resize/zoom, export/summary giữ context/hash |
| Health | Receive/write/sync/UI access phải khỏe; source demo vẫn qua guard không import serial |

Fixture dùng chung [stage03_phases.tsv](../fixtures/stage03_phases.tsv): 116 bước Python reference đạt. Đã cung cấp C++ native driver/engine test runner nhưng **chưa chạy native parity** vì không tìm thấy g++/clang++ native. Năm translation units engine/ADS/output/test được Xtensa cross-compile thành object thành công; [CPP_TEST_RESULTS.json](stage03/CPP_TEST_RESULTS.json) ghi `COMPILE_ONLY`, `cpp_executed=false`. Full Arduino link ở mục 3 dùng core thật, không thay bằng API stubs. Mock object compilation không phải ADC/BME/LEDC hardware passed.

Demo entry point hiện tại đã chạy offscreen 2 s, exit 0, CLOSED/PWM 0: [DEMO_SMOKE.txt](stage03/DEMO_SMOKE.txt). Cửa sổ Windows thật/console/DPI/multi-monitor vẫn NOT_EXECUTED.

## 5. Dataset emulator bàn giao

```powershell
.\.venv\Scripts\python.exe scripts/stage03_fixture.py
```

Session bàn giao mới nhất [881888dc-e3b0-4e6b-b923-452dcc00c29c](../data/emulation/2026-11-06/Phien_090000_2026-11-06_881888dce3b0/): **517 dòng**, hai trial COMPLETE, quality UNCONFIGURED tách riêng. Tên trùng nhưng UUID khác:

- `edbf2900-58d0-422b-a712-4fa01a2ec456`.
- `8c58163c-d0bd-4577-a39f-88b07d29cfa5`.

Transport chia 257 byte/chunk; clock ảo, vẫn giữ preset 60/120/60. Có WAIT/name, marker, extension 10 s và một dòng lỗi TGS/BME stale tạo null. Khởi tạo sensor 1 lần, PWM ON 1 lần, OFF ACK khi đóng được xác nhận ở mức command. Raw/export/summary/wire hash đã đối chiếu; raw mẫu bước 02 không đổi.

Manifest [EMULATED_FIXTURE.json](stage03/EMULATED_FIXTURE.json), [log](stage03/EMULATED_FIXTURE_LOG.txt), [ảnh dashboard](stage03/EMULATED_DASHBOARD.png). Ảnh offscreen đã được xem. Fixture dùng checkpoint 0.02 s để đồng hồ ảo không vượt writer sync; **default người dùng vẫn 5 s**. Đây không phải benchmark thời gian thực hay dữ liệu cảm biến thật. Các lần fixture trước được giữ nguyên dưới UUID khác.

## 6. Board readiness và phần chưa làm

[STAGE03_BOARD_READINESS.json](STAGE03_BOARD_READINESS.json): model/FQBN/flash/PSRAM/USB/cổng thật vẫn null; chỉ có profile generic compile. Reference platformio.ini dùng board ví dụ, không chứng minh board thật. COM3 ở inventory cũ là Intel SOL, không được chọn mặc định. Cần model/ảnh module và Tools từng nạp thành công trước hướng dẫn nạp theo bo.

Chưa upload, mở serial thật, tác động bơm/van, kiểm nguồn/AOUT/readback ngoài mạch, gate/reset/brownout, mất USB, OFF latency, stack high-water hoặc soak/blank thật. Các threshold 2/5/15 s là chính sách phần mềm, chưa có bằng chứng timing vật lý. ACK chỉ xác nhận output được ra lệnh; không có flow/RPM/vị trí van đo được. DTR/RTS deassert trước open không bảo đảm driver/bridge không tạo xung nếu chưa đo.

Source Pi/sample lịch sử vẫn NEEDS_INPUT; compatibility adapter/analyzer Pi chưa xác minh. Median summary, delta/AUC/recovery metrics, analog thresholds/classifier, native GUI và soak/blank thật từ bước 02 tiếp tục là phần chưa triển khai/kiểm; không tự đổi thành PASS khi thêm USB.

## 7. Lệnh bàn giao

Demo luôn không mở serial:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo
```

Lệnh hardware **có implementation nhưng chưa chạy**; chỉ dùng sau khi board/firmware/port được xác minh:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --port COM_THUC_TE --serial-kind native-cdc
# Hoặc --serial-kind uart cho bridge đã xác minh.
```

Hardware startup hợp lệ sẽ tự command **80%**; không yêu cầu bật bơm riêng. Upload chỉ có mẫu điều kiện trong [FIRMWARE_BUILD_AND_RUN.md](../docs/FIRMWARE_BUILD_AND_RUN.md), chưa có lệnh upload đã thực hiện. Dừng ở mốc source/software/provisional build để người dùng kiểm báo cáo và cung cấp board trước phần nạp/đo thật.

## 8. Rà soát hoàn tất theo yêu cầu tiếp tục bước 03

Đã hoàn tất phần source/mock/provisional build trong prompt. Rà soát bổ sung sửa ba điểm ở host adapter:

1. Active telemetry và ACK thường phải có đúng session UUID; session rỗng/thiếu không còn được nhận như wildcard preflight. Idle preflight vẫn giữ ngoại lệ, còn OFF có ngoại lệ scope riêng để dừng được ngay trước BEGIN.
2. ACK có tương quan phải đủ request ID, accepted boolean, reason string, applied_ms và barrier_seq hợp lệ; không xác nhận thành công khi thiếu các trường này.
3. Lỗi một frame không bỏ các frame tiếp theo trong cùng chunk, đặc biệt OFF ACK. Lỗi protocol phát sinh trong shutdown phải làm session ERROR dù commanded OFF đã được ACK; không báo CLOSED sạch khi đã có lỗi.

Đã thêm chín test hợp đồng/fault cho các trường hợp trên. Lần suite đầu của đợt rà soát phát hiện lỗi trạng thái shutdown (85 passed, 1 failed, 1 skipped); [log](stage03/COMPLETION_INITIAL.txt). Đã sửa implementation và chạy lại ba test shutdown liên quan đạt ([log](stage03/SHUTDOWN_RETEST.txt)), sau đó suite đầy đủ đạt **86 passed, 1 skipped** như mục 4. Không đổi kỳ vọng để bỏ lỗi.

Đã chạy lại fixture byte transport hai lượt với host code hiện tại, kiểm raw/export/summary/wire và giữ các session cũ nguyên trạng. [VALIDATION.json](stage03/VALIDATION.json) có hash từng module host, hash artifact, kiểm firmware source đúng bản đã link, 47 test bước 02 và raw mẫu cũ không đổi. Firmware không thay đổi trong đợt rà soát host này nên giữ hai build/link đã xác minh ở mục 3. Không cài compiler/core mới để biến test native đang skip thành kết quả giả.

Board thật/Pi source/native GUI và đo hardware vẫn là các mục còn thiếu ở mục 6. Chúng không chặn mốc phần mềm/build tạm đã hoàn thành, nhưng chưa đủ để upload hoặc thu thật.

## 9. Bản sửa sau sự cố START của lượt 4 (06/11/2026)

Theo yêu cầu kiểm tra dataset hardware do người dùng cung cấp, đã đọc log
phiên `20c1efbb-3143-4e37-86bf-e503fda3e7e0` và lượt
`ae707239-de77-4a6b-8999-7e03985d609b`. MCU xác nhận START/PWM80 rồi tự ERROR/OFF
trước khi host gửi FAULT; lượt có 0 dòng. Đã sửa lỗi tràn phép trừ unsigned của
watchdog USB khi TX progress mới hơn mốc thời gian vòng lặp; thêm fault_reason
đầu tiên và HELLO revision `usb_watchdog_time_order.v1`. Log cũ không ghi mã
nguyên nhân nên việc gán đúng nhánh gây sự cố này vẫn là suy luận có căn cứ.

Kết quả mới: **98 passed, 1 skipped**; 47 test bước 02 giữ nguyên và đạt.
C++ static_assert về tràn số/biên watchdog đã cross-compile thành công; các test
C++ runtime chưa chạy native. Hai profile provisional build/link lại thành
công: CDC-on program **353241**, static RAM **36464** byte; CDC-off program
**357933**, static RAM **36272** byte. Đây là số mới thay cho số build trước ở
mục 3. Profile/log/JUnit/VALIDATION hiện phản ánh bản sửa mới; bản trước đợt sửa
được lưu trong `runtime/start_fault/prior_validation`.

Đối chiếu SHA-256 xác nhận 18 file của phiên hardware gốc không đổi. Không mở
COM thật, upload hoặc chạy tải trong đợt này; log hardware là dữ liệu có sẵn
do người dùng thu, không phải kết quả đo do agent thực hiện.

Chi tiết: [START_FAULT_REPORT.md](START_FAULT_REPORT.md),
[bằng chứng frame](START_FAULT_EVIDENCE.json),
[kiểm chứng dữ liệu/build](START_FAULT_VALIDATION.json).
Bản sửa cần được nạp lại đúng cấu hình board đã xác minh trước khi kiểm lại
START trên thiết bị; cấu hình board trong paths.local.json vẫn UNKNOWN.

## 10. Tên folder dữ liệu theo yêu cầu mới

Đã đổi host sang storage layout v2: phiên `Phien_HHMMSS_YYYY-MM-DD_ID12`, lượt
`Ten_mau_HHMMSS_YYYY-MM-DD_ID12`; UUID đầy đủ trong raw/metadata/USB giữ nguyên.
Lệnh name đổi folder bởi writer. Đã chuyển 14 phiên/18 lượt cũ và đối chiếu
124 file không thay đổi nội dung; cập nhật tra cứu, fixture và audit. Suite
hiện tại **113 passed, 1 skipped**, gồm đủ 47 test gốc bước 02. Firmware giữ
nguyên bản sửa watchdog ở mục 9, chưa có phép thử phần cứng mới trong đợt này.
Chi tiết và đường dẫn mới ở [DATA_LAYOUT_REPORT.md](DATA_LAYOUT_REPORT.md).

## 11. Chẩn đoán COM8 Short serial write ở phiên 22:11:49

Phiên `26258fa9-c7ed-4104-86ce-45617ee41ed7` có firmware revision mới, vẫn ở
MONITOR và lưu 818 dòng trước lỗi host `Short serial write`. Wire có các JSON
bị cắt và 5 seq thiếu, cùng boot ID; chưa xác định được nguyên nhân USB/driver/
MCU gốc. Host gửi được ALL_OFF best-effort nhưng không đọc OFF ACK ở nhánh
ngoại lệ đó. PWM80 cuối là trạng thái đã nhận trước lỗi; bơm thật chưa xác nhận.

Người dùng sau đó xác nhận bơm thực tế đã tắt. Đây là quan sát được báo lại;
không đổi OFF ACK=false của phiên và chưa xác định cơ chế/độ trễ dừng.

Đã bổ sung reason vào terminal và log số byte/attempt của write lỗi, giữ
chính sách lỗi/OFF và dataset gốc. Suite mới **118 passed, 1 skipped**; chưa
mở COM, nạp hoặc kiểm hardware trong đợt này. Chi tiết và giới hạn bằng chứng:
[USB_LINK_FAULT_REPORT.md](USB_LINK_FAULT_REPORT.md).

## 12. Sửa USB native và shutdown sau lỗi lặp lại

Phiên 22:35:33 lỗi PING 0/64 byte và ALL_OFF 0/8 byte trong WAIT_RECOVERY.
Đã triển khai revision `usb_idf_stream_off_ack.v2`: native hwcdc dùng driver
ESP-IDF sẵn có, buffer TX/RX 16384/1024, gửi từng chunk có deadline; host giữ
COM cho tối đa 3 lần OFF và đọc ACK trong budget shutdown, không reconnect
hoặc resume. Info hiển thị revision/transport; metadata chốt lỗi sửa cách
ánh xạ clock và đánh dấu thời gian ước lượng. Dữ liệu cũ giữ nguyên.

Suite cuối **126 passed, 1 skipped**, giữ đủ 47 test bước 02. C++ object/mock compile
thành công, chưa chạy native. Build CDC-on program **356393**, static RAM
**36472** byte; CDC-off program **358861**, static RAM **36280** byte; đây là
số build hiện tại thay cho các bản trước. ELF xác nhận link driver IDF.

Người dùng xác nhận nguồn bơm riêng; log hiện chưa đủ kết luận lỏng dây/quá
nóng. Chưa đo nguồn/dòng/nhiệt tải hoặc retest hardware. Chi tiết, evidence,
giới hạn và cách kiểm revision:
[USB_RECOVERY_REPORT.md](USB_RECOVERY_REPORT.md).

Rà soát cuối thêm test hủy BEGIN thiếu newline để resync không vô tình bật
bơm sau fault; host dùng ký tự hủy `!` trước LF. Đã đối chiếu nguồn/đầu nối/
nhiệt theo [USB_POWER_PUMP_DIAGNOSTICS.md](../docs/USB_POWER_PUMP_DIAGNOSTICS.md),
ghi riêng quan sát bơm đã tắt ở phiên cũ và trạng thái chưa biết của phiên mới.

## 13. Sửa panic watchdog ngắt USB ở revision v3 (07/11/2026)

Phiên `Phien_235935_2026-11-06_8df0399528dc` đã nạp v2, vẫn MONITOR,
758 dòng seq 71–828 liên tục, chưa có trial. Wire ghi sáu panic CPU1; panic
đầu lúc host mono 758.531 s có trước PING 379 ở 759 s. Timeout PING là hậu quả
MCU treo/reset. ELF trong Arduino IDE cache khớp SHA prefix `8708bee49` của
dump; decode và disassembly xác nhận ISR USB RX/TX gặp trạng thái BUS_RESET
0x200 không được xử lý/xóa. V2 chưa dọn enable ngắt kế thừa khi cài driver.

Revision mới `usb_irq_handoff.v3` snapshot/dọn ngắt trước cài IDF, giữ pending
RX/TX, loại bit ngoài 0xC và công bố mask trong HELLO/info. Host từ chối BEGIN
nếu mask v3 không an toàn; nhận diện panic console ngay khi đọc để giữ nguyên
nguyên nhân MCU thay vì chỉ chờ ACK timeout. Các dump vẫn giữ đầy đủ trong wire.
Không tăng watchdog, không thay core/SDK hoặc logic PWM/pha/dataset.

Suite hiện tại **139 passed, 1 skipped**, gồm đủ 47 test bước 02. C++ mock
cross-compile và static_assert policy ngắt đạt; chưa chạy C++ native. Hai build
provisional/link v3 đạt: CDC-on program **356761**, static RAM **36488** byte;
CDC-off program **359117**, static RAM **36296** byte. Audit đối chiếu source,
artifact, Bosch/reference, raw bước 02; 5 file phiên mới và 17 file hai phiên
cũ không đổi. Đây là số build mới nhất, thay các số ở mục 12.

Người dùng báo nguồn bơm riêng, dây đã hàn chắc, bơm dừng khi chưa nóng.
Đã có bằng chứng lỗi ISR phần mềm; tác nhân phát sinh USB bus reset chưa xác
định. Không mở COM/upload/đo hardware trong đợt sửa; cần nạp v3 và kiểm lại.
Model/flash/PSRAM vật lý vẫn UNKNOWN; Tools quan sát từ ELF cache được ghi
riêng, không điền thành cấu hình board đã xác minh.

Chi tiết: [USB_ISR_REPORT.md](USB_ISR_REPORT.md),
[evidence](USB_ISR_EVIDENCE.json), [validation](USB_ISR_VALIDATION.json).

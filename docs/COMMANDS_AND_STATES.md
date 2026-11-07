# Terminal và trạng thái — demo RoboNose

Chạy tại root bằng interpreter đã chuẩn bị:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo
```

Một engine mô phỏng sở hữu phase/deadline trong demo; Qt chỉ đọc snapshot và terminal gửi command queue. Bước 03 đã thêm backend USB: MCU sở hữu phase/deadline, host không chạy StateMachine/timer tự đổi pha. Demo vẫn không import/mở serial. Chọn hardware cần `--port` và `--serial-kind` rõ ràng; không mặc định chọn COM3. Xem [USB_PROTOCOL.md](USB_PROTOCOL.md) và [FIRMWARE_BUILD_AND_RUN.md](FIRMWARE_BUILD_AND_RUN.md).

## Chuỗi chính

| Trạng thái | Chuyển tiếp | Route / van | PWM SIMULATED |
| --- | --- | --- | --- |
| Khởi tạo log | Writer ready → MONITOR | SAMPLE / ON B | Tự 80% |
| MONITOR | `start` → BASELINE | SAMPLE | 80% |
| BASELINE | 60 s → WAIT_EXPOSURE | SAMPLE | 80% |
| WAIT_EXPOSURE | `expose` → EXPOSURE | SAMPLE | 80% |
| EXPOSURE | 120 s → WAIT_RECOVERY | SAMPLE | 80% |
| WAIT_RECOVERY | `recover` → RECOVERY | SAMPLE cho tới recover | 80% |
| RECOVERY | 60 s → WAIT_FINISH | FILTERED_AIR / OFF A | 80% |
| WAIT_FINISH | `finish` → WAIT_NAME; `extend N` → RECOVERY segment mới | FILTERED_AIR | 80% |
| WAIT_NAME | `name ...`, `notes ...`; `next` → MONITOR | FILTERED_AIR cho tới next | 80% |
| MONITOR sau next | Chờ start | SAMPLE | Giữ 80% |
| Bất kỳ đang chạy | `quit` / Ctrl+C / đóng cửa sổ / EOF / lỗi | FILTERED_AIR | 0% |

Hết giờ chỉ vào WAIT và tiếp tục raw; chờ bao lâu cũng không tự expose/recover. Deadline ghi mốc hiệu lực đúng ngay cả khi engine xử lý muộn. WAIT không cộng vào thời lượng pha. Finish/name/next không reinit sensor hoặc phát ON lần nữa. MONITOR bao gồm warm-up, không có Start Session bổ sung.

## Bảng lệnh

| Lệnh | Trạng thái được phép | Tác dụng |
| --- | --- | --- |
| `start` | MONITOR | UUID mới, baseline 60 s; ghi cảnh báo quality nếu chưa stable |
| `expose` | WAIT_EXPOSURE | Bắt đầu 120 s, giữ SAMPLE |
| `recover` | WAIT_RECOVERY | Đổi FILTERED_AIR rồi bắt đầu 60 s |
| `extend <s>` | WAIT_FINISH | Số hữu hạn `0 < s <= 3600`; đoạn RECOVERY mới, hết lại WAIT_FINISH |
| `finish` | BASELINE/EXPOSURE/RECOVERY và các WAIT của chúng | WAIT_FINISH → COMPLETE; kết thúc sớm → ABORTED; vào WAIT_NAME, lọc, giữ bơm |
| `abort` | Các pha/WAIT đang thu | ABORTED → WAIT_NAME, lọc, giữ bơm |
| `name <tên>` | WAIT_NAME | Gán đúng lượt vừa xong; UTF-8, khoảng trắng, dấu phẩy/nháy; UUID giữ nguyên |
| `notes <nội dung>` | WAIT_NAME | Cập nhật notes tùy chọn |
| `next` | WAIT_NAME | Đóng export/index/summary lượt cũ; MONITOR, chưa tự baseline; có thể bỏ tên/notes |
| `mark <text>` | Mọi trạng thái đang chạy | Event với thời điểm lệnh; không phải mốc khí tới sensor |
| `status`, `info` | Mọi trạng thái đang chạy | Context; dashboard hiển thị thêm writer và quality |
| `durations` | Mọi trạng thái đang chạy | Preset thực đang dùng |
| `help` | Mọi trạng thái đang chạy | Danh sách lệnh |
| `quit` | Mọi trạng thái đang chạy | Output OFF trước, đóng và sync session |

Lệnh sai trạng thái, thiếu/thừa đối số, số không hữu hạn hoặc dài quá 2048 ký tự bị từ chối với lý do; không đổi route/timer do lệnh đó. Timer tự nhiên vẫn có thể hết trong lúc chờ lệnh. `start` lặp trong BASELINE bị từ chối. API có request ID: cùng ID/cùng nội dung trả lại result, không tạo event/lượt thứ hai trong cache 256 ID; ID cũ với nội dung khác bị từ chối. Hai lần gõ mark với ID mới là hai marker có chủ ý. Không có retry serial/ACK hardware trong bước này.

Quit giữa lượt giữ ABORTED và dữ liệu; lỗi giữ ERROR nếu ghi được. Sau fault không nhận start để tự chạy lại. Mở demo mới tạo session mới, không nối PARTIAL cũ. Extension đang chạy mà finish sớm cũng là ABORTED theo quy tắc pha chưa đủ.

## Điều khiển và đóng chương trình

Input nằm ở worker riêng, queue command 64, mỗi vòng engine xử lý tối đa 16 lệnh rồi kiểm acquisition. Windows console dùng đọc phím không chặn, hỗ trợ tiếng Việt, backspace, Enter; không cung cấp history/autocomplete. Pipe dùng os.read UTF-8 ở daemon, không khóa buffered stdin khi thoát. EOF xử lý các dòng đã nhận rồi queue quit; nếu queue không còn chỗ thì yêu cầu dừng trực tiếp. Ctrl+C và GUI close dùng cờ dừng riêng, không phải đợi command queue hoặc Enter.

Qt ở main thread, refresh 200 ms, bộ đệm 1800 mẫu. Tám đại lượng có đơn vị/count, phase/countdown, quality và writer health. Pause chỉ dừng cập nhật đồ thị, số đo/thu/ghi tiếp tục; resume trả lại history hữu hạn. Zoom bằng chuột; combobox chọn 120/600/1800 s. Gap/invalid là đoạn đứt; marker/phase/WAIT có vạch nhãn, tối đa 16 mốc trên hình. Hover quality xem slope/range/noise/reasons. Các giới hạn này chỉ là giới hạn hiển thị; raw không bị cắt theo buffer UI.

Ví dụ thao tác theo thời gian thật:

```text
start
[đợi BASELINE 60 s → WAIT_EXPOSURE; đặt mẫu giả/quan sát]
expose
[đợi EXPOSURE 120 s → WAIT_RECOVERY]
recover
[đợi RECOVERY 60 s → WAIT_FINISH]
finish
name Mẫu thử 1
notes Ghi chú tùy chọn
next
start
...
quit
```

Để tái tạo nhanh dữ liệu hai lượt bằng thời gian ảo mà vẫn giữ preset 60/120/60:

```powershell
.\.venv\Scripts\python.exe scripts/stage02_demo_fixture.py
```

Fixture ghi session mới dưới `data/simulation`, gồm WAIT, hai tên trùng, extension và ảnh dashboard offscreen. Không phải benchmark thời gian thực hoặc kiểm cửa sổ Windows native. `runtime/STAGE02_FIXTURE.json` trỏ tới lần sinh gần nhất; những session cũ giữ nguyên.

## Tìm lại dữ liệu khi nhiều lượt trùng tên

Mỗi lượt có UUID/thư mục riêng; tên như `Tai` nằm trong metadata và có thể trùng. Từ PowerShell ở root workspace, tìm tất cả lượt mang tên đó:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --find-sample Tai
```

Kết quả có loại dữ liệu HARDWARE/SIMULATED/EMULATED, thời điểm mẫu đầu (+07:00), số lượt trong phiên, UUID, trạng thái, notes và đường dẫn đầy đủ tới thư mục chứa raw.csv/metadata.json/summary.json. Chọn theo ngày/giờ, số lượt và UUID; không coi hai lượt cùng tên là cùng một phép đo. Tên nhiều từ đặt trong dấu nháy, ví dụ `--find-sample "Tai lần sáng"`.

Tra cứu không phân biệt hoa/thường, giữ phân biệt dấu tiếng Việt (`Tai` khác `Tài`). Lệnh chỉ đọc metadata và dòng raw đầu tiên; không mở GUI/COM, không sửa/đổi tên/gộp hoặc ghi đè dataset. Có thể chạy ở terminal khác trong lúc app thu; metadata đang cập nhật/chưa có mẫu sẽ hiện rõ giới hạn. Thời gian hiển thị lấy từ dòng dữ liệu đầu, không khẳng định là thời điểm khí tới cảm biến. COMPLETE vẫn chỉ nói quy trình, quality xem summary.json.

## Folder mẫu dễ đọc (layout v2)

`name Tai` đổi folder lượt sang dạng `Tai_HHMMSS_YYYY-MM-DD_ID12` ngay khi
writer xử lý metadata. Có thể đổi lại name trong WAIT_NAME; UUID/số đo và thời
điểm bắt đầu lượt giữ nguyên. Chưa nhập name thì folder bắt đầu bằng
`Chua_dat_ten`. Folder phiên cha là `Phien_HHMMSS_YYYY-MM-DD_ID12`. Một phiên có
thể chứa nhiều tên mẫu khác nhau. Có thể lọc trực tiếp folder lượt bằng `Tai_*`.

Chuyển dữ liệu đã có khi app thu đã đóng:

```powershell
.\.venv\Scripts\python.exe scripts/migrate_data_layout.py
.\.venv\Scripts\python.exe scripts/migrate_data_layout.py --apply
```

Lệnh đầu lập kế hoạch; lệnh thứ hai chuyển folder và đối chiếu hash mọi file.
Phiên PARTIAL/đang ghi được giữ nguyên; một backend đang có writer sẽ chặn
migration. Các file CSV/JSON/JSONL cũ giữ nguyên nội dung. Journal và ánh xạ
folder cũ/mới nằm trong `runtime/DATA_LAYOUT_MIGRATION.json`. Hoàn tác khi dữ
liệu lưu trữ chưa thay đổi:

```powershell
.\.venv\Scripts\python.exe scripts/migrate_data_layout.py --rollback runtime/DATA_LAYOUT_MIGRATION.json
```

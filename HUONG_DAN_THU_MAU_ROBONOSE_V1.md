# Hướng dẫn thu mẫu thử RoboNose v1.0 — điều khiển bơm thủ công

**Mục tiêu:** khảo sát tín hiệu thật của BME688, MQ135, MQ3 và các yếu tố gây trôi. Đây là các lượt thăm dò; chưa gán ý nghĩa nhận dạng mùi hay xây dựng tập dữ liệu chuẩn. **Phiên bản hướng dẫn: 03/10/2026.**

Hướng dẫn này dựa trên các lệnh và màn hình bạn đã gửi. Trước khi dùng lâu dài, cho Codex trên Pi đối chiếu với CLI và file cấu hình hiện tại, cập nhật tài liệu cùng repo nếu có thay đổi.

## 1. Nguyên tắc hoạt động

- Pi **chỉ đọc cảm biến và ghi dữ liệu**. Mọi lệnh thu dùng `--pump-disabled`; không chạy `pump-test`, không dùng `--enable-pump` và không dùng lệnh `pump on/off` để điều khiển nguồn bơm.
- Bơm, nếu sử dụng, được bật/tắt bằng **nguồn riêng có công tắc phù hợp**. Trạng thái `pump command=DISABLED` trên màn hình là trạng thái **lệnh phần mềm**, không cho biết bơm ngoài đang chạy hay dừng.
- Ghi `mark ...` ngay khi bạn thay đổi bơm, nắp hoặc ống; ghi trạng thái thực tế vào `notes ...` khi kết thúc. Không ghi chú rằng bơm ON/OFF nếu bạn chưa nhìn thấy hoặc xác nhận trạng thái đó.
- BASELINE, EXPOSURE, RECOVERY lần lượt dự kiến 30, 60, 60 giây. Các khoảng `WAIT_*` dùng để thao tác thủ công và **tiếp tục ghi cảm biến**; chúng không được tính vào thời lượng của pha chính.

## 2. Trước khi cấp nguồn cho bơm

Nguồn/đường dây cấp cho bơm đã từng có dấu hiệu cháy/hỏng. **Chưa cấp điện lại cho cụm bơm bằng nguồn đó.** Nhờ người có chuyên môn kiểm tra adapter, dây nguồn, cực tính, tải bơm, module MOSFET và diode; chỉ tiếp tục khi có bộ nguồn 12 V an toàn và cách bật/tắt phù hợp. Không thao tác với dây AC hoặc đầu DC hở khi đang có điện. Bơm không được nối trực tiếp vào GPIO của Pi. [Tài liệu Raspberry Pi](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html) cũng yêu cầu dùng mạch điều khiển riêng cho động cơ.

Bạn **có thể bắt đầu các lượt không dùng bơm** ngay sau khi cảm biến và dây đã được kiểm tra. Ghi rõ `pump_external=OFF` để phân biệt với lượt có luồng khí cưỡng bức.

Khi cụm nguồn đã được kiểm tra, lần đầu chỉ thử có giám sát trong thời gian ngắn, xác nhận bơm dừng khi tắt công tắc. Tránh chạy bơm khi đường hút/xả bị bịt kín; tuân theo hướng dẫn của đúng mẫu bơm đang dùng. Nếu adapter nóng bất thường, có mùi khét, bơm không dừng, hoặc Pi/cảm biến mất kết nối thì ngắt nguồn và kiểm tra mạch trước khi thu tiếp.

## 3. Kiểm tra cảm biến và làm ấm

Trên Pi:

```bash
cd /home/pi/robonosev1.0
.venv/bin/python -m robonose doctor --config config.example.toml
.venv/bin/python -m robonose monitor --hardware --pump-disabled \
  --config config.example.toml
```

Xem BME688 có `BME=OK`, gas có `gas_valid=True`, và cả hai kênh MQ có điện áp hữu hạn. Đối chiếu điện áp ADS với cách mắc và hệ số chia áp thực tế. `heater_stable=True` chỉ nói về trạng thái gia nhiệt của phép đo, **không có nghĩa đường gas đã ổn định**.

Bạn từng thấy gas tăng rất nhanh, nhiệt độ BME khoảng 39 °C và cảnh báo `ĐANG TRÔI`. Hãy để hệ thống chạy và quan sát xu hướng trước khi bấm `start`. Không có một thời gian làm ấm cố định phù hợp mọi lần; nếu còn trôi thì vẫn có thể thu thăm dò nhưng phải đánh dấu lượt đó có nền trôi, không so sánh định lượng với lượt khác. Nhiệt độ BME tại vị trí đặt cảm biến không mặc nhiên là nhiệt độ phòng.

Thoát `monitor` bằng Ctrl+C. Nếu ứng dụng tạo một lượt `ABORTED`, đó là bản ghi quan sát bị dừng chủ động; kiểm tra thư mục dữ liệu của lượt đó trước khi xóa gì.

## 4. Lượt đầu: đối chứng không mẫu, không bơm

Để kiểm tra cả đường ghi và đồ thị, giữ buồng ở một cấu hình cố định, không đưa mẫu vào. Chạy:

```bash
cd /home/pi/robonosev1.0
.venv/bin/python -m robonose collect --hardware --pump-disabled \
  --config config.example.toml \
  --baseline 30 --exposure 60 --recovery 60 \
  --sample-description "doi chung khong mau" \
  --sampling-method "buong co dinh, bom ngoai OFF" \
  --purge-method "khong xa bang bom"
```

1. `MONITOR`: chờ tín hiệu bớt trôi, gõ `start` rồi Enter. Từ đây BASELINE chạy 30 giây.
2. `WAIT_EXPOSURE`: không đổi điều kiện; gõ `mark doi chung khong dua mau` rồi `expose`. EXPOSURE chạy 60 giây.
3. `WAIT_RECOVERY`: gõ `mark doi chung khong thao tac xa` rồi `recover`. RECOVERY chạy 60 giây.
4. `WAIT_FINISH`: gõ `finish`. Khi được hỏi tên, nhập `name doi_chung_khong_bom_01`; ghi `notes ...` về thời điểm, tình trạng nguồn bơm OFF, buồng, vị trí, nhiệt/ẩm và mọi bất thường, hoặc dùng `skip` theo hướng dẫn trên màn hình.
5. Nếu ứng dụng hỏi lượt tiếp, gõ `quit` khi muốn kết thúc. Đọc đường dẫn thư mục lượt mà chương trình in ra.

Trong lúc chạy có thể gõ `status`, `help`, `mark <ghi chú>`; `abort` hoặc Ctrl+C sẽ dừng lượt và thường giữ trạng thái `ABORTED`. Đừng dùng chúng như cách kết thúc lượt bình thường.

## 5. Thu mẫu bằng ống — sau khi nguồn bơm được kiểm tra

Giữ nắp buồng kín. Xác định **đầu hút**, **đầu xả**, chiều khí đi qua buồng và đường cấp khí nền. Không có van ba chiều nên đổi nguồn khí bằng tay trong `WAIT_EXPOSURE` và `WAIT_RECOVERY`; không giả định khí đổi tức thì ở đầu cảm biến.

1. Trước `start`, bố trí ống lấy khí nền theo cách bạn muốn thử. Nếu bật bơm ngoài, xác nhận luồng khí, gõ `mark bom_ngoai_ON khi nen` khi chương trình đang ghi, chờ nền bớt trôi rồi `start`.
2. Hết BASELINE, ở `WAIT_EXPOSURE`, chuyển đầu hút sang nguồn mẫu. Gõ `mark chuyen_ong_sang_mau bom_ngoai_ON` (sửa ON/OFF đúng thực tế), sau đó `expose`. Ghi chú nếu chuyển ống mất nhiều thời gian.
3. Hết EXPOSURE, ở `WAIT_RECOVERY`, rời nguồn mẫu, đưa đầu hút về khí nền hoặc nguồn xả đã chọn. Gõ `mark chuyen_ong_ve_khi_nen`; nếu đổi trạng thái bơm, ghi thêm `mark bom_ngoai_OFF` hoặc `mark bom_ngoai_ON`. Sau đó `recover`.
4. Sau 60 giây RECOVERY, nếu đường gas/MQ chưa về gần mức trước khi lấy mẫu, dùng `extend 30` hoặc `extend 60` nếu CLI đang hỗ trợ; ghi lại lý do. Kết thúc bằng `finish`, đặt tên và notes.

Với mỗi lượt, giữ các yếu tố có thể cố định như vị trí ống, vị trí mẫu, độ kín, trạng thái bơm và thời gian. Không thay đổi cách lấy mẫu giữa hai lượt rồi coi độ lớn tín hiệu là so sánh trực tiếp.

## 6. Thu bằng cách mở nắp buồng

Có thể làm lượt này với bơm ngoài OFF; cách này phù hợp để thử toàn bộ chương trình trước khi dùng nguồn 12 V. Cần ghi rõ nắp mở trong bao lâu vì độ ẩm/nhiệt/khí phòng cùng đi vào buồng.

1. Đóng buồng ở trạng thái nền đã chọn, bơm OFF, chờ tín hiệu bớt trôi. Trong MONITOR gõ `mark bom_ngoai_OFF nap_dong` rồi `start`.
2. Đợi BASELINE kết thúc. Ở `WAIT_EXPOSURE`, mở nắp, đưa mẫu vào vị trí đã chọn, đóng nắp (hoặc để mở nếu đó là phép thử bạn chủ đích). Gõ `mark mo_nap_dua_mau_dong_nap` và `expose` **sau khi** thao tác xong.
3. Đợi EXPOSURE kết thúc. Ở `WAIT_RECOVERY`, mở nắp, bỏ mẫu ra, đóng buồng/xả theo cách đã chọn. Gõ `mark mo_nap_bo_mau_dong_nap`; nếu bật bơm ngoài sau khi đã kiểm tra nguồn, ghi riêng `mark bom_ngoai_ON`; gõ `recover` sau khi thao tác hoàn tất.
4. Ở `WAIT_FINISH`, `extend 30/60` nếu cần tiếp tục quan sát, rồi `finish`, nhập `name ...`, `notes ...`.

Nếu khí mẫu có thể gây kích ứng hoặc không rõ thành phần, đừng đưa trực tiếp vào buồng trong phòng kín. Các mẫu mùi cơ thể/quần áo cần bảo quản và thao tác vệ sinh nhất quán; đây là thăm dò tín hiệu, không đánh giá sức khỏe từ MQ/BME.

## 7. Tên, ghi chú và nhật ký tối thiểu

Tên sau lượt nên dễ tìm và không chứa thông tin cá nhân nhạy cảm, ví dụ `name ao_mac_sang_ngay01_lan01`. Hãy ghi vào `notes`:

| Mục | Ví dụ |
| --- | --- |
| Mẫu | Áo cotton đã mặc 3 giờ; vị trí lấy khí ở cổ áo |
| Cách lấy | Mở nắp 12 giây rồi đóng; hoặc ống hút cách mẫu 2 cm |
| Bơm ngoài | OFF toàn lượt; hoặc ON từ 10:45, OFF lúc WAIT_RECOVERY |
| Điều kiện | Buồng khô/ẩm, vị trí đặt, thông gió, nắng/nguồn nhiệt gần đó |
| Bất thường | Nền gas trôi, nắp hở, tuột ống, mất một kênh, sai thao tác |

Lệnh `mark ...` nên ghi **ngay thời điểm sự kiện**. `notes ...` là tường thuật bổ sung sau lượt; đồng hồ ghi sự kiện của `mark` mới giúp đối chiếu với đường tín hiệu.

## 8. Kiểm tra sau mỗi lượt

Ứng dụng sẽ in thư mục lượt dưới `data/exploration/YYYY-MM-DD/...`. Kiểm tra thư mục thật vừa được in; sau đó phân tích lại bằng đường dẫn đó, ví dụ:

```bash
.venv/bin/python -m robonose analyze \
  "data/exploration/YYYY-MM-DD/THU_MUC_LUOT"
```

Xác nhận có CSV thô, nhật ký sự kiện, metadata, summary/đồ thị theo định dạng của phiên bản CLI hiện tại. Xem trạng thái `COMPLETE`; nếu `ABORTED` hoặc `ERROR`, giữ lại file và đọc lý do. Kiểm tra số dòng CSV tăng qua MONITOR và các pha `WAIT_*`, timestamp tăng, và không có lỗ hổng dài bất thường. Trên đồ thị, phân biệt các pha, chú ý độ trôi của nền, nhiệt/ẩm, mức trở về sau recovery và cờ giá trị thiếu. Không coi thay đổi gas là do mùi mẫu nếu lượt đối chứng cũng trôi tương tự.

Nguyên tắc chấp nhận **về chương trình**: một lượt đủ 30–60–60 giây, không bị chặn khi chờ nhập; mỗi hàng có thời gian/pha và dữ liệu cảm biến hoặc null kèm lý do; hoàn thành/thoát sớm giữ dữ liệu; tên lượt không ghi đè; `--pump-disabled` không phát lệnh GPIO. Nguyên tắc chấp nhận **về phép đo**: tình trạng khí nền và thao tác được ghi trung thực; lượt trôi mạnh vẫn hữu ích để chẩn đoán nhưng chưa dùng để khẳng định mùi.

## 9. Khi cần xử lý sự cố

| Hiện tượng | Bước xử lý |
| --- | --- |
| Gas tăng nhanh, báo `ĐANG TRÔI` | Chờ thêm ở MONITOR, kiểm tra nhiệt/ẩm và vị trí BME, chạy lượt đối chứng. Ghi rõ lượt có nền trôi. |
| BME lỗi nhưng MQ vẫn có số | Giữ file; kiểm tra dây I2C/nguồn sau lượt. Không thay null bằng 0. |
| MQ đứng im hoặc sát 0 | Kiểm tra nguồn MQ, GND chung, đúng A0/A1 và tỷ lệ chia áp; đối chiếu ADC với AO đo thực tế. |
| `pump command=DISABLED` dù bơm ngoài chạy | Bình thường trong chế độ này. Ghi `mark bom_ngoai_ON` và notes đúng tình trạng vật lý. |
| Lỡ Enter sai pha | Gõ `help`/`status`, xem pha hiện tại; không sửa CSV bằng tay. Ghi `mark` về thao tác thực và tiếp tục khi có thể. |
| Mất điện/thoát sớm | Giữ nguyên thư mục lượt, kiểm tra metadata/events/CSV; phân tích lượt đó như `ABORTED` hoặc `ERROR`, thu lại lượt mới. |

Sau khi thu xong vài lượt, sao lưu cả thư mục lượt nguyên vẹn. Gửi Codex đường dẫn một lượt đối chứng và một lượt có mẫu, cùng nhận xét về bơm/nắp/ống; yêu cầu đối chiếu event, đồ thị và chất lượng dữ liệu trước khi sửa ngưỡng hay rút kết luận.

## Tài liệu đối chiếu

- [Raspberry Pi: phần cứng và GPIO](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html).
- [Bosch BME688 datasheet](https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme688-ds000.pdf): phân biệt trạng thái phép đo heater với xu hướng ổn định của môi trường/đường gas.

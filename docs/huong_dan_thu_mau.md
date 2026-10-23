# Hướng dẫn thu mẫu thăm dò RoboNose v1.0

Tài liệu dùng CLI hiện tại trong repo /home/pi/robonosev1.0.
Pi chỉ đọc BME688 và ADS1115, **không điều khiển bơm**.
Mọi lệnh monitor/collect bên dưới có --pump-disabled. Không chạy pump-test
hoặc enable-pump. Nếu dùng bơm ngoài, bạn tự bật/tắt nguồn riêng; phần mềm chỉ
biết thao tác bạn khai báo, không đo bơm chạy hay lưu lượng. Thu không bơm cũng được.

## 1. Chuẩn bị và kiểm tra

- Chuẩn bị buồng, mẫu, đường ống hoặc cách mở nắp theo cách lấy khí bạn chọn.
  Ghi tình trạng buồng/nắp và cách xả thực tế. Chưa có van ba chiều/lọc than;
  chương trình không tự xả hoặc chuyển đường khí.
- Kiểm tra dây/nguồn BME688, ADS1115, MQ135 A0 và MQ3 A1 theo phần cứng thực tế.
  Địa chỉ mặc định BME 0x77, ADS 0x48; chỉnh config nếu khác.
- MQ voltage là điện áp tại ADS. Nếu chia áp 10 kΩ/10 kΩ đã xác nhận, thêm
  mq135_divider_factor=2.0 và mq3_divider_factor=2.0 trong [hardware], ghi
  divider_description tương ứng là đã xác nhận. Chưa xác nhận thì giữ factor
  không đặt: AO estimate trống. Gain không thay thế giới hạn điện áp chân ADS;
  điện áp/nguồn/chia áp phải được kiểm tra trên máy thật.
- Chọn output đủ dung lượng, sao lưu lượt cũ. Không sửa CSV để bổ sung mẫu mất.
- Mô tả mặc định không lưu tên người, địa chỉ, thông tin sức khỏe hay tài khoản.
  person_code là tùy chọn; không cần điền để thu.

Doctor chỉ kiểm tra môi trường/cấu hình, không mở I2C/GPIO và không chứng minh cảm biến hoạt động:

~~~bash
cd /home/pi/robonosev1.0
.venv/bin/python -m robonose doctor --pump-disabled --config config.example.toml
~~~

Kiểm tra cảm biến thật, bơm GPIO disabled:

~~~bash
.venv/bin/python -m robonose monitor --hardware --pump-disabled   --config config.example.toml --display-interval 1
~~~

Xem gas Ω, T °C, H %RH, P hPa, MQ V, status và flags; dùng status/help.
quit kết thúc monitor và giữ log. Không gõ start nếu chỉ muốn kiểm tra:
start trong monitor mở lượt BASELINE trên cùng reader/heater đang chạy.

MONITOR đã ghi liên tục. Đánh giá ổn định xét slope/range gas/T/H, độ phủ cửa sổ,
mẫu hợp lệ, gap và độ mới; [stability] cấu hình được, mặc định cửa sổ 30 s.
Đây không phải warmup bắt buộc: bạn tự chọn lúc bắt đầu. Baseline không thay warmup.

Gas trôi mạnh hoặc T khoảng 39°C: đọc cảnh báo, ghi điều kiện thực tế. **heater_stable=True
không có nghĩa nền gas ổn định**. Có thể chờ thêm hoặc chủ động start; phần mềm
giữ cờ/lý do, không kết luận mùi. Cảnh báo T cao không tự bù nhiệt hay tìm nguyên nhân.

Màn hình GPIO pump command=DISABLED chỉ nói Pi không điều khiển bơm.
Bơm ngoài=unknown nghĩa chưa khai báo. DISABLED không đồng nghĩa bơm ngoài OFF.

## 2. Lượt đối chứng 30–60–60 không mẫu, không bơm

Lượt này khảo sát độ trôi và điều kiện nền. Giữ phương pháp/nắp/điều kiện đúng
như khai báo; không đưa mẫu trong EXPOSURE. Nếu mở nắp/đổi ống, đánh dấu và ghi notes.

~~~bash
.venv/bin/python -m robonose collect --hardware --pump-disabled   --config config.example.toml --baseline 30 --exposure 60 --recovery 60   --external-pump-state not-used   --sample-description "đối chứng không mẫu, không bơm"   --sampling-method "không đưa mẫu"   --purge-method "không thay đổi điều kiện" --lid-state "đóng"
~~~

Chương trình in đường dẫn session log và lượt. Thư mục giờ + run_id được tạo trước
đặt tên, dữ liệu ghi ngay.

| Pha | Bạn làm gì | Chương trình |
|---|---|---|
| MONITOR | Theo dõi/warmup, mark điều kiện, start khi muốn | Đọc/lưu liên tục, chưa tính baseline |
| BASELINE | Giữ điều kiện nền, không expose sớm | Đọc/lưu 30 s, kết thúc theo monotonic |
| WAIT_EXPOSURE | mark mốc đối chứng, expose | Vẫn đọc/lưu riêng nhãn WAIT |
| EXPOSURE | Không đưa mẫu ở lượt đối chứng | Đọc/lưu 60 s |
| WAIT_RECOVERY | mark không có mẫu để bỏ, recover | Vẫn đọc/lưu riêng nhãn WAIT |
| RECOVERY | Giữ/ghi điều kiện thực tế | Đọc/lưu 60 s |
| WAIT_FINISH | finish hoặc extend 30/60/thời lượng khác | Vẫn đọc/lưu, chờ quyết định |
| WAIT_NAME/WAIT_NOTES | name/notes hoặc skip | Session log vẫn đọc/lưu |
| BETWEEN_RUNS | next hoặc quit | Reader hoạt động, session vẫn ghi |

Gõ **từng bước**, không dán cả danh sách cùng lúc:

1. MONITOR: "mark đối chứng không bơm; nắp đóng", rồi "start".
2. Đợi Pha WAIT_EXPOSURE: "mark bắt đầu đoạn đối chứng không mẫu", rồi "expose".
3. Đợi Pha WAIT_RECOVERY: "mark bắt đầu hồi phục đối chứng", rồi "recover".
4. Đợi Pha WAIT_FINISH: "finish", hoặc "extend 30", "extend 60", "extend 90.5".
   Hết extension lại WAIT_FINISH; finish khi muốn kết thúc.
5. Hỏi tên: "name doi_chung_khong_bom_20261003_A".
6. Hỏi notes: "notes Không mẫu; không bơm; nắp đóng; ghi nhận độ trôi gas/T/H".
7. "next" mở MONITOR lượt mới giữ reader/heater; "quit" kết thúc phiên.

Dấu ngoặc kép ở ví dụ terminal chỉ phân biệt nội dung lệnh; **không gõ dấu ngoặc**.
finish trước WAIT_FINISH lưu ABORTED. Không mặc định RECOVERY 60 s đã sạch.

## 3. Lượt đưa khí qua ống

Không có lịch bơm cố định. Bạn tự chọn có bơm hay không, chạy liên tục hay đổi theo
thao tác; ghi trung thực. Để so sánh, lưu cách lấy/xả, đổi đường khí và điều kiện
nền. Đổi bơm/đường khí cũng có thể đổi tín hiệu, không tự quy thành tác động mùi.

~~~bash
.venv/bin/python -m robonose collect --hardware --pump-disabled   --config config.example.toml --baseline 30 --exposure 60 --recovery 60   --external-pump-state unknown   --sample-description "mẫu áo A" --source "vật liệu mẫu tự chọn"   --sampling-method "đưa khí qua ống"   --purge-method "xả thủ công theo bố trí thực tế" --lid-state "đóng"
~~~

- MONITOR: "mark đường ống nền đã nối; nắp đóng". Nếu đã tự bật nguồn ngoài,
  gõ "external-pump on đã tự bật nguồn riêng; dùng đường khí nền".
  Không dùng bơm: "external-pump not-used không dùng bơm trong lượt".
- start khi muốn, giữ điều kiện nền đã khai báo trong BASELINE 30 s.
- WAIT_EXPOSURE: đổi ống/đưa mẫu thực tế, "mark đổi ống sang mẫu áo A", rồi expose
  gần cùng thời điểm bắt đầu tiếp xúc.
- Bật/tắt nguồn bất kỳ lúc nào: "external-pump on bật nguồn riêng" hoặc
  "external-pump off tắt nguồn riêng". Chỉ là khai báo, không GPIO.
- WAIT_RECOVERY: bỏ mẫu/chuyển đường khí/xả, "mark bỏ mẫu; đổi ống sang khí hồi phục",
  rồi recover.
- WAIT_FINISH: extend hoặc finish, đặt tên/notes. Bạn tự tắt bơm khi cần;
  finish/abort/quit không tắt nguồn ngoài.

## 4. Lượt mở nắp buồng

Bạn chọn đặt mẫu/áo/bông hoặc cách tiếp xúc phù hợp bố trí. Không cần class/số trial.
Lượt mở nắp không bơm:

~~~bash
.venv/bin/python -m robonose collect --hardware --pump-disabled   --config config.example.toml --baseline 30 --exposure 60 --recovery 60   --external-pump-state not-used   --sample-description "mẫu tự chọn A"   --sampling-method "mở nắp buồng, đưa mẫu bằng tay"   --purge-method "bỏ mẫu và xả bằng thao tác tay" --lid-state "đóng lúc bắt đầu"
~~~

- MONITOR/BASELINE: ghi điều kiện thực tế, start khi muốn.
- WAIT_EXPOSURE: "mark mở nắp, đưa mẫu A", thao tác thực tế và expose gần cùng lúc.
  Nếu đóng nắp: "mark đóng nắp sau đưa mẫu".
- EXPOSURE: ghi thay đổi nắp/vị trí/điều kiện bằng mark.
- WAIT_RECOVERY: "mark mở nắp, bỏ mẫu A; bắt đầu xả thủ công", rồi recover.
  "mark đóng nắp sau xả" nếu thực sự đóng.
- Sau 60 s recovery, finish hoặc extend. Notes ghi thao tác lệch thời điểm,
  phương pháp thực tế, baseline chưa ổn định nếu có.

lid_state là mô tả người dùng, không có cảm biến nắp. Đổi lúc thu dùng mark;
không có van/chuyển khí tự động.

## 5. Lệnh, tên và notes

| Lệnh | Ý nghĩa |
|---|---|
| help, status | Lệnh/pha/giá trị/xu hướng |
| durations 30 60 60 | Đổi trước baseline hoặc giữa lượt |
| info sampling_method văn bản | Đổi mô tả trước baseline |
| info lid_state văn bản | Khai báo nắp trước baseline |
| mark văn bản | Ghi nguyên văn thao tác |
| external-pump on/off/not-used/unknown ghi chú | Khai báo nguồn ngoài, không GPIO |
| start, expose, recover | Bắt đầu đúng pha khi nhận lệnh |
| extend 30 / extend 60 / extend 90.5 | Thêm RECOVERY từ WAIT_FINISH |
| finish | COMPLETE ở WAIT_FINISH; dùng sớm thì ABORTED |
| abort | Dừng lượt sớm, giữ dữ liệu và hỏi tên/notes |
| name tên | Tên sau lượt, giữ run_id, không ghi đè |
| notes văn bản | Ghi chú sau lượt |
| skip hoặc Enter trống | Bỏ qua riêng từng câu hỏi tên/notes |
| next | Lượt mới cùng phiên |
| quit | Kết thúc; lượt đang dở ABORTED |

**Mốc mark/external-pump là lúc nhận Enter**, không phải lúc bắt đầu gõ hoặc phép
đo thời điểm vật lý. Gõ gần lúc thao tác, notes ghi sai lệch sau thu. Vòng đọc
vẫn chạy khi gõ chậm; terminal giữ dòng nhập khi trạng thái mới xuất hiện.

mark không tự đoán ON/OFF: "mark bật bơm ngoài" lưu văn bản nhưng trạng thái có
cấu trúc vẫn giữ khai báo trước. external-pump dùng khi muốn raw/meta có on/off.
unknown chưa biết; not-used là khai báo không dùng. Trạng thái khai báo giữ
giữa lượt đến khi bạn đổi; xem status trước next/start.

Tên không nhận dạng cá nhân:
- name mau_co_the_A_tham_do_20261003
- name ao_cotton_A_mo_nap_20261003
- name ao_A_qua_ong_20261003

Notes ví dụ, chỉnh đúng thực tế:
- notes Mẫu A; tiếp xúc qua vật liệu tự chọn; không bơm; nắp mở lúc tiếp xúc; nền gas đang trôi.
- notes Áo cotton A; khí qua ống; bơm ngoài bật thủ công, mốc trong events; không lưu tên người.
- notes Mẫu áo A; mở nắp đưa/bỏ mẫu; recovery thêm 60 s; T BME khoảng 39 C; chưa quy tín hiệu cho mẫu.

Tên trùng vẫn là thư mục riêng do UUID khác. Tên làm sạch không đi ra ngoài output,
metadata giữ tên gốc. Đổi tên lỗi giữ đường dẫn cũ/báo lỗi. Không đổi tên hoặc di
chuyển thư mục đang thu bằng công cụ khác.

## 6. Đọc kết quả

Mỗi lượt: raw.csv, events.csv, metadata.json, summary.json, signals.png,
normalized.png dưới data/exploration/ngày. Session log toàn phiên ghi cả đặt
tên/giữa lượt; không ghép raw session và raw lượt thành mẫu độc lập.

- Raw: ISO Asia/Ho_Chi_Minh; elapsed_s/phase_elapsed_s monotonic; phase; thời gian
  vòng và từng thiết bị; BME gas/T/H/P/flags; ADC count/voltage; AO estimate nếu
  factor xác nhận; lỗi/độ mới và khai báo bơm ngoài.
- Metadata: cấu hình yêu cầu/áp dụng, driver, phương pháp/thời lượng/chất lượng,
  tên/notes/status. baseline_started_without_stability là bắt đầu khi cửa sổ
  chưa ổn định/đủ quan sát, không đồng nghĩa lỗi phần mềm.
- Summary: mẫu hợp lệ/drift/slope/extrema/delta/AUC/hồi phục. measurement_quality
  là cảnh báo, không phân loại mùi.
- signals.png giữ đơn vị gốc; normalized.png % theo nền, tách raw.
  WAIT có nhãn riêng, không cộng vào pha chính. AUC không nối qua lỗi/gap hoặc
  hai đoạn recovery cách nhau bằng WAIT.
- Null/ô trống: chưa đọc được hoặc chưa đủ điều kiện tính, xem lý do; không thay 0.
  Giá trị flag invalid vẫn trong raw. Nền gần 0 thì % null; thiếu nền/pha thì
  thống kê liên quan null.
- COMPLETE chỉ là hoàn thành pipeline, không bảo đảm nền ổn định/buồng sạch/ppm/
  nhận dạng mùi. Gas trôi mạnh/T 39°C cần đọc cùng đối chứng, nhiệt/ẩm/events.

Phân tích lại bằng thư mục lượt **đã in trên terminal**:

~~~bash
.venv/bin/python -m robonose analyze "data/exploration/YYYY-MM-DD/THU_MUC_LUOT"
~~~

analyze không mở GPIO/I2C, không cần --hardware/--pump-disabled, không cần desktop.
Nó cập nhật summary/PNG, không sửa raw/events/metadata. Không analyze lúc đang thu.
Muốn giữ cả summary/PNG cũ, phân tích một bản sao thư mục ở nơi khác trong repo.

## 7. Thoát sớm và sự cố

- abort/finish sớm: ABORTED, giữ dữ liệu; đặt tên/notes, next thu lại.
- Ctrl+C/EOF (Ctrl+D dòng trống): kết thúc phiên; lượt dở ABORTED. Hủy nhập tên
  sau COMPLETE vẫn giữ COMPLETE bằng tên tự động/đã khai báo.
- Lỗi từng sensor: lỗi/null/events; kênh còn đọc được vẫn ghi. Lỗi worker không
  phục hồi hoặc lỗi đóng/sync: ERROR, xem end_reason. Cố đóng cả raw/events và
  giữ metadata nếu filesystem cho phép.
- ABORTED/ERROR giữ để chẩn đoán, không coi là lượt hoàn chỉnh. Ghi bất thường,
  thu lượt mới; xem status/error/fresh và gap.
- Mất điện/SIGKILL/đĩa hỏng có thể để PARTIAL; không hứa bảo toàn mọi dữ liệu.
  Sao lưu file còn lại, không tự đổi trạng thái thành COMPLETE.
- Tất cả cách thoát **không tắt bơm ngoài**; bạn tự tắt nguồn riêng. Ngay cả khi
  đã ghi sự kiện, đó vẫn là khai báo, không phản hồi đo được.

## 8. Tập bằng sim, không thiết bị

~~~bash
.venv/bin/python -m robonose collect --sim --pump-disabled   --baseline 2 --exposure 2 --recovery 2 --external-pump-state not-used
.venv/bin/python scripts/verify_interactive.py
.venv/bin/python -m pytest -q -k 'not pump_test'
~~~

Sim tương tác dùng cùng start/expose/recover/finish/name/notes. Script tự gửi
lệnh ngắn, không --auto, report/log mới và không GPIO. Khai báo bơm ngoài chỉ
diễn tập nhật ký. Bộ test loại pump_test theo phạm vi hiện tại.

Chỉ bạn xác nhận trên hardware: nguồn/điện áp/chia áp/kênh, warmup, ảnh hưởng
nhiệt/ẩm, khí đến buồng, nắp/ống và bơm ngoài thực sự chạy/tắt.
Sim/mock không chứng minh các điều đó.

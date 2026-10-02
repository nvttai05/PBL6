RoboNose v1.0 — Hướng dẫn dùng Codex trên Raspberry Pi

Soạn ngày 02/10/2026. Đây là bộ hướng dẫn và prompt; chương trình chưa được triển khai trên Pi bởi cuộc trò chuyện này. Các bước triển khai được thực hiện bởi Codex đang chạy trong repo trên Pi.

1. Mở repo đúng trên Pi

Kết nối VS Code Remote SSH, mở thư mục repo đã setup. Terminal cần hiển thị phiên làm việc trên Pi. Chạy:

```bash
pwd
git status --short --branch
git remote -v
```

Nếu chưa ở Git repo, mở đúng thư mục đã tạo/clone. Không init một repo mới trong thư mục bất kỳ. Nếu có code chưa commit từ trước, chọn các file code đã kiểm tra và tạo checkpoint bằng Source Control trước khi triển khai. Giữ data, .venv và secrets ngoài commit.

2. Mở Codex

Trong terminal của Pi, ở chính repo:

```bash
codex --sandbox workspace-write --ask-for-approval on-request
```

Chế độ này cho phép đọc/sửa/chạy lệnh trong workspace, các thao tác mạng hoặc ngoài phạm vi có thể cần approval. Khi có yêu cầu cài thư viện, kiểm tra đó là lệnh cài vào môi trường dự án. Thử phần cứng bằng lệnh bạn tự chạy ở terminal thường.

Nếu bạn dùng extension Codex thay vì CLI, mở biểu tượng Codex trong VS Code đang kết nối Pi; prompt bên dưới dùng được tương tự. Xác nhận repo/host bằng prompt khảo sát. Chỉ chọn một giao diện để làm lượt này.

3. Gửi prompt khảo sát

Dán phần giữa hai đường phân cách dưới đây vào Codex, không dán vào shell. Chờ phản hồi hoàn tất. Không cần gửi lại toàn bộ lịch sử ChatGPT.

---

Bạn đang làm việc trực tiếp trên Raspberry Pi trong repo RoboNose của tôi.

Ở bước này chỉ khảo sát, chưa sửa file hay cài đặt:
- Xác định thư mục hiện tại, Git repo, nhánh, trạng thái thay đổi và đọc AGENTS.md nếu có.
- Xem cấu trúc dự án, README, cấu hình và code hiện có; repo trống thì nói rõ.
- Kiểm tra Python, hệ điều hành, kiến trúc CPU, môi trường ảo và thư viện cảm biến hiện có.
- Xác định phần có thể tái sử dụng cho RoboNose v1.0.
- Phần cứng: Pi 4, BME688, MQ135 qua ADS1115 A0, MQ3 qua ADS1115 A1, buồng thủy tinh, bơm 12V qua MOSFET. Chưa dùng van ba chiều hoặc lọc than.
- GPIO điều khiển bơm và mức kích MOSFET chưa xác nhận. Chưa truy cập GPIO/I2C hoặc chạy bơm.
- Không đọc khóa SSH, token hay nội dung đăng nhập.

Trả lời bằng tiếng Việt: môi trường thực tế, hiện trạng repo, kiến trúc tối thiểu đề xuất, dependency còn thiếu và thông tin phần cứng còn cần xác nhận. Không giả định code cũ còn tồn tại.

---

4. Tạo nhánh triển khai

Mở terminal thứ hai trong cùng repo, chạy:

```bash
git switch -c feat/robonose-v1-pilot
```

Nếu đã có nhánh đó thì chuyển sang bằng git switch feat/robonose-v1-pilot. Nếu repo đã có công việc riêng trên nhánh khác, giữ checkpoint trước khi chuyển. Terminal Codex vẫn phải làm việc trong cùng repo.

5. Gửi prompt xây dựng

Dán toàn bộ prompt dưới đây trong cùng phiên Codex. Cho Codex tự xử lý việc đọc file, viết code và sửa lỗi test trong phạm vi đã nêu. GPIO chưa biết không cản việc hoàn thành phần mềm và mô phỏng.

---

Hãy triển khai hoàn chỉnh công cụ thu thử RoboNose v1.0 trong repo hiện tại, dựa trên kết quả khảo sát vừa rồi. Thực sự viết file, chạy kiểm thử mô phỏng và sửa lỗi đến khi các kiểm tra phù hợp đạt. Đây là công cụ khảo sát dữ liệu, chưa cần ML, phân loại mùi hoặc manifest dataset.

1. Phạm vi làm việc
- Đọc và tuân thủ hướng dẫn repo; bảo toàn thay đổi có sẵn của tôi.
- Nếu repo có code phù hợp thì tái sử dụng hoặc bổ sung, không dựng lại toàn bộ một cách máy móc.
- Tạo/cập nhật AGENTS.md ngắn gọn cho ngữ cảnh và quy tắc RoboNose, cùng README tiếng Việt và tài liệu schema dữ liệu.
- Chỉ chỉnh sửa trong repo. Dùng môi trường ảo của dự án; có thể tạo .venv và cài dependency cần thiết vào đó.
- Không tự sửa hệ điều hành, cấu hình SSH/Wi-Fi, cài package toàn hệ thống hoặc dùng sudo. Nếu thiếu package hệ thống, ghi chính xác lệnh và lý do để tôi thực hiện.
- Không tự commit/push, không xóa dữ liệu thu, không reset Git hoặc ghi đè file của tôi.
- Chế độ mặc định là mô phỏng. Trong quá trình triển khai chỉ chạy mô phỏng, không truy cập I2C/GPIO hay chạy bơm thật.

2. Phần cứng và cấu hình
- Raspberry Pi 4; BME688 qua I2C; ADS1115 đọc MQ135 ở A0, MQ3 ở A1.
- Địa chỉ trước đây là BME688 0x77, ADS1115 0x48, nhưng phải cấu hình được.
- Thông số khởi điểm: BME heater 320°C/150 ms, oversampling T×8/H×2/P×4; ADS gain=1, data_rate=128 SPS. Kiểm tra hỗ trợ thực tế và gọi đúng API/constant của driver, ghi cấu hình đã áp dụng vào metadata.
- Chọn driver hỗ trợ đúng BME688, kiểm tra đơn vị và khả năng đọc gas/status; không đánh đồng các biến thể cảm biến.
- Tần suất ghi mặc định 1 Hz, cấu hình được. Phân biệt tần suất ghi với SPS nội bộ của ADC.
- Pump mặc định disabled, GPIO và cực tính kích chưa xác nhận. Để cấu hình rõ ràng; không tự đoán chân hoặc mức HIGH/LOW bật bơm.
- Chế độ pump-disabled và sim không khởi tạo GPIO. Khi sau này enable pump, yêu cầu đủ cấu hình đã xác nhận.
- Chỉ điều khiển bật/tắt. Trạng thái lưu là lệnh đã gửi, không giả định đo được lưu lượng hoặc xác nhận bơm chạy.
- Nếu có chia áp, lưu hệ số đã biết và điện áp tại ADS; chỉ suy ra AO khi cấu hình thực sự có đủ thông tin.

3. Luồng thu và thao tác
- MONITOR/warmup: theo dõi và lưu dữ liệu đến khi người dùng yêu cầu bắt đầu; lưu thời gian đã chạy cảm biến. Baseline không thay thế warmup.
- BASELINE 30 s -> WAIT_EXPOSURE -> EXPOSURE 60 s -> WAIT_RECOVERY -> RECOVERY 60 s.
- Người dùng chủ động đánh dấu bắt đầu tiếp xúc và hồi phục bằng lệnh terminal, cùng lúc thao tác thực tế.
- Các khoảng chờ vẫn ghi dữ liệu với nhãn riêng, không cộng vào thời lượng pha chính.
- Sau hồi phục cho chọn kết thúc hoặc kéo dài thêm 30/60 s hay thời lượng tự nhập; ghi riêng thời lượng dự kiến/thực tế và các lần kéo dài. Nếu chờ quyết định thì tiếp tục ghi với nhãn phù hợp.
- Cho đổi thời lượng trước mỗi lượt. Bộ đếm dựa trên monotonic time, không dựa trên số dòng hoặc giờ hệ thống.
- Người dùng đưa mẫu bằng ống, mở nắp, đặt áo/bông hay bất kỳ cách nào. Thông tin mẫu và cách thu là văn bản tự do, không bắt chọn class hoặc số trial.
- Xả/hồi phục là thao tác vật lý người dùng thực hiện, chương trình không mặc định tự chuyển đường khí.
- Trong khi thu có lệnh bật/tắt bơm khi đã enable, mark ghi chú/sự kiện, xem trạng thái và kết thúc sớm.
- Thiết kế nhập lệnh không chặn vòng đọc/lưu cảm biến. Hiển thị pha, thời gian còn lại, giá trị hiện tại và trợ giúp lệnh rõ ràng.
- Có thể thu nhiều lượt trong cùng phiên; giữ cảm biến hoạt động giữa các lượt, không khởi tạo lại heater chỉ để chuyển pha hoặc đổi tên.
- Thu xong mới hỏi tên file và ghi chú; có thể bỏ qua để dùng tên tự động.

4. Dữ liệu gốc
- Mỗi lượt có run_id duy nhất, số thứ tự dòng, thời gian ISO có múi giờ Asia/Ho_Chi_Minh, elapsed_s, phase_elapsed_s và phase.
- BME688: temperature_c, humidity_pct, pressure_hpa, gas_resistance_ohm; lưu gas_valid, heater_stable, new_data hoặc trạng thái tương đương thực sự đọc được.
- MQ135/MQ3: ADC count gốc và điện áp ở đầu vào ADS1115. ADC count và voltage của một kênh phải xuất phát từ cùng phép chuyển đổi, không gọi hai lần đọc khác nhau rồi ghép.
- Lưu thời điểm đọc từng thiết bị/kênh và thời gian giữa các vòng đọc để thể hiện độ lệch khi đọc tuần tự.
- Lưu lệnh bơm, trạng thái đọc/lỗi từng cảm biến, thông tin fresh/stale và trễ đọc.
- Lưu thêm trường driver thực sự cung cấp nếu hữu ích; thông tin cố định như cấu hình, phiên bản driver, hệ số hiệu chuẩn được cung cấp thì lưu một lần trong metadata.
- Giá trị không đọc được để trống/null và ghi lý do. Không điền 0 hoặc lấy mẫu cũ giả làm dữ liệu mới.
- Dữ liệu đọc được nhưng gas flag không hợp lệ vẫn giữ cùng flag; thống kê dùng quy tắc lọc minh bạch.
- Không tự suy ra ppm, CO2, IAQ hoặc nồng độ mùi khi chưa có phương pháp/library/hiệu chuẩn tương ứng.
- Giữ đủ độ chính xác khi lưu; CSV gốc không bị chuẩn hóa, làm mượt hoặc chỉnh sửa trong bước phân tích.

5. Lưu và đặt tên
- Tạo bộ file bằng tên ngày giờ + run_id trước khi thu, ghi dữ liệu tăng dần, flush thường xuyên và có cơ chế đồng bộ xuống đĩa hợp lý.
- Lưu theo ngày trong data/exploration; dữ liệu sim ở data/simulation để nhận diện rõ.
- Sau lượt thu nhận tên và ghi chú, tạo tên file hợp lệ, bảo toàn tên gốc trong metadata, tránh ghi đè hoặc đi ra ngoài thư mục output.
- Đổi tên/finalize lỗi vẫn giữ dữ liệu và báo đường dẫn đang có. run_id không đổi khi đổi tên.
- Mỗi lượt có CSV raw, metadata JSON, events CSV, summary JSON và PNG đồ thị. Có thể dùng thư mục riêng mỗi lượt để quản lý bộ file nhất quán.
- Metadata gồm loại mẫu/mã người tùy chọn, nguồn mẫu, cách lấy khí, cách xả, trạng thái nắp người dùng khai báo, khoảng cách nếu biết, ghi chú, địa chỉ I2C/kênh ADS, cấu hình, phiên bản chương trình/driver, giờ bắt đầu/kết thúc, thời lượng và trạng thái hoàn thành.
- Events có cùng cơ sở thời gian với raw: chuyển pha, pump command, marker, lỗi và kết thúc sớm.
- Khi Ctrl+C, exception hoặc SIGTERM có thể xử lý: cố gắng đưa pump OFF nếu được enable, đóng file, giữ dữ liệu và đánh dấu COMPLETE/ABORTED/ERROR/PARTIAL phù hợp.
- Không coi việc nhập tên bị hủy sau khi thu hoàn tất là lỗi thu; vẫn giữ tên tự động.
- Không hứa bảo toàn mọi dữ liệu khi mất điện hoặc process bị kill cưỡng bức.
- .gitignore loại .venv, output dữ liệu, cache và thông tin bí mật; có thể commit fixture mô phỏng nhỏ dành riêng cho test.

6. Phân tích và đồ thị
- Thống kê nền: số mẫu hợp lệ, mean/median/std/min/max và độ trôi.
- Ba tín hiệu mùi chính: extrema tăng và giảm, thay đổi có dấu so với nền, % khi nền đủ điều kiện, slope, thời điểm extrema và AUC dùng thời gian thực.
- Hồi phục: lệch cuối pha so với nền và xu hướng hồi phục; không mặc định 60 s là đã sạch.
- Cảnh báo dữ liệu thiếu, cảm biến lỗi, baseline drift, ADC chạm giới hạn đo, không hồi phục hoặc pha chưa hoàn thành. Ngưỡng cấu hình được, cảnh báo không xóa dữ liệu.
- Khi pha thiếu hoặc baseline không đủ hợp lệ, thống kê liên quan trả null và lý do; không chia cho 0.
- PNG có các subplot phù hợp cho BME gas, MQ135, MQ3 và nhiệt độ/độ ẩm/áp suất, có vùng pha và mốc sự kiện.
- Thêm đồ thị đáp ứng chuẩn hóa so với nền nếu hợp lệ, giữ riêng với dữ liệu raw.
- PNG render được trên Pi không cần desktop; cho chạy phân tích lại offline từ lượt đã lưu.

7. Kiến trúc, lệnh và bàn giao
- CLI Python gọn, dependency phù hợp Pi và Python thực tế. Tách reader, pump controller, state machine, writer và analysis đủ để kiểm thử; tránh framework quá nặng.
- Có backend mô phỏng tái lập được và backend cảm biến thật; sim phải chạy kể cả không có thư viện GPIO/I2C.
- Có lệnh kiểm tra môi trường (doctor), monitor, collect và phân tích offline; có tùy chọn hardware/pump-disabled rõ ràng.
- Viết test tập trung vào timer pha, thao tác nhập không chặn thu, dữ liệu lỗi, lưu khi thoát sớm, đổi tên/trùng tên, sim không truy cập hardware và OFF best-effort của controller.
- Chạy test phù hợp, mô phỏng end-to-end với thời lượng ngắn và kiểm tra các file/PNG sinh ra; sửa lỗi phát hiện được.
- Lưu thiết kế/schema/hướng dẫn sử dụng trong repo, không dựa vào lịch sử chat.
- Cuối cùng báo chính xác: file đã đổi, kiểm tra thực sự đã chạy và kết quả, việc chưa kiểm tra bằng hardware, cấu hình còn thiếu, các lệnh copy-paste dùng .venv để chạy doctor, mô phỏng, monitor hardware với pump-disabled, collect thật và phân tích lại.
- Nếu môi trường cản một bước, nói rõ bước bị cản và vẫn hoàn tất phần độc lập; không tuyên bố hardware đã chạy nếu chỉ dùng sim.

---

6. Rà soát và thử mô phỏng

Sau khi Codex bàn giao, gửi:

---

Rà soát bản RoboNose v1.0 vừa triển khai với yêu cầu đã lưu trong repo. Tập trung vào lỗi ảnh hưởng dữ liệu và điều khiển:
- Khi chờ nhập lệnh hoặc chờ chuyển pha, cảm biến vẫn được đọc và lưu.
- Các pha chính đúng thời gian theo monotonic clock; khoảng chờ được gắn nhãn riêng.
- Sim và pump-disabled không truy cập GPIO ngoài ý muốn.
- ADC/voltage, đơn vị, dữ liệu thiếu và các cờ chất lượng được xử lý đúng.
- Kết thúc sớm vẫn giữ CSV, metadata, events và trạng thái thích hợp.
- Đặt tên sau không ghi đè file cũ, không làm mất dữ liệu.
- Stats/plot dùng đúng pha và mẫu hợp lệ; xử lý pha thiếu và baseline gần 0.

Hãy sửa lỗi thực sự tìm được, chạy kiểm tra phù hợp và một lượt mô phỏng tương tác ngắn. Nếu test nhập lệnh bằng automation, giữ stdin mở đủ lâu để thể hiện các pha và chứng minh vòng đọc không bị chặn.

Bàn giao các lệnh copy-paste đúng theo CLI thực tế, giải thích lệnh thao tác trong lúc thu và hướng dẫn một lượt 30–60–60. Chưa truy cập phần cứng thật, chưa commit/push.

---

Chạy đúng lệnh .venv/doctor/collect mô phỏng do Codex đưa ra ở terminal thứ hai. Thử thời lượng ngắn trước, rồi một lượt mặc định 30–60–60. Quan sát CSV tăng trong khi đang chờ thao tác; thử marker, tên tùy ý, kéo dài hồi phục và thoát sớm. Kiểm tra đường dẫn output, raw/events/meta/summary/PNG. Mô phỏng được lưu ở vùng riêng.

7. Kiểm tra cảm biến thật rồi thu

Gửi:

---

Chuẩn bị kiểm tra cảm biến thật cho RoboNose v1.0.
- Đọc README, cấu hình và kết quả test hiện tại.
- Cho tôi lệnh activate .venv, doctor và monitor hardware với điều khiển bơm disabled.
- Giải thích cách kiểm tra đủ BME688, MQ135 ở A0 và MQ3 ở A1; đơn vị, timestamp và flag chất lượng.
- Nếu GPIO/mức kích bơm chưa biết, giữ pump disabled và hướng dẫn cách điền đúng cấu hình sau khi tôi xác nhận dây thực tế; không tự chọn chân.
- Cho lệnh collect thật 30–60–60 với pump-disabled, hướng dẫn từng thao tác và các file sinh ra. Tôi tự chạy các lệnh phần cứng ở terminal.
- Nếu thiếu dependency hoặc quyền thiết bị, chỉ ra đúng lỗi và cách sửa tối thiểu; không tự sửa hệ điều hành hay chạy sudo.
- Cuối cùng cho danh sách chính xác file code/docs nên commit, kiểm tra .gitignore đang loại data/.venv/secrets và đưa lệnh git add theo danh sách đó. Không tự commit/push.

---

Bạn tự chạy doctor và monitor hardware với pump disabled. Đối chiếu địa chỉ/kênh thực tế, giá trị và các flag. Cấu hình driver có thể kích heater cảm biến để đo, nhưng pump-disabled không điều khiển GPIO của bơm; trạng thái vật lý bơm còn phụ thuộc mạch và nguồn ngoài.

Khi các cảm biến đọc được, chạy một lượt collect thật: chuẩn bị nền, bắt đầu BASELINE, đánh dấu EXPOSURE đồng thời đưa mẫu vào, đánh dấu RECOVERY đồng thời bỏ mẫu/xả buồng, kết thúc hoặc kéo dài rồi đặt tên. Lệnh thao tác cụ thể lấy từ help/README thực tế vừa được tạo.

Sau đó xác nhận chân BCM đã nối TRIG MOSFET và mức kích HIGH/LOW để bật bơm; cập nhật cấu hình. Chạy thử điều khiển bơm theo hướng dẫn trong repo khi sẵn sàng. Không nhập số GPIO theo ví dụ khi dây thực tế khác.

8. Lưu phiên bản bằng Git

Trong Source Control hoặc theo danh sách file code/docs Codex đã bàn giao, chọn các file cần lưu. Không dùng git add . một cách máy móc. Trước commit kiểm tra:

```bash
git diff --stat
git diff --cached --stat
git status --short
```

Sau khi đã stage đúng các file code/docs:

```bash
git commit -m "Implement RoboNose v1 exploratory acquisition"
git push -u origin feat/robonose-v1-pilot
```

Các lệnh giả định đang ở nhánh feat/robonose-v1-pilot và origin là remote bạn đã setup. Dữ liệu đang được ignore không đi theo git push; sao lưu CSV/JSON/PNG bằng cách riêng, ví dụ chép thư mục lượt thu sang laptop sau mỗi buổi.

9. Tiếp tục lần sau hoặc báo lỗi

Trong cùng repo, mở lại phiên CLI:

```bash
codex resume --last --sandbox workspace-write --ask-for-approval on-request
```

Gửi log kèm lệnh chạy, sử dụng prompt:

---

Tôi chạy lệnh dưới đây và gặp lỗi:

[LỆNH ĐÃ CHẠY]

Log nguyên văn:
[LOG LỖI]

Hãy đọc code và truy tìm nguyên nhân từ log; nếu đủ dữ liệu thì sửa lỗi và kiểm tra phần liên quan. Bảo toàn mọi dữ liệu thu và các chức năng đã hoạt động. Chỉ thay đổi cần thiết, giải thích nguyên nhân và đưa lệnh chạy lại. Nếu thiếu thông tin, nêu chính xác thông tin còn thiếu; không đoán nguyên nhân hoặc coi test mô phỏng là kiểm tra phần cứng.

---

Nguồn chính thức đã đối chiếu cho thao tác Codex:

- [CLI và lệnh resume](https://developers.openai.com/codex/cli/reference)
- [Quyền làm việc và approval](https://developers.openai.com/codex/agent-approvals-security)
- [AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- [Codex trong IDE](https://developers.openai.com/codex/ide)


# Rà soát RoboNose v1.0 — 02/10/2026

Đối chiếu yêu cầu trong `RoboNose_v1_Codex_Guide.md`, AGENTS và schema.
Chỉ chạy mô phỏng/mock; chưa mở I2C/GPIO, chưa chạy bơm, chưa commit/push.
Không sửa hệ điều hành/cài thêm package. Giữ tài liệu và dữ liệu thu có sẵn.

## Lỗi đã tìm và sửa

1. **UI xử lý trễ kéo dài pha chính:** tái hiện trực tiếp baseline yêu cầu 1 s,
   tick ở t=5 s, code cũ ghi actual_s=5 s. State machine nay kết thúc ở deadline;
   worker nhận deadline trong context và tự gắn nhãn WAIT khi bắt đầu đọc, không
   đợi UI. Command batch cũng tick trước khi áp dụng lệnh. Event giữ mốc hiệu lực.
2. **Reader lỗi lúc đóng lượt:** code cũ bỏ `self.run` trước barrier mà chưa giữ
   tham chiếu để cleanup. Thêm `finishing` và mốc kết thúc đã yêu cầu; test tiêm lỗi
   ở phép đọc thứ ba lúc abort giữ hai dòng đã đọc, đóng file và ghi ERROR/run_end.
3. **AUC nối qua khoảng chờ không có mẫu giữa hai đoạn recovery:** nay kiểm tra
   cùng phase interval. Fixture cho AUC đúng 22, loại phần nối qua khoảng chờ 11.
4. **Nền chưa đủ và session nhiều lượt vẫn có số thống kê nền:** giữ n quan sát,
   thống kê số null với reason khi nền thiếu/chưa đủ/chưa hoàn thành. Session/
   monitor không tính đáp ứng nền nhiều lượt; dùng summary của từng collect.
   Completion chấp nhận sai số số thực rất nhỏ (1e-9), không bỏ pha đã hoàn thành
   chỉ vì phép trừ monotonic bị roundoff.
5. **Decode UTF-8 từng chunk làm hỏng chữ tiếng Việt:** dùng incremental decoder.
   Test gửi nửa ký tự `á`, chờ 0.3 s, gửi phần còn lại; marker lưu nguyên `áo vải`
   và CSV vẫn tăng trong khi lệnh chưa có newline.
6. **Driver trả NaN/Infinity được đánh OK:** đổi trường không hữu hạn thành null,
   giữ các số hữu hạn và cờ thực đã đọc, ghi ERROR/lý do, fresh=false. Gas-invalid
   hữu hạn vẫn giữ raw và cờ False, không đổi thành 0.

## Kiểm tra

- `.venv/bin/python -m pytest -q`: **49 passed in 69.96 s**.
- Sau đó bỏ mock plot trong hai test nền bằng 0 và thiếu baseline, chạy riêng
  hai test đó: **2 passed in 7.72 s**; cả signals.png/normalized.png thực sự được
  render và có chữ ký PNG hợp lệ, không chia cho 0 hoặc crash khi raw rỗng.
- Bao gồm sim/pump-disabled không import GPIO/I2C, timer/UI trễ, sample context,
  queue đầy không drop, tắt bơm giả best-effort, thoát sớm/SIGINT/SIGTERM, hủy hỏi tên,
  trùng tên/traversal, lỗi lúc finish, ADC signed count cùng conversion và cả 6 gain,
  BME Pa→hPa/Ω/%RH/status bits, gas-invalid giữ giá trị, nonfinite/null,
  pha thiếu/nền gần zero, AUC theo timestamp không nối gap/đoạn khác.
- `git diff --check`: đạt; AST parse 19 file Python: đạt.
- Không thay đổi pump.py, driver native hoặc nguồn Bosch trong lần rà soát này.

## Phiên mô phỏng tương tác thực sự

Chạy `.venv/bin/python scripts/verify_interactive.py`, **không dùng --auto**.
Script giữ stdin mở, chặn import GPIO/I2C, mở `/dev/i2c-*`/GPIO và load Bosch library.
Ở WAIT_EXPOSURE gửi một phần lệnh tiếng Việt, gồm nửa ký tự UTF-8 và chưa có newline.

| Pha | Khoảng chờ không gửi lệnh hoàn chỉnh | CSV trước → sau | Dòng thêm đúng pha |
|---|---:|---:|---:|
| MONITOR | 0.7 s | 1 → 15 | 14 |
| WAIT_EXPOSURE | 0.7 s | 31 → 45 | 14 |
| WAIT_RECOVERY | 0.7 s | 62 → 76 | 14 |
| WAIT_FINISH | 0.7 s | 92 → 107 | 15 |
| WAIT_NAME (session) | 0.7 s | 117 → 131 | 14 |
| WAIT_NOTES (session) | 0.4 s | 132 → 140 | 8 |

Lượt `b93e259ca6c342d59a4b5e0b0f7b33c6`: COMPLETE, 117 dòng; 16 lỗi BME được
ghi trống/lý do, không mất mẫu ADS. Baseline/exposure 0.8/0.8 s; recovery 0.8 s
và extension 0.5 s, tổng thực tế 1.3 s (sai số số thực <1e-12). Không có mẫu timed
bị gắn nhãn qua deadline. Đặt tên nguyên văn `../../Rà soát áo` được làm sạch,
UUID giữ nguyên và nằm trong cùng output parent. `pump on` bị từ chối, mọi raw
pump_command=DISABLED. Đủ raw/events/meta/summary/signals.png/normalized.png.

Phân tích lại bằng CLI: exit 0, checksum raw.csv/events.csv/metadata.json không đổi.
Cảnh báo đúng 16 lỗi BME và 13.7% gas không hợp lệ.

- Console: `logs/interactive_review_2966b5fb3f4d.log`.
- Report số dòng/checksum: `logs/interactive_review_2966b5fb3f4d.json`.
- Output: `data/simulation/2026-10-02/Rà_soát_áo_20261002_123826_b93e259ca6c342d59a4b5e0b0f7b33c6/`.

## File thay đổi trong lượt rà soát

Sửa `robonose/state.py`, `session.py`, `writer.py`, `analysis.py`, `readers.py`,
`tests/test_analysis.py`, `README.md`, `docs/schema.md`, `docs/design.md`.
Tạo `tests/test_review.py`, `scripts/verify_interactive.py`, `docs/review.md`.
Output và log mô phỏng đã ignore; không xóa output cũ.

## Thao tác 30–60–60

```bash
cd /home/pi/robonosev1.0
.venv/bin/python -m robonose doctor --config config.example.toml
.venv/bin/python -m robonose collect --sim --pump-disabled \
  --baseline 30 --exposure 60 --recovery 60 \
  --sample-description "mẫu tự chọn" --sampling-method "cách lấy khí tự chọn"
```

MONITOR/warmup ghi ngay; gõ `start` khi sẵn sàng. Sau BASELINE 30 s, ở WAIT_EXPOSURE
gõ `expose` đồng thời thao tác tiếp xúc. Sau EXPOSURE 60 s, ở WAIT_RECOVERY gõ
`recover` đồng thời bỏ mẫu/xả thực tế. Sau RECOVERY 60 s, chọn `finish` hoặc
`extend 30`/`extend 60`/`extend <giây>`, rồi quyết định ở WAIT_FINISH tiếp theo.
Thu xong `name ...`, `notes ...` hoặc `skip`/Enter ở từng câu hỏi. `next` cho lượt
mới, `quit` kết thúc phiên. `mark ...`, `status`, `help`, `abort` dùng trong khi thu.
`durations B E R` chỉ đổi trước baseline/giữa lượt; `info <trường> <văn bản>` nhập mô tả.

Lệnh hardware trong README chỉ dành cho người dùng tự chạy sau xác nhận nguồn/dây;
để `--pump-disabled` đến khi có GPIO/cực tính thực tế. Phần cứng thật chưa được
kiểm thử. Deadline phần mềm không xác nhận việc đưa/bỏ mẫu hoặc chuyển khí vật lý.

## Sửa giao diện terminal và start từ MONITOR (2026-10-02)

Hai lỗi xác định: output trạng thái dùng print trong khi terminal đang nhập
canonical nên xen vào dòng nhập; CLI monitor chưa mở state machine lượt thu,
nên start rơi vào nhánh từ chối chung. Không phải lỗi cảm biến hay heater.

- Thêm robonose/terminal.py: một ứng dụng PromptSession chạy liên tục, nhận
  input/editing trên luồng UI; patch_stdout đưa mọi output qua cùng renderer.
  Lệnh hoàn chỉnh được chuyển bằng queue sang vòng state/writer. Vòng acquisition
  tiếp tục độc lập; không đợi Enter. Pipe/auto giữ decoder không chặn cũ.
- monitor nhận start, mở lượt BASELINE trên reader/heater đang hoạt động;
  log liên tục giữ toàn bộ warmup trước start. --duration chỉ giới hạn monitor
  trước start, không cắt lượt thu sau đó. next tiếp tục được sau lượt đầu.
- Chuẩn hóa khoảng trắng/newline và casefold từ khóa, giữ nguyên nội dung Unicode
  marker. Events command_received lưu raw và normalized để đối chiếu.
- start kiểm tra reader/vòng acquisition còn hoạt động, báo rõ nếu chưa sẵn sàng
  hoặc sai pha. Không có ngưỡng warmup tự động trong cấu hình hiện tại: người dùng
  chọn lúc đủ warmup; chương trình không chứng nhận cảm biến đã ổn định.
- Không sửa state.py hoặc deadline monotonic của ba pha chính.
- prompt-toolkit 3.0.53, pyte 0.8.2 và wcwidth 0.9.1 cài trong .venv;
  pyproject.toml/requirements-lock.txt và README đã cập nhật. pyte chỉ dùng test.

Kiểm thử PTY thật (pty.openpty + màn hình VT100 pyte), backend sim và chặn
import/device GPIO/I2C: cả monitor và collect nhận từng ký tự s/t/a/r/t,
chờ 0.5 s giữa ký tự, kiểm tra dòng tại cursor đúng robonose> + nội dung đã gõ.
Mỗi khoảng chờ in 7–10 trạng thái và ghi thêm 11–12 dòng CSV. Ví dụ monitor:
s 10→21 dòng, st 22→34, sta 34→46, star 47→58, start 59→70;
thêm x 71→82, Backspace trở về start 83→94. Đây là số dòng đọc lại từ
raw.csv trên đĩa, không chỉ đếm output. Sau Enter, event raw=start,
normalized=start và transition BASELINE xuất hiện đúng một lần.
Unicode mark thử nghiệm giữ nguyên. Ctrl+C trong WAIT_EXPOSURE lưu ABORTED;
BASELINE actual_s=2 s. EOF/Ctrl+D dòng trống và quit lưu monitor COMPLETE.
Cả ba cách thoát khôi phục ECHO/ICANON terminal. Test chuẩn hóa start với
CR/LF/tab/chữ hoa, deadline 30 s và lỗi readiness có lý do cụ thể cũng đạt.
8 kiểm thử mới đạt (45.61 s). Bằng chứng:
.cache/pty_fixed_20261002a/test_slow_tty_start_backspace_0/pty_proof.json
và pty_console.txt (console giữ cả mã điều khiển terminal).

scripts/verify_interactive.py exit 0, vẫn ghi lúc stdin mở/chờ lệnh:
MONITOR +14, WAIT_EXPOSURE +14, WAIT_RECOVERY +14, WAIT_FINISH +14,
WAIT_NAME +15, WAIT_NOTES +8 dòng. Report:
logs/interactive_review_94dbd35e90b5.json. Dữ liệu mô phỏng giữ ở:
data/simulation/2026-10-02/Rà_soát_áo_20261002_171815_d8ac784215f542bb944ce456b7976b99/.
pip check và git diff --check đạt. Không chạy hardware, không bật bơm,
không commit/push, không xóa output cũ.

File thay đổi: robonose/terminal.py, session.py, cli.py, writer.py,
tests/test_terminal.py, pyproject.toml, requirements-lock.txt, README.md,
docs/review.md. Driver và schema cảm biến không thay đổi.

Người dùng tự kiểm tra trên hardware:

```bash
cd /home/pi/robonosev1.0
.venv/bin/python -m robonose doctor --config config.example.toml
.venv/bin/python -m robonose monitor --hardware --pump-disabled \
  --config config.example.toml --display-interval 0.5 \
  --baseline 30 --exposure 60 --recovery 60
```

Trong MONITOR, chờ warmup phù hợp; gõ chậm từng ký tự start, thử thêm x rồi
Backspace, kiểm tra prompt vẫn đầy đủ, nhấn Enter một lần. BASELINE 30 s →
WAIT_EXPOSURE: expose đồng thời đưa mẫu → EXPOSURE 60 s →
WAIT_RECOVERY: recover đồng thời bỏ mẫu/xả → RECOVERY 60 s →
WAIT_FINISH: finish hoặc extend 30/60. name/notes hoặc skip ở từng câu hỏi;
quit kết thúc phiên. mark thử nghiệm đánh dấu sự kiện. Ctrl+C giữ lượt dở dang;
Ctrl+D trên dòng trống kết thúc input và giữ dữ liệu. Bơm vẫn disabled.

Toàn bộ suite cuối cùng: .venv/bin/python -m pytest -q --basetemp
.cache/full_terminal_20261002b → 57 passed in 126.20 s.
Doctor exit 0, hardware_opened=false; chỉ đọc metadata/đường dẫn.

## Hoàn thiện thử tích hợp (2026-10-02)

Đọc code/config/README/review và raw, metadata, events, summary, signals.png của
lượt hardware mới nhất COMPLETE do người dùng thu:
data/exploration/2026-10-02/taidz_20261002_172514_318a946c320f4242a1aacc4191c9d0f8/.
385 dòng, BASELINE/EXPOSURE/RECOVERY 30/60/60 s. Không coi start là lỗi mới.
Baseline gas 16,728→75,095 Ω, mean 49,201 Ω, drift 118.63%, slope
249.18 %/phút; T mean 39.184°C, H slope −1.014 điểm %RH/phút. MQ135 mean
0.062396 V và MQ3 mean 0.243808 V tại ADS; không suy ra AO vì factor cũ null.
Bơm chưa cấp nguồn là quan sát người dùng; CSV DISABLED chỉ xác nhận phần mềm
không điều khiển GPIO, không đo trạng thái nguồn hoặc lưu lượng.

### Thay đổi và giới hạn

- quality.py dùng chung UI/offline: cửa sổ gas/T/H, slope theo thời gian,
  range, số mẫu/độ phủ, thiếu/cũ/gap, không chỉ heater_stable. [stability]
  cấu hình được. Không ép thời gian warmup và không chặn start khi chưa ổn định.
  Snapshot pre_baseline_quality, baseline_started_without_stability và
  baseline_quality/baseline_unstable lưu metadata, summary.measurement_quality.
  Pha thiếu/chưa đủ đánh giá cho null và lý do; trôi rõ có cờ false cho stable.
  Advisory nhiệt độ cao độc lập với tiêu chí xu hướng.
- Cả hai PNG có nhãn BASELINE DRIFT / UNASSESSED khi cần. Thống kê số giữ
  dưới dạng thay đổi tín hiệu; không quy kết mùi, không thêm ppm/IAQ/ML.
- adc_inputs ghi kênh, điện áp tại ADS, mô tả chia áp và factor đã xác nhận.
  Dự kiến 10 kΩ/10 kΩ được ghi là chưa xác nhận; AO null đến khi factor được
  khai báo chính xác từng kênh. Driver/count/unit/flags và raw không thay đổi.
- JZ-MOS BCM17/physical11 đã xác định theo người dùng. Cực tính còn chưa
  xác nhận: template disabled/confirmed=false/active_high chưa đặt.
  GPIO chỉ dùng on/off; khởi tạo OutputDevice initial_value=false theo cực tính.
  OFF lúc kết thúc/abort/cleanup; bổ sung sự kiện OFF khi kết thúc lượt vào cả
  session log (trước chỉ có event của lượt), và sự kiện khởi tạo ở session.
  Trạng thái ON/OFF là command, physical feedback=null/chưa đo.
- Thêm pump-test: sim mặc định không GPIO/I2C; hardware cần --hardware
  --enable-pump và config xác nhận. OFF→ON theo deadline monotonic bắt đầu
  ngay sau gửi ON→OFF, cleanup OFF, giới hạn <=10 s; độc lập với cảm biến.
  Audit CSV/events/meta/summary, cảm biến null, không PNG cảm biến.
  Không bảo đảm OFF lúc Pi chưa boot/mất điện/SIGKILL; phải kiểm tra module thật.
- Terminal renderer không đổi trong lượt này: 8 test PTY đạt lại 44.90 s,
  cả monitor/collect, từng ký tự start với output liên tục, Backspace, Unicode,
  Ctrl+C/EOF, CSV tăng và BASELINE đúng một lần. Chưa tái hiện lỗi giao diện mới.

### Bằng chứng khảo sát/kiểm thử

Phân tích hardware trên **bản sao** .cache/hardware_analysis_96d5c980e6,
phát hiện gas/H đang trôi và T vượt ngưỡng cảnh báo 35°C. Hash của raw/events/
metadata/summary/cả hai PNG nguồn giữ nguyên. Report đối chiếu:
logs/integration_hardware_source.json. Không chạy analyze vào nguồn cũ.

Test mới kiểm tra: tiêu chí gas/T/H độc lập heater-bit, ngưỡng có thể đổi,
thiếu/gap/cũ/nền gần zero/pha thiếu; count-voltage cùng conversion/factor AO;
mock JZ-MOS hai cực tính đều pin17 initial_value=false; OFF/ON/OFF có audit;
Ctrl+C/exception cố gắng OFF, OFF thất bại báo UNKNOWN/ERROR.
Mất BME toàn bộ baseline: gas null, ADC vẫn ghi, COMPLETE pipeline nhưng
baseline chất lượng null và thống kê gas liên quan null. EOF baseline giữ
ABORTED và đủ CSV/events/meta/summary/PNG. Abort khi mock ON ghi OFF ở cả
session/lượt. Test phiên nhiều lượt nay đặt cùng nhãn mẫu áo cho cả hai lượt:
UUID/đường dẫn khác nhau, lượt COMPLETE và lượt ABORTED đều giữ đầy đủ file.
Các test cũ vẫn kiểm tra SIGINT/SIGTERM, lỗi giữa lượt, tên đích trùng thực sự,
AUC không nối qua gap/extension, pha thiếu và baseline gần 0, offline giữ raw.

Phiên scripts/verify_interactive.py (không --auto, guard chặn hardware) exit 0:
lượt fd48213d2d4543cda23ff38d5b85213d COMPLETE, 117 dòng; BME lỗi 16 dòng
giữ null/lý do và dữ liệu ADS. Baseline/exposure 0.8/0.8 s, recovery 1.3 s gồm
extension 0.5 s, sai số số thực <1e-9. WAIT vẫn ghi:

| Pha | CSV trước → sau |
|---|---:|
| MONITOR | 1 → 15 |
| WAIT_EXPOSURE | 32 → 45 |
| WAIT_RECOVERY | 62 → 76 |
| WAIT_FINISH | 92 → 107 |
| WAIT_NAME | 118 → 132 |
| WAIT_NOTES | 133 → 141 |

Report logs/interactive_review_d32e63e092de.json; analyze offline exit 0,
checksum raw/events/meta không đổi, đủ hai PNG. Pump-test sim 2 s exit 0:
data/simulation/2026-10-02/20261002_175224_273c6ceeb7414f4b9a64304d953e377d/,
mọi command DISABLED (chỉ requested_command mô tả diễn tập ON/OFF).
Doctor exit 0, hardware_opened=false, template pump BCM17 disabled và
active_high=null. Không truy cập GPIO/I2C thật, không cấp nguồn/chạy bơm.

File chỉnh trong lượt này: AGENTS.md, README.md, config.example.toml,
docs/schema.md, docs/review.md; robonose/config.py, quality.py (mới),
analysis.py, session.py, writer.py, cli.py, pump_test.py (mới);
tests/test_integration_ready.py (mới), test_session.py, test_terminal.py
(chỉ cập nhật mock Session cho metadata mới). Các thay đổi dependency và
robonose/terminal.py có sẵn từ lượt trước được bảo toàn, không cài thêm dependency.

### Checklist nghiệm thu

1. Doctor + monitor --hardware --pump-disabled: xác nhận count/voltage/flags,
   gas/T/H và xu hướng; lưu mark trạng thái nắp/nguồn bơm. Xác nhận nguồn MQ/ADS
   và chia áp A0/A1, không mặc định tín hiệu gas tăng là mùi.
2. Xác nhận JZ-MOS cực tính, BCM17/physical11, GND điều khiển nối GND Pi,
   nguồn 12 V riêng. Kiểm tra OFF cả trước/chưa boot Pi bằng hardware.
   Người dùng tự chạy pump-test OFF→ON 2 s→OFF và đối chiếu bơm thực tế.
3. Thu 30–60–60; tự chọn bằng ống/mở nắp, ghi phương pháp/nắp/xả/marker.
   start sau warmup tự quyết định; expose/recover đúng lúc thao tác mẫu.
   finish/extend, name/notes hoặc skip; kiểm tra COMPLETE và chất lượng riêng.
4. Xem raw/% PNG và summary.measurement_quality; analyze lại không sửa raw.
   next cho lượt mới, quit kết thúc. Nếu chưa xác nhận bơm luôn --pump-disabled.

Lệnh chính xác, chỉ người dùng tự chạy hardware:

```bash
cd /home/pi/robonosev1.0
.venv/bin/python -m robonose doctor --config config.example.toml
.venv/bin/python -m robonose monitor --hardware --pump-disabled --config config.example.toml
cp --no-clobber config.example.toml config.jz-mos.toml
nano config.jz-mos.toml
# Sau xác nhận: [pump] confirmed=true, gpio_bcm=17, active_high theo mức TRIG;
# giữ enabled=false. Nếu xác nhận chia áp 10k/10k, đặt factor=2.0 từng kênh
# và description đã xác nhận. Chưa xác nhận thì không đặt factor/cực tính.
.venv/bin/python -m robonose pump-test --hardware --enable-pump --config config.jz-mos.toml --seconds 2
.venv/bin/python -m robonose collect --hardware --enable-pump --config config.jz-mos.toml \
  --baseline 30 --exposure 60 --recovery 60 --sampling-method "bằng ống hoặc mở nắp" \
  --purge-method "cách xả thực tế" --lid-state "trạng thái nắp"
.venv/bin/python -m robonose analyze "data/exploration/YYYY-MM-DD/THU_MUC_LUOT"
```

Terminal: start → đợi WAIT_EXPOSURE rồi expose → đợi WAIT_RECOVERY rồi recover →
đợi WAIT_FINISH rồi finish hoặc extend 30/60; name/notes hoặc skip. mark ... ghi
mốc; pump on/off thủ công nếu đã enable (không tự bật theo pha). Nếu chưa xác nhận
bơm, collect với --pump-disabled; không chạy pump-test hardware.
Nghiệm thu trên nguồn 12 V, cực tính/module, trạng thái OFF lúc boot, hoạt động
bơm/lưu lượng, ảnh hưởng nhiệt/warmup và mức AO chỉ người dùng xác nhận được.

Kết quả cuối sau chỉnh deadline pump-test và test OFF thất bại:
.venv/bin/python -m pytest -q --basetemp .cache/integration_final_20261002d
→ 73 passed in 142.17 s. Kiểm tra git diff/git status: nhánh
feat/robonose-v1-pilot, giữ các thay đổi có sẵn; git diff --check đạt.
Không commit/push. Đối chiếu checksum nguồn hardware lần cuối: 6/6 không đổi.
PTY sau thêm dòng chất lượng: monitor nhập s→start, raw 10→70 dòng;
mỗi ký tự 5–9 trạng thái mới, rồi x/Backspace giữ start, raw lên 94 dòng.
Collect tương tự 10→71 rồi lên 95 dòng. Không tái hiện mất ký tự/chèn lệnh.

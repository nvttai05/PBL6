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

# Kiểm tra thực sự đã chạy — 02/10/2026

Môi trường: Pi 4 Model B Rev 1.4, Debian 12, ARM64, Python 3.11.2 trong `.venv`.
Không truy cập I2C/GPIO, không chạy bơm. Không sửa OS hoặc commit/push.

- Biên dịch Bosch bridge bằng `.venv/bin/python -m robonose.build_driver`:
  thành công với `cc -Wall -Wextra -Werror`. Không load/open thiết bị.
- `.venv/bin/python -m pytest -q`: lần đầu 30 passed;
  sau sửa barrier/đóng file và thêm test acquisition: **32 passed, 60.41 s**.
- Thêm kiểm thử tên Unicode dài sau lượt chạy trên, chạy riêng
  `tests/test_core.py::test_long_unicode_name_has_valid_byte_length`:
  **1 passed, 0.19 s**. Tổng 33 kiểm thử hiện có đã đạt.
- Phiên tương tác dùng pipe nhưng giữ stdin mở trong các khoảng chờ:
  CSV tiếp tục tăng ở WAIT_EXPOSURE, WAIT_RECOVERY và WAIT_NAME;
  extension 0.3 s, đặt tên có traversal, hai lượt/phiên, một lượt ABORTED.
- SIGINT/SIGTERM giữ raw và trạng thái ABORTED; SIGINT khi hỏi tên giữ lượt COMPLETE.
- Fake GPIO kiểm tra OFF best-effort và lỗi OFF; sim chạy với hardware imports bị chặn.
- Driver ADS được test bằng mock register, một conversion/count-voltage;
  BME được test bằng kết quả Bosch giả để kiểm tra đơn vị/cờ/stale.
- `.venv/bin/python -m pip check`: No broken requirements found.
- AST parse 17 file Python và `git diff --check`: đạt ở thời điểm kiểm tra.
- `doctor --config config.example.toml`: dependency/bridge có;
  hardware_opened=false, `/dev/i2c-1` không thấy trong môi trường chạy hiện tại.
- Mô phỏng E2E thật bằng CLI: sample_hz=10, các pha 1–1–1 s,
  warmup=0.5 s, các khoảng chờ 0.3 s, lỗi BME mỗi 7 vòng.
  Lượt `cbb4f53abeed4e9eac82e2f8598d2b61`: COMPLETE, 44 dòng, đủ 7 pha,
  6 lỗi BME lưu số đo trống; raw/events/meta/summary/signals.png/normalized.png đầy đủ.
  Thời lượng thực tế baseline/exposure/recovery: 1.0003/1.0091/1.0013 s.
- Monitor mô phỏng CLI 0.5 s, 10 Hz: COMPLETE và tạo được output/PNG.
- CLI analyze offline trên lượt E2E: exit 0; SHA-256 của raw.csv,
  events.csv và metadata.json không đổi. Cảnh báo phản ánh đúng 6 lỗi BME
  và 13.6% mẫu gas không hợp lệ.
- Kiểm tra PNG bằng chữ ký binary trong test và xem trực tiếp signals.png của E2E:
  đủ 6 subplot, vùng pha và các mốc lỗi đọc, render Agg không cần desktop.

Dữ liệu mô phỏng nằm trong `data/simulation/2026-10-02/`, đã ignore và được giữ lại.
Test fixtures tạm không phải dữ liệu thu phần cứng.

Chưa kiểm tra: wiring/nguồn/chia áp, địa chỉ thiết bị thực tế, cấu hình heater thực
tế, driver trên I2C thật, GPIO/MOSFET, bơm/lưu lượng, warmup và hiệu chuẩn MQ.
Các lệnh hardware trong README dành cho người dùng tự chạy sau xác nhận phần cứng.

## File triển khai

- Sửa `.gitignore`; bổ sung `AGENTS.md` có sẵn, giữ các quy tắc cũ.
- Tạo `README.md`, `config.example.toml`, `pyproject.toml`, `requirements-lock.txt`.
- Tạo `docs/schema.md`, `docs/design.md`, `docs/validation.md`, `docs/vendor-provenance.json`.
- Tạo `robonose/__init__.py`, `__main__.py`, `cli.py`, `config.py`, `schema.py`,
  `state.py`, `readers.py`, `pump.py`, `writer.py`, `analysis.py`, `session.py`, `build_driver.py`.
- Tạo `robonose/native/bridge.c`; tải nguyên bản `native/vendor/bme68x.c`,
  `bme68x.h`, `bme68x_defs.h`, `LICENSE` từ Bosch.
- Tạo `tests/__init__.py`, `test_core.py`, `test_analysis.py`, `test_session.py`, `test_acquisition.py`.
- `.venv`, `.cache`, compiled `.so` và output mô phỏng là artifact đã ignore.
- Không sửa `RoboNose_v1_Codex_Guide.md`, không xóa dữ liệu có sẵn.

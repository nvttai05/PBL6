import argparse
import json
from pathlib import Path
import platform
import sys
from . import __version__
from .config import load, validate, positive
from .readers import package_version

def parser():
    p = argparse.ArgumentParser(description="RoboNose v1.0 — khảo sát cảm biến; mặc định mô phỏng")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="Kiểm tra môi trường/cấu hình, không mở GPIO/I2C")
    doctor.add_argument("--config")
    analysis = sub.add_parser("analyze", help="Phân tích lại offline; không sửa raw")
    analysis.add_argument("run_directory")
    for name in ("collect", "monitor"):
        s = sub.add_parser(name)
        s.add_argument("--config")
        backend = s.add_mutually_exclusive_group()
        backend.add_argument("--hardware", action="store_true", help="Mở cảm biến thật khi bạn tự chạy")
        backend.add_argument("--sim", action="store_true", help="Mô phỏng (mặc định)")
        pump = s.add_mutually_exclusive_group()
        pump.add_argument("--pump-disabled", action="store_true", help="Ghi đè config: không khởi tạo GPIO bơm")
        pump.add_argument("--enable-pump", action="store_true", help="Cần đầy đủ cấu hình đã xác nhận")
        s.add_argument("--output", default="data", help="Root output; luôn thêm simulation/exploration/ngày")
        s.add_argument("--sample-hz", type=float)
        s.add_argument("--baseline", type=float)
        s.add_argument("--exposure", type=float)
        s.add_argument("--recovery", type=float)
        s.add_argument("--display-interval", type=float, default=1.)
        s.add_argument("--sim-fail-every", type=int, default=0, help="Tiêm lỗi BME mỗi N vòng mô phỏng")
        s.add_argument("--auto", action="store_true", help="Tự thao tác CHỈ trong sim, để kiểm thử")
        s.add_argument("--auto-warmup", type=float, default=1.)
        s.add_argument("--auto-wait", type=float, default=.5)
        s.add_argument("--duration", type=float, help="Giới hạn thời gian monitor; collect dùng finish/abort")
        for field in ("sample_description", "person_code", "source", "sampling_method", "purge_method", "lid_state", "distance_cm"):
            s.add_argument("--" + field.replace("_", "-"), default="")
    return p

def doctor(cfg):
    dependencies = {name: package_version(name) for name in ("numpy", "matplotlib", "pytest", "smbus2", "gpiozero", "lgpio")}
    lib = Path(__file__).parent / "native/librobonose_bme.so"
    result = {"program_version": __version__, "python": sys.version, "executable": sys.executable,
        "virtualenv": sys.prefix != sys.base_prefix, "os": platform.platform(), "architecture": platform.machine(),
        "dependencies": dependencies, "bosch_bridge_present": lib.is_file(),
        "i2c_device_path_exists": Path(f"/dev/i2c-{cfg['hardware']['i2c_bus']}").exists(),
        "hardware_opened": False, "pump_config": cfg["pump"], "config": cfg,
        "note": "Chỉ kiểm tra metadata/đường dẫn. Không import GPIO, không mở I2C; chưa xác nhận cảm biến/bơm."}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if dependencies["numpy"] and dependencies["matplotlib"] else 1

def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "analyze":
            from .analysis import analyze
            result = analyze(args.run_directory)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        cfg = load(args.config, check=args.command == "doctor")
        if args.command == "doctor":
            return doctor(cfg)
        for option, key in (("sample_hz", "sample_hz"), ("baseline", "baseline_s"), ("exposure", "exposure_s"), ("recovery", "recovery_s")):
            if getattr(args, option) is not None:
                cfg[key] = getattr(args, option)
        if args.pump_disabled:
            cfg["pump"]["enabled"] = False
        elif args.enable_pump:
            cfg["pump"]["enabled"] = True
        validate(cfg)
        positive(args.display_interval, "display_interval")
        for k in ("auto_warmup", "auto_wait"):
            positive(getattr(args, k), k)
        if args.duration is not None:
            positive(args.duration, "duration")
        if args.command == "collect" and args.duration:
            raise ValueError("--duration chỉ dùng cho monitor")
        if args.auto and args.hardware:
            raise ValueError("--auto chỉ dùng mô phỏng")
        if args.auto and args.command == "monitor" and args.duration is None:
            raise ValueError("monitor --auto cần --duration")
        if args.hardware and args.sim_fail_every:
            raise ValueError("Tiêm lỗi chỉ dùng mô phỏng")
        if args.sim_fail_every < 0:
            raise ValueError("sim-fail-every >= 0")
        from .session import Session
        return Session(args, cfg).run_session()
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())

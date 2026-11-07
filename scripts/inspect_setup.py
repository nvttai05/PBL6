"""Inspect host dependencies and known local paths; never open serial or run legacy code."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
os.environ["MPLCONFIGDIR"] = str(RUNTIME / "mplconfig")
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"
COMMANDS = []


def run_readonly(arguments: list[str], log_name: str) -> dict:
    try:
        result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=20)
        record = {"argv": arguments, "exit_code": result.returncode,
                  "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except (OSError, subprocess.TimeoutExpired) as error:
        record = {"argv": arguments, "exit_code": None, "error": str(error)}
    (RUNTIME / "logs" / log_name).write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    COMMANDS.append(record)
    return record


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if Path(sys.prefix).resolve() != (ROOT / ".venv").resolve():
        raise SystemExit("Run this script using this project's .venv/Scripts/python.exe")
    (RUNTIME / "logs").mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone(timedelta(hours=7))).isoformat()
    local_path = ROOT / "configs/paths.local.json"
    existing = json.loads(local_path.read_text(encoding="utf-8-sig")) if local_path.exists() else {}
    source_entries = {}
    for source_key, default in (("legacy_pi_source", ROOT / "legacy/pi"),
                                ("legacy_s3_source", ROOT / "legacy/s3")):
        candidate = Path(existing.get(source_key) or default).resolve()
        present = candidate.is_dir() and any(candidate.iterdir())
        source_entries[source_key] = {
            "checked_path": str(candidate), "path": str(candidate) if present else None,
            "status": "PRESENT" if present else "NEEDS_INPUT",
            "reason": None if present else "Source directory missing or empty; no legacy entry point executed.",
        }
    legacy_files = []
    for path in sorted((ROOT / "legacy").rglob("*")):
        if path.is_file():
            legacy_files.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                                 "sha256": digest(path)})
    git = run_readonly(["git", "status", "--short"], "git-status.json")
    documents = ["AGENTS.md", "configs/project_target.json", "requirements.in",
                 "prompts/01_KIEM_KE_VA_MOI_TRUONG.txt",
                 "docs/KE_HOACH_ROBONOSE_DATASET_ESP32S3.md", "docs/BAN_GIAO_ROBONOSE_ESP32S3.md"]
    inventory = {
        "generated_at": timestamp, "workspace_root": str(ROOT), "source_status": source_entries,
        "legacy_files": legacy_files,
        "sample_data_status": "PRESENT" if (ROOT / "legacy/samples").is_dir() else "NOT_PROVIDED",
        "legacy_entry_points_executed": False,
        "source_configs_tests": {"pi": "NOT_AVAILABLE", "s3": "NOT_AVAILABLE"},
        "reference_differences": [
            "Pi handover: A0 MQ135_1; current target: A0 TGS2602. S3 test A2 TGS is documented only; source not supplied.",
            "Pi handover: ADS 3.3 V, gain 1, dividers; target: ADS 5 V, gain 2/3, 0.0001875 V/count, no divider.",
            "Pi handover proposes standalone microSD/ESP-IDF and pump opt-in; target is USB/Windows, Arduino bring-up, pump automatic 80% after hardware app initialization.",
            "Current protocol: terminal WAIT transitions, baseline/exposure/recovery 60/120/60 s, valve ON sample and OFF filtered air.",
            "BME S3 bring-up 300 C/100 ms T2/H2/P4 differs from Pi 320 C/150 ms T8/H2/P4; production profile remains null until pilot."
        ],
        "legacy_versions_commits_diffs": None,
        "workspace_git": git,
        "workspace_git_note": "No repository: no commit or diff available." if git["exit_code"] else None,
        "documents_read": [{"path": name, "sha256": digest(ROOT / name)} for name in documents],
        "root_plan_matches_docs": digest(ROOT / "KE_HOACH_ROBONOSE_DATASET_ESP32S3.md") == digest(ROOT / documents[-2]),
        "scope": "Only workspace legacy and explicit paths.local.json source paths; no drive scan.",
    }

    local_app = Path(os.environ["LOCALAPPDATA"])
    ide_candidates = [local_app / "Programs/Arduino IDE",
                      Path(os.environ["ProgramFiles"]) / "Arduino IDE"]
    ide_root = next((p for p in ide_candidates if (p / "Arduino IDE.exe").is_file()), None)
    package_json = ide_root / "resources/app/package.json" if ide_root else None
    ide_version = json.loads(package_json.read_text(encoding="utf-8"))["version"] if package_json and package_json.is_file() else None
    cli_candidates = [Path(shutil.which("arduino-cli") or "__not_found__")]
    if ide_root:
        cli_candidates.append(ide_root / "resources/app/lib/backend/resources/arduino-cli.exe")
    cli = next((p.resolve() for p in cli_candidates if p.is_file()), None)
    cli_version = run_readonly([str(cli), "version"], "arduino-cli-version.json") if cli else None
    cores_root = local_app / "Arduino15/packages/esp32/hardware/esp32"
    cores = []
    if cores_root.is_dir():
        for core in sorted(cores_root.iterdir()):
            if not core.is_dir():
                continue
            platform_file = core / "platform.txt"
            if platform_file.is_file():
                selected = {line.split("=", 1)[0]: line.split("=", 1)[1]
                            for line in platform_file.read_text(encoding="utf-8-sig").splitlines()
                            if line.startswith(("name=", "version="))}
                cores.append({"directory_version": core.name, "path": str(core.resolve()),
                              "platform": selected})
    board = {key: None for key in ("model", "fqbn", "flash_mb", "psram_mb", "usb_cdc_on_boot", "port")}
    sample_dirs = [str(Path(p).resolve()) for p in existing.get("legacy_sample_dirs", []) if Path(p).is_dir()]
    if (ROOT / "legacy/samples").is_dir() and str(ROOT / "legacy/samples") not in sample_dirs:
        sample_dirs.append(str(ROOT / "legacy/samples"))
    paths = {
        "workspace_root": str(ROOT), "python_base_exe": str(Path(sys._base_executable).resolve()),
        "python_exe": str(Path(sys.executable).resolve()),
        **{key: value["path"] for key, value in source_entries.items()},
        "legacy_sample_dirs": sample_dirs, "arduino_cli_exe": str(cli) if cli else None,
        "arduino_ide_version": ide_version,
        "arduino_esp32_core_version": cores[0]["directory_version"] if len(cores) == 1 else None,
        "board": board,
    }
    imports = []
    for module_name, distribution in (("PySide6", "PySide6"), ("pyqtgraph", "pyqtgraph"),
                                      ("serial", "pyserial"), ("numpy", "numpy"),
                                      ("matplotlib", "matplotlib"), ("pytest", "pytest")):
        try:
            module = importlib.import_module(module_name)
            imports.append({"module": module_name, "distribution": distribution,
                            "version": importlib.metadata.version(distribution),
                            "file": str(Path(module.__file__).resolve()), "status": "PASS"})
        except Exception:
            imports.append({"module": module_name, "distribution": distribution,
                            "status": "FAIL", "error": traceback.format_exc()})
    try:
        from serial.tools import list_ports
        ports = [{"device": p.device, "description": p.description, "hwid": p.hwid,
                  "vid": p.vid, "pid": p.pid, "manufacturer": p.manufacturer,
                  "product": p.product} for p in list_ports.comports()]
        port_status, port_error = "PASS_ENUMERATION_ONLY", None
    except Exception:
        ports, port_status, port_error = [], "FAIL", traceback.format_exc()
    pip_check = run_readonly([sys.executable, "-m", "pip", "check"], "pip-check.json")
    frozen = run_readonly([sys.executable, "-m", "pip", "freeze"], "pip-freeze.json")
    if frozen["exit_code"] == 0:
        (ROOT / "requirements-lock.txt").write_text(frozen["stdout"] + "\n", encoding="utf-8")
    launcher = run_readonly(["py", "-0p"], "python-launcher.json")
    base_info = run_readonly([sys._base_executable, "--version"], "python-base-version.json")
    pip_info = run_readonly([sys.executable, "-m", "pip", "--version"], "pip-version.json")
    good = (sys.version_info[:2] == (3, 11) and struct.calcsize("P") * 8 == 64
            and all(item["status"] == "PASS" for item in imports)
            and pip_check["exit_code"] == 0 and frozen["exit_code"] == 0)
    environment = {
        "generated_at": timestamp, "timezone": "Asia/Saigon", "status": "PASS" if good else "FAIL",
        "scope": "Host preparation only; GUI results are in gui_smoke_report.json.",
        "os": {"platform": platform.platform(), "release": platform.release(),
               "version": platform.version(), "machine": platform.machine()},
        "python": {"executable": sys.executable, "base_executable": sys._base_executable,
                   "version": sys.version, "bits": struct.calcsize("P") * 8,
                   "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                   "launcher_probe": launcher, "base_version_probe": base_info,
                   "python_on_path": shutil.which("python"), "default_python_changed": False},
        "imports": imports, "pip_check": pip_check, "pip_version": pip_info,
        "lock_file": str(ROOT / "requirements-lock.txt") if frozen["exit_code"] == 0 else None,
        "arduino": {"ide_root": str(ide_root) if ide_root else None, "ide_version": ide_version,
                    "ide_version_source": str(package_json) if package_json else None,
                    "cli_exe": str(cli) if cli else None, "cli_version_probe": cli_version,
                    "esp32_cores": cores, "core_modified": False,
                    "known_successful_board_configuration": None,
                    "board_status": "UNKNOWN/NEEDS_INPUT: model and previously successful Tools settings not provided."},
        "com": {"status": port_status, "ports": ports, "error": port_error,
                "ports_opened": False, "board_port_selected": False},
        "hardware": {"serial_opened": False, "legacy_executed": False, "flashed": False,
                     "pump_or_valve_actuated": False, "build_status": "NOT_EXECUTED",
                     "hardware_validation_status": "NOT_EXECUTED"},
        "commands": COMMANDS,
        "setup_commands": json.loads((RUNTIME / "setup_commands.json").read_text(encoding="utf-8")),
    }
    write_json(local_path, paths)
    write_json(RUNTIME / "source_inventory.json", inventory)
    write_json(RUNTIME / "environment_report.json", environment)
    print(json.dumps({"status": environment["status"], "python": environment["python"],
                      "imports": imports, "arduino": environment["arduino"], "com": environment["com"],
                      "sources": source_entries}, ensure_ascii=False, indent=2))
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())

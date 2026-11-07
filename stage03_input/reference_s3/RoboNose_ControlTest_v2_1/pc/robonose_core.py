"""Protocol validation and crash-tolerant recording. No GUI or serial dependency."""
from __future__ import annotations

import base64
import csv
import json
import math
import os
import platform
import time
import uuid
from datetime import datetime
from pathlib import Path

SCHEMA = "robonose.control_test.v2.1"
SOFTWARE_VERSION = "2.1.0"
ANALOG_NAMES = ("mq135_1", "mq3_1", "tgs2602", "mq3_2")
CHANNEL_MAP = dict(zip(("A0", "A1", "A2", "A3"), ANALOG_NAMES))
VALVE_AIR_PATH_MAP = {"OFF": "FILTERED_AIR", "ON": "SAMPLE"}
COUNT_FIELDS = tuple(f"{n}_count" for n in ANALOG_NAMES)
VOLTAGE_FIELDS = tuple(f"{n}_voltage_v" for n in ANALOG_NAMES)
ENV_FIELDS = ("temperature_c", "humidity_pct", "pressure_hpa", "bme688_gas_ohm")
VALUE_FIELDS = VOLTAGE_FIELDS + ENV_FIELDS
ERROR_FIELDS = tuple(f"ads_a{i}_error" for i in range(4)) + ("bme_error",)
FLAG_FIELDS = ("bme_new_data", "gas_valid", "heater_stable")
TIME_FIELDS = ("device_cycle_start_ms", "device_cycle_end_ms", "acquisition_duration_ms",
               "schedule_lag_ms", "skipped_intervals_total")
CONTROL_FIELDS = ("pump_pwm_pct", "pump_pwm_duty", "valve_energized", "valve_air_path_commanded", "failsafe_active",
                  "control_ready", "control_revision", "lease_remaining_ms")
CONTROL_BOOL_FIELDS = ("valve_energized", "failsafe_active", "control_ready", "control_changed_during_scan")
CONTROL_EVENT_FIELDS = ("host_received_at", "host_elapsed_s", "event", "request_id", "command",
                        "requested_value", "ok", "device_ms", "pump_pwm_pct", "pump_pwm_duty",
                        "valve_energized", "valve_air_path_commanded", "failsafe_active", "control_revision", "error")
CSV_FIELDS = ("host_received_at", "host_elapsed_s", "boot_id", "seq") + TIME_FIELDS + \
    COUNT_FIELDS + VOLTAGE_FIELDS + ENV_FIELDS + FLAG_FIELDS + ("bme_status_raw",) + \
    ERROR_FIELDS + CONTROL_FIELDS + ("control_revision_start", "control_changed_during_scan",
                                    "seq_gap_before", "order_flag", "quality_flags")
MAX_LINE_BYTES = 8192


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def write_json_atomic(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


class ProtocolError(ValueError):
    pass


def valve_air_path(energized) -> str | None:
    """Plumbing mapping from commanded coil state; no flow/position feedback."""
    if type(energized) is not bool:
        return None
    return VALVE_AIR_PATH_MAP["ON" if energized else "OFF"]


def _bad_constant(value):
    raise ProtocolError(f"Non-finite JSON number: {value}")


def parse_packet(raw: bytes) -> dict:
    if len(raw) > MAX_LINE_BYTES:
        raise ProtocolError("Serial line exceeds 8192 bytes")
    try:
        obj = json.loads(raw.decode("utf-8"), parse_constant=_bad_constant)
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError(f"Invalid JSON/UTF-8: {exc}") from exc
    if not isinstance(obj, dict):
        raise ProtocolError("Packet must be a JSON object")
    if obj.get("schema") != SCHEMA:
        raise ProtocolError(f"Wrong firmware/schema: expected {SCHEMA}")
    if obj.get("type") not in ("hello", "sample", "event", "ack"):
        raise ProtocolError("Unknown packet type")
    if not isinstance(obj.get("boot_id"), str) or not 1 <= len(obj["boot_id"]) <= 64:
        raise ProtocolError("Missing/invalid boot_id")
    if obj["type"] == "ack":
        if type(obj.get("request_id")) is not int or obj["request_id"] < 0 or type(obj.get("ok")) is not bool:
            raise ProtocolError("Invalid command acknowledgement")
        if not isinstance(obj.get("command"), str) or not isinstance(obj.get("error"), str):
            raise ProtocolError("Invalid acknowledgement command/error")
        for key in ("device_ms", "control_revision", "lease_remaining_ms", "pump_pwm_pct", "pump_pwm_duty"):
            if type(obj.get(key)) is not int or obj[key] < 0:
                raise ProtocolError(f"Invalid acknowledgement {key}")
        for key in ("valve_energized", "failsafe_active", "control_ready"):
            if type(obj.get(key)) is not bool:
                raise ProtocolError(f"Invalid acknowledgement {key}")
        if obj["pump_pwm_pct"] > 100 or obj["pump_pwm_duty"] > 1023:
            raise ProtocolError("Invalid acknowledgement PWM range")
    if obj["type"] != "sample":
        return obj
    for key in ("seq",) + TIME_FIELDS:
        if type(obj.get(key)) is not int or obj[key] < 0:
            raise ProtocolError(f"Missing/invalid integer {key}")
    if obj["device_cycle_end_ms"] < obj["device_cycle_start_ms"]:
        raise ProtocolError("Cycle ends before it starts")
    for key in COUNT_FIELDS + VALUE_FIELDS + ("bme_status_raw",):
        if key not in obj:
            raise ProtocolError(f"Missing field {key}")
        value = obj[key]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ProtocolError(f"Invalid number {key}")
    for key in COUNT_FIELDS:
        value = obj[key]
        if value is not None and (type(value) is not int or not -32768 <= value <= 32767):
            raise ProtocolError(f"Invalid ADC count {key}")
    if obj["bme_status_raw"] is not None and (
        type(obj["bme_status_raw"]) is not int or not 0 <= obj["bme_status_raw"] <= 255
    ):
        raise ProtocolError("Invalid BME status byte")
    for key in FLAG_FIELDS:
        if key not in obj or (obj[key] is not None and type(obj[key]) is not bool):
            raise ProtocolError(f"Missing/invalid flag {key}")
    for key in ERROR_FIELDS:
        if not isinstance(obj.get(key), str):
            raise ProtocolError(f"Missing/invalid error field {key}")
    for key in ("pump_pwm_pct", "pump_pwm_duty", "control_revision", "lease_remaining_ms", "control_revision_start"):
        if type(obj.get(key)) is not int or obj[key] < 0:
            raise ProtocolError(f"Missing/invalid output state {key}")
    if obj["pump_pwm_pct"] > 100 or obj["pump_pwm_duty"] > 1023:
        raise ProtocolError("Output PWM out of range")
    for key in CONTROL_BOOL_FIELDS:
        if type(obj.get(key)) is not bool:
            raise ProtocolError(f"Missing/invalid output flag {key}")
    return obj


class LineFramer:
    """Assemble partial reads; discard an oversized line until its newline."""
    def __init__(self):
        self.buffer = bytearray()
        self.discarding = False

    def feed(self, chunk: bytes) -> list[bytes]:
        out = []
        for part_index, part in enumerate(chunk.split(b"\n")):
            if part_index:
                if not self.discarding:
                    line = bytes(self.buffer).rstrip(b"\r")
                    if line:
                        out.append(line)
                self.buffer.clear()
                self.discarding = False
            if not self.discarding:
                self.buffer.extend(part)
                if len(self.buffer) > MAX_LINE_BYTES:
                    # Emit a bounded invalid frame for the error log, then resync.
                    out.append(bytes(self.buffer[:MAX_LINE_BYTES + 1]))
                    self.buffer.clear()
                    self.discarding = True
        return out


def quality_flags(packet: dict) -> list[str]:
    flags = []
    for i, name in enumerate(ANALOG_NAMES):
        value, count = packet[f"{name}_voltage_v"], packet[f"{name}_count"]
        error = packet[f"ads_a{i}_error"]
        if error:
            flags.append(f"a{i}:{error}")
        elif value is None or count is None:
            flags.append(f"a{i}:missing")
        elif abs(value - count * 0.0001875) > 0.000002:
            flags.append(f"a{i}:count_voltage_mismatch")
    if packet["bme_error"]:
        flags.append(f"bme:{packet['bme_error']}")
    if packet["bme_new_data"] is not True:
        flags.append("bme:no_new_data")
    if packet["gas_valid"] is not True:
        flags.append("bme:gas_invalid_or_unknown")
    if packet["heater_stable"] is not True:
        flags.append("bme:heater_unstable_or_unknown")
    if any(packet[k] is None for k in ENV_FIELDS):
        flags.append("bme:missing_value")
    if packet["control_changed_during_scan"]:
        flags.append("control:changed_during_scan")
    if packet["failsafe_active"]:
        flags.append("control:failsafe_active")
    return flags


def valid_value(packet: dict, field: str) -> bool:
    if packet.get(field) is None:
        return False
    if field in VOLTAGE_FIELDS:
        return not packet[ERROR_FIELDS[VOLTAGE_FIELDS.index(field)]]
    if packet["bme_error"] or packet["bme_new_data"] is not True:
        return False
    if field == "bme688_gas_ohm":
        return packet["gas_valid"] is True and packet["heater_stable"] is True
    return True


class RunningStats:
    def __init__(self):
        self.count = 0
        self.mean = self.m2 = self.minimum = self.maximum = 0.0

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        if self.count == 1:
            self.minimum = self.maximum = value
        else:
            self.minimum = min(self.minimum, value)
            self.maximum = max(self.maximum, value)

    def as_dict(self) -> dict:
        return {"valid_count": self.count,
                "min": self.minimum if self.count else None,
                "max": self.maximum if self.count else None,
                "mean": self.mean if self.count else None,
                "std_population": math.sqrt(max(0.0, self.m2 / self.count)) if self.count else None}


class SessionRecorder:
    """Owned by the acquisition thread while it is running; finalize after join."""
    def __init__(self, output: Path, mode: str, port: str | None = None,
                 note: str = "", sync_seconds: float = 5.0):
        stamp = datetime.now().astimezone()
        name = f"sensor_test_{stamp:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
        self.directory = output / f"{stamp:%Y-%m-%d}" / name
        self.directory.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.last_sync = self.started
        self.sync_seconds = sync_seconds
        self.sample_count = self.bad_samples = self.parse_errors = 0
        self.missing_seq = self.resets = self.out_of_order = 0
        self.last_boot = None
        self.last_seq = None
        self.stats = {key: RunningStats() for key in VALUE_FIELDS}
        self.error_counts: dict[str, int] = {}
        self.closed = False
        self.last_packet = None
        self.metadata = {"schema": SCHEMA, "software_version": SOFTWARE_VERSION,
                         "mode": mode, "status": "IN_PROGRESS", "started_at": iso_now(),
                         "port": port, "note": note, "python": platform.python_version(),
                         "firmware": None, "sample_unit": "one complete sequential sensor scan",
                         "actuator_control": True,
                         "channel_map": CHANNEL_MAP,
                         "valve_air_path_map": VALVE_AIR_PATH_MAP,
                         "valve_air_path_source": "user_confirmed_plumbing_2026-11-06",
                         "valve_air_path_feedback": "derived_from_commanded_coil_state",
                         "analog_measurement": "direct_AOUT_voltage_no_ppm_or_Rs_conversion",
                         "output_feedback": "commanded_state_not_measured_speed_flow_or_valve_position",
                         "shutdown_all_off_acknowledged": False}
        write_json_atomic(self.directory / "metadata.json", self.metadata)
        self.csv_file = (self.directory / "samples.csv").open("w", newline="", encoding="utf-8-sig")
        self.writer = csv.DictWriter(self.csv_file, fieldnames=CSV_FIELDS)
        self.writer.writeheader()
        self.raw_file = (self.directory / "raw_serial.jsonl").open("w", encoding="utf-8")
        self.events_file = (self.directory / "events.jsonl").open("w", encoding="utf-8")
        self.bytes_file = (self.directory / "serial_bytes.bin").open("wb")
        self.control_file = (self.directory / "control_events.csv").open("w", newline="", encoding="utf-8-sig")
        self.control_writer = csv.DictWriter(self.control_file, fieldnames=CONTROL_EVENT_FIELDS)
        self.control_writer.writeheader()
        self.event("session_started", mode=mode)

    def event(self, code: str, **details) -> None:
        self.events_file.write(json.dumps({"host_received_at": iso_now(), "code": code, **details},
                                         ensure_ascii=False, allow_nan=False) + "\n")
        self.events_file.flush()

    def transport(self, chunk: bytes) -> None:
        # Exact transport bytes include boot chatter and malformed/oversized lines.
        self.bytes_file.write(chunk)

    def control_event(self, code: str, **details) -> None:
        row = {"host_received_at": iso_now(), "host_elapsed_s": round(time.monotonic() - self.started, 6),
               "event": code, **details}
        row["valve_air_path_commanded"] = valve_air_path(row.get("valve_energized"))
        self.control_writer.writerow({key: row.get(key) for key in CONTROL_EVENT_FIELDS})
        self.control_file.flush()
        self.event(code, **details)

    def receive(self, raw: bytes) -> dict | None:
        self.last_packet = None
        received = iso_now()
        elapsed = time.monotonic() - self.started
        self.raw_file.write(json.dumps({"host_received_at": received, "host_elapsed_s": elapsed,
                                      "raw_b64": base64.b64encode(raw).decode("ascii"),
                                      "text": raw.decode("utf-8", errors="replace")},
                                     ensure_ascii=False, allow_nan=False) + "\n")
        try:
            packet = parse_packet(raw)
        except ProtocolError as exc:
            self.parse_errors += 1
            self.event("parse_error", error=str(exc), raw_preview=raw[:200].decode("utf-8", "replace"))
            self.sync()
            return None
        self.last_packet = packet
        if packet["type"] == "hello":
            self.metadata["firmware"] = packet
            write_json_atomic(self.directory / "metadata.json", self.metadata)
            self.event("firmware_info", packet=packet)
            self.sync()
            return None
        if packet["type"] == "event":
            self.event("device_event", packet=packet)
            if "pump_pwm_pct" in packet:
                self.control_event("device_event:" + packet.get("code", "unknown"),
                                   **{k: packet.get(k) for k in CONTROL_EVENT_FIELDS if k not in ("event", "host_received_at", "host_elapsed_s")})
            self.sync()
            return None
        if packet["type"] == "ack":
            self.control_event("device_ack", **{key: packet.get(key) for key in CONTROL_EVENT_FIELDS
                                               if key not in ("event", "host_received_at", "host_elapsed_s")})
            self.sync()
            return None
        gap, order = 0, "ok"
        boot, seq = packet["boot_id"], packet["seq"]
        if boot != self.last_boot:
            if self.last_boot is not None:
                self.resets += 1
                order = "new_boot"
                self.event("device_boot_changed", previous=self.last_boot, current=boot)
            self.last_boot, self.last_seq = boot, None
        if self.last_seq is not None:
            if seq <= self.last_seq:
                self.out_of_order += 1
                order = "duplicate_or_out_of_order"
                self.event("sequence_order", previous=self.last_seq, current=seq)
            else:
                gap = seq - self.last_seq - 1
                self.missing_seq += gap
                if gap:
                    self.event("sequence_gap", missing=gap, previous=self.last_seq, current=seq)
        self.last_seq = max(seq, self.last_seq) if self.last_seq is not None else seq
        flags = quality_flags(packet)
        if order != "ok":
            flags.append(order)
        if gap:
            flags.append(f"sequence_gap:{gap}")
        row = {key: packet.get(key) for key in CSV_FIELDS}
        row.update(host_received_at=received, host_elapsed_s=round(elapsed, 6),
                   valve_air_path_commanded=valve_air_path(packet["valve_energized"]),
                   seq_gap_before=gap, order_flag=order, quality_flags=";".join(flags))
        self.writer.writerow(row)
        self.sample_count += 1
        self.bad_samples += bool(flags)
        for flag in flags:
            self.error_counts[flag] = self.error_counts.get(flag, 0) + 1
        for key in VALUE_FIELDS:
            if valid_value(packet, key):
                self.stats[key].add(float(packet[key]))
        self.sync()
        # Private UI timestamp is never included in the CSV.
        row["_received_monotonic"] = time.monotonic()
        return row

    def sync(self, force: bool = False) -> None:
        files = (self.csv_file, self.raw_file, self.events_file, self.bytes_file, self.control_file)
        for f in files:
            f.flush()
        if force or time.monotonic() - self.last_sync >= self.sync_seconds:
            for f in files:
                os.fsync(f.fileno())
            self.last_sync = time.monotonic()

    def finalize(self, reason: str) -> dict:
        if self.closed:
            return self.metadata
        report = {"mode": self.metadata["mode"], "stop_reason": reason,
                  "sample_count": self.sample_count, "samples_with_flags": self.bad_samples,
                  "parse_errors": self.parse_errors, "missing_sequence_numbers": self.missing_seq,
                  "device_boot_changes": self.resets, "duplicate_or_out_of_order": self.out_of_order,
                  "elapsed_s": round(time.monotonic() - self.started, 3),
                  "shutdown_all_off_acknowledged": self.metadata["shutdown_all_off_acknowledged"],
                  "quality_flag_counts": self.error_counts,
                  "values": {key: value.as_dict() for key, value in self.stats.items()},
                  "note": "Raw CSV retains invalid gas values. Gas statistics exclude invalid/unstable gas."
                  }
        self.event("session_finished", reason=reason)
        self.sync(force=True)
        write_json_atomic(self.directory / "summary.json", report)
        self.metadata.update(status="STOPPED" if reason in ("user_stop", "duration_reached") else "ERROR",
                             stopped_at=iso_now(), stop_reason=reason, sample_count=self.sample_count)
        write_json_atomic(self.directory / "metadata.json", self.metadata)
        for f in (self.csv_file, self.raw_file, self.events_file, self.bytes_file, self.control_file):
            f.close()
        self.closed = True
        return report


def demo_hello(interval: float = 1.0) -> dict:
    return {"type": "hello", "schema": SCHEMA, "boot_id": "SIMULATED",
            "firmware_version": SOFTWARE_VERSION, "device_id": "SIMULATED",
            "hardware_revision": "SIMULATED_NOT_HARDWARE", "sample_interval_ms": round(interval * 1000),
            "channel_map": "A0=mq135_1,A1=mq3_1,A2=tgs2602,A3=mq3_2",
            "valve_off_air_path": "FILTERED_AIR", "valve_on_air_path": "SAMPLE",
            "ads_fsr_v": 6.144, "ads_lsb_v": 0.0001875, "divider_factor": 1,
            "bme_sda": 8, "bme_scl": 9, "ads_sda": 10, "ads_scl": 11,
            "bme_address": 119, "ads_address": 72, "actuator_control": True, "control_protocol": 1,
            "control_ready": True, "pump_pin": 5, "valve_pin": 4, "control_timeout_ms": 15000,
            "pump_pwm_hz": 1000, "pump_pwm_bits": 10, "pump_active_high": True, "valve_active_high": True}


def demo_sample(seq: int, elapsed: float | None = None, faults: bool = False) -> dict:
    t = float(seq if elapsed is None else elapsed)
    packet = {"type": "sample", "schema": SCHEMA, "boot_id": "SIMULATED", "seq": seq,
              "device_cycle_start_ms": max(0, round(t * 1000) - 163), "device_cycle_end_ms": round(t * 1000),
              "acquisition_duration_ms": min(163, round(t * 1000)), "schedule_lag_ms": 0, "skipped_intervals_total": 0}
    for i, name in enumerate(ANALOG_NAMES):
        volts = (0.48, 0.91, 0.72, 1.30)[i] + 0.03 * math.sin(t / (15 + i * 4) + i)
        count = round(volts / 0.0001875)
        packet[f"{name}_count"] = count
        packet[f"{name}_voltage_v"] = round(count * 0.0001875, 6)
        packet[f"ads_a{i}_error"] = ""
    packet.update(temperature_c=round(32.5 + 0.2 * math.sin(t / 38), 3),
                  humidity_pct=round(65.1 + 0.5 * math.cos(t / 30), 3),
                  pressure_hpa=round(1010.5 + 0.2 * math.sin(t / 55), 3),
                  bme688_gas_ohm=round(42000 + 1500 * math.sin(t / 22), 3),
                  bme_new_data=True, gas_valid=True, heater_stable=True,
                  bme_status_raw=0xB0, bme_error="")
    if faults and seq % 37 == 10:
        packet["mq135_1_count"] = packet["mq135_1_voltage_v"] = None
        packet["ads_a0_error"] = "i2c_conversion_read_failed"
    if faults and seq % 47 in (15, 16):
        packet.update(gas_valid=False, heater_stable=False, bme_status_raw=0x80)
    packet.update(pump_pwm_pct=0, pump_pwm_duty=0, valve_energized=False, failsafe_active=False,
                  control_ready=True, control_revision=0, control_revision_start=0,
                  control_changed_during_scan=False, lease_remaining_ms=15000)
    return packet

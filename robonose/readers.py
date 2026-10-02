"""Hardware imports live inside hardware constructors, never in sim/doctor."""
import ctypes
import hashlib
import math
from pathlib import Path
import random
import time
from importlib.metadata import version, PackageNotFoundError
from .schema import blank_sample, iso_now

FSR = {2/3: 6.144, 1: 4.096, 2: 2.048, 4: 1.024, 8: .512, 16: .256}
RATES = (8, 16, 32, 64, 128, 250, 475, 860)
GAINS = (2/3, 1, 2, 4, 8, 16)

def package_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None

def timing(row, name, operation, run_start):
    start = time.monotonic()
    row[name + "_read_started_at"] = iso_now()
    row[name + "_read_elapsed_s"] = start - run_start
    try:
        row.update(operation())
        row.setdefault(name + "_status", "OK")
        if row[name + "_status"] is None:
            row[name + "_status"] = "OK"
        if row[name + "_fresh"] is None:
            row[name + "_fresh"] = True
        nonfinite = [k for k, value in row.items() if isinstance(value, float) and not math.isfinite(value)]
        if nonfinite:
            for key in nonfinite:
                row[key] = None
            row[name + "_status"] = "ERROR"
            row[name + "_error"] = "Driver trả giá trị không hữu hạn: " + ", ".join(nonfinite)
            row[name + "_fresh"] = False
    except Exception as exc:
        row[name + "_status"] = "ERROR"
        row[name + "_error"] = f"{type(exc).__name__}: {exc}"
        row[name + "_fresh"] = False
    row[name + "_read_duration_s"] = time.monotonic() - start

class SimReader:
    def __init__(self, cfg, fail_every=0):
        self.cfg, self.rng = cfg, random.Random(cfg["seed"])
        self.started = time.monotonic()
        self.effect, self.index, self.fail_every = 0., 0, fail_every
        self.applied = {"backend": "sim", "seed": cfg["seed"], "hardware_access": False,
                        "simulated_hardware": cfg["hardware"], "driver": "RoboNose deterministic sim 1.0"}

    def read(self, phase, run_start):
        self.index += 1
        self.effect += ((1. if phase == "EXPOSURE" else 0.) - self.effect) * .22
        row = blank_sample()
        def bme():
            if self.fail_every and self.index % self.fail_every == 0:
                raise OSError("Lỗi BME mô phỏng")
            return {"temperature_c": 26 + self.rng.uniform(-.05, .05), "humidity_pct": 55 + self.effect,
                "pressure_hpa": 1008 + self.rng.uniform(-.1, .1),
                "gas_resistance_ohm": 100000 * (1 - .45 * self.effect) + self.rng.uniform(-100, 100),
                "gas_valid": True, "heater_stable": True, "new_data": True,
                "bme_status_bits": 0xB0, "bme_meas_index": self.index % 256}
        timing(row, "bme", bme, run_start)
        for sensor, base, scale in (("mq135", 10000, 6000), ("mq3", 7000, 9000)):
            count = int(base + scale * self.effect + self.rng.uniform(-20, 20))
            def adc(sensor=sensor, count=count):
                voltage = count * FSR[self.cfg["hardware"]["ads_gain"]] / 32768
                factor = self.cfg["hardware"][sensor + "_divider_factor"]
                return {sensor + "_adc_count": count, sensor + "_voltage_v": voltage,
                        sensor + "_ao_voltage_v": voltage * factor if factor is not None else None}
            timing(row, sensor, adc, run_start)
        return row

    def close(self):
        pass

class BMEResult(ctypes.Structure):
    _fields_ = [(k, ctypes.c_double) for k in ("temperature", "pressure_pa", "humidity", "gas_ohm")] + [
        (k, ctypes.c_ubyte) for k in ("status", "index", "gas_index", "res_heat", "idac", "gas_wait")]

class BoschBME:
    def __init__(self, h):
        path = Path(__file__).parent / "native/librobonose_bme.so"
        if not path.exists():
            raise RuntimeError("Thiếu Bosch bridge: chạy .venv/bin/python -m robonose.build_driver")
        self.lib = ctypes.CDLL(str(path))
        self.lib.rn_open.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
        self.lib.rn_open.restype = ctypes.c_void_p
        self.lib.rn_close.argtypes = [ctypes.c_void_p]
        self.lib.rn_close.restype = None
        self.lib.rn_config.argtypes = [ctypes.c_void_p] + [ctypes.c_int] * 5
        self.lib.rn_config.restype = ctypes.c_int
        self.lib.rn_read.argtypes = [ctypes.c_void_p, ctypes.POINTER(BMEResult)]
        self.lib.rn_read.restype = ctypes.c_int
        self.lib.rn_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)]
        self.lib.rn_info.restype = ctypes.c_int
        code = ctypes.c_int()
        self.ptr = self.lib.rn_open(h["i2c_bus"], h["bme_address"], ctypes.byref(code))
        if not self.ptr:
            raise RuntimeError(f"BME688 init lỗi {code.value}; -101 = không phải gas-high BME688; -1000-errno = lỗi mở I2C")
        try:
            oscode = {1: 1, 2: 2, 4: 3, 8: 4, 16: 5}
            self.check(self.lib.rn_config(self.ptr, oscode[h["temperature_oversampling"]],
                oscode[h["humidity_oversampling"]], oscode[h["pressure_oversampling"]], h["heater_c"], h["heater_ms"]))
            info = (ctypes.c_int * 5)()
            self.check(self.lib.rn_info(self.ptr, info))
            gw = info[3]
            self.applied = {"driver": "Bosch BME68x SensorAPI v4.4.8", "chip_id": info[0], "variant_id": info[1],
                "mode": "FORCED", "filter": "OFF", "odr": "NONE", "ambient_temperature_for_heater_c": 25,
                "temperature_oversampling": h["temperature_oversampling"],
                "humidity_oversampling": h["humidity_oversampling"], "pressure_oversampling": h["pressure_oversampling"],
                "heater_target_c": h["heater_c"], "heater_requested_ms": h["heater_ms"],
                "heater_programmed_ms": (gw & 63) * 4 ** (gw >> 6), "res_heat_register": info[2],
                "gas_wait_register": gw, "conversion_wait_s": info[4] / 1e6,
                "library_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        except BaseException:
            self.close()
            raise

    @staticmethod
    def check(code):
        if code:
            raise RuntimeError(f"Bosch SensorAPI code={code}")

    def read(self):
        result = BMEResult()
        code = self.lib.rn_read(self.ptr, ctypes.byref(result))
        if code == 2:
            return {"bme_status": "STALE", "bme_error": "Bosch W_NO_NEW_DATA", "bme_fresh": False, "new_data": False}
        self.check(code)
        status = result.status
        fresh = bool(status & 0x80)
        values = {"temperature_c": result.temperature, "humidity_pct": result.humidity,
            "pressure_hpa": result.pressure_pa / 100, "gas_resistance_ohm": result.gas_ohm,
            "gas_valid": bool(status & 0x20), "heater_stable": bool(status & 0x10), "new_data": fresh,
            "bme_status_bits": status, "bme_meas_index": result.index, "bme_gas_index": result.gas_index,
            "bme_res_heat": result.res_heat, "bme_idac": result.idac, "bme_gas_wait": result.gas_wait,
            "bme_fresh": fresh, "bme_status": "OK" if fresh else "STALE"}
        if not fresh:
            for key in ("temperature_c", "humidity_pct", "pressure_hpa", "gas_resistance_ohm"):
                values[key] = None
            values["bme_error"] = "Không có phép đo mới"
        return values

    def close(self):
        if self.ptr:
            self.lib.rn_close(self.ptr)
            self.ptr = None

class ADS1115:
    """Single-shot ADC; configuration readback, bounded ready polling, one count read."""
    def __init__(self, bus, h):
        self.bus, self.h = bus, h
        self.addr = h["ads_address"]

    def write_reg(self, reg, value):
        from smbus2 import i2c_msg
        self.bus.i2c_rdwr(i2c_msg.write(self.addr, [reg, value >> 8, value & 255]))

    def read_reg(self, reg):
        from smbus2 import i2c_msg
        reply = i2c_msg.read(self.addr, 2)
        self.bus.i2c_rdwr(i2c_msg.write(self.addr, [reg]), reply)
        a, b = list(reply)
        return a * 256 + b

    def read(self, sensor):
        channel = self.h[sensor + "_channel"]
        config = (0x8000 | ((4 + channel) << 12) | (GAINS.index(self.h["ads_gain"]) << 9)
                  | 0x100 | (RATES.index(self.h["ads_data_rate"]) << 5) | 3)
        self.write_reg(1, config)
        deadline = time.monotonic() + 2 / self.h["ads_data_rate"] + .1
        while True:
            applied = self.read_reg(1)
            if (applied & 0x7fff) != (config & 0x7fff):
                raise RuntimeError("ADS1115 config readback khác cấu hình yêu cầu")
            if applied & 0x8000:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("ADS1115 conversion timeout")
            time.sleep(min(.002, 1 / self.h["ads_data_rate"]))
        count = self.read_reg(0)
        if count >= 32768:
            count -= 65536
        voltage = count * FSR[self.h["ads_gain"]] / 32768
        factor = self.h[sensor + "_divider_factor"]
        return {sensor + "_adc_count": count, sensor + "_voltage_v": voltage,
                sensor + "_ao_voltage_v": voltage * factor if factor is not None else None}

class HardwareReader:
    def __init__(self, cfg):
        from smbus2 import SMBus
        self.started = time.monotonic()
        self.bus = None
        self.bme = BoschBME(cfg["hardware"])
        try:
            self.bus = SMBus(cfg["hardware"]["i2c_bus"])
            self.ads = ADS1115(self.bus, cfg["hardware"])
            # Verify one conversion per channel at initialization, before reporting applied ADC config.
            for sensor in ("mq135", "mq3"):
                self.ads.read(sensor)
            self.applied = {"backend": "hardware", "bme": self.bme.applied,
                "ads": {"driver": "RoboNose ADS1115 register driver 1.0", "smbus2": package_version("smbus2"),
                    "mode": "single-shot", "gain": cfg["hardware"]["ads_gain"],
                    "data_rate_sps": cfg["hardware"]["ads_data_rate"], "configuration_readback": True},
                "hardware": cfg["hardware"]}
        except BaseException:
            self.close()
            raise

    def read(self, phase, run_start):
        row = blank_sample()
        timing(row, "bme", self.bme.read, run_start)
        for sensor in ("mq135", "mq3"):
            timing(row, sensor, lambda s=sensor: self.ads.read(s), run_start)
        return row

    def close(self):
        self.bme.close()
        if self.bus is not None:
            self.bus.close()
            self.bus = None

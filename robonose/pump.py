class Pump:
    def __init__(self, config, backend="sim", factory=None):
        self.enabled = config["enabled"] and backend == "hardware"
        self.device = None
        self.commanded = "DISABLED"
        if self.enabled:
            if not config["confirmed"] or type(config["gpio_bcm"]) is not int or type(config["active_high"]) is not bool:
                raise ValueError("Thiếu GPIO/cực tính bơm đã xác nhận")
            if factory is None:
                from gpiozero import OutputDevice
                from gpiozero.pins.lgpio import LGPIOFactory
                factory = lambda **kw: OutputDevice(pin_factory=LGPIOFactory(), **kw)
            self.device = factory(pin=config["gpio_bcm"], active_high=config["active_high"], initial_value=False)
            self.commanded = "OFF"

    def set(self, on):
        if not self.enabled:
            raise ValueError("Điều khiển bơm disabled (sim luôn disabled)")
        # Update only after successful command; never claim physical feedback.
        try:
            self.device.on() if on else self.device.off()
        except Exception:
            self.commanded = "UNKNOWN"
            raise
        self.commanded = "ON" if on else "OFF"

    def off_best_effort(self):
        if self.device is None:
            return None
        try:
            self.set(False)
            return None
        except Exception as exc:
            return str(exc)

    def close(self):
        error = self.off_best_effort()
        if self.device:
            try:
                self.device.close()
            except Exception as exc:
                error = error or str(exc)
        return error

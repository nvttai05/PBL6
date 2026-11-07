"""Queued output requests. One acquisition thread owns serial; UI only submits."""
from __future__ import annotations
import threading
import time
from collections import deque


class ControlLink:
    def __init__(self):
        self.lock = threading.RLock()
        self.queue = deque()
        self.pending = {}
        self.next_id = 1
        self.boot = None
        self.capable = False
        self.synced = False
        self.latched = False
        self.message = "Waiting for v2.1 firmware / initial ALL OFF acknowledgement"
        self.confirmed = {}
        self.last_state_ms = -1
        self.last_rx = 0.0
        self.last_live_rx = 0.0
        self.initial_sync_started = False

    def _enqueue(self, command, value=None):
        request = {"request_id": self.next_id, "command": command, "requested_value": value}
        self.next_id += 1
        if command == "ALL_OFF":
            self.queue.clear()
            self.pending.clear()
            self.queue.appendleft(request)
        else:
            self.queue.append(request)
        return request["request_id"]

    def request(self, command: str, value=None) -> bool:
        with self.lock:
            if command not in ("PUMP", "VALVE", "ALL_OFF"):
                raise ValueError("Unknown output command")
            if command == "PUMP" and (type(value) is not int or not 0 <= value <= 100):
                raise ValueError("Pump PWM must be an integer 0..100")
            if command == "VALVE" and (type(value) is not int or value not in (0, 1)):
                raise ValueError("Valve must be 0 or 1")
            if command != "ALL_OFF" and not self.enabled():
                self.message = "Controls locked: wait for firmware; use ALL OFF to re-sync after a fault"
                return False
            if command != "ALL_OFF" and len(self.queue) >= 16:
                self.message = "Command queue full; use ALL OFF"
                return False
            self._enqueue(command, value)
            self.message = f"{command} {'' if value is None else value}: queued, waiting for device ACK"
            return True

    def enabled(self):
        return (self.capable and self.synced and not self.latched and self.confirmed.get("control_ready") is True
                and time.monotonic() - self.last_live_rx < 4)

    def suspend(self, message: str):
        with self.lock:
            self.latched = True
            self.synced = False
            self._enqueue("ALL_OFF")
            self.message = message

    def next_wire(self, now: float):
        with self.lock:
            timed_out = any(now - request["sent_at"] > 3 for request in self.pending.values())
            if timed_out:
                self.latched = True
                self.synced = False
                self.pending.clear()
                self._enqueue("ALL_OFF")
                self.message = "Output command ACK timed out; ALL OFF requested"
            if not self.queue:
                return None
            # Only one output mutation in flight, except ALL OFF which preempts it.
            if self.pending and self.queue[0]["command"] != "ALL_OFF":
                return None
            request = dict(self.queue.popleft())
            request["sent_at"] = now
            self.pending[request["request_id"]] = request
            arg = "" if request["requested_value"] is None else f" {request['requested_value']}"
            wire = f"@{request['request_id']} {request['command']}{arg}\n".encode("ascii")
            return wire, request

    def ping_wire(self):
        with self.lock:
            request_id = self.next_id; self.next_id += 1
            return f"@{request_id} PING\n".encode("ascii")

    def on_packet(self, packet, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self.last_rx = now
            self.last_live_rx = time.monotonic()
            boot = packet["boot_id"]
            new_boot = self.boot is not None and self.boot != boot
            if new_boot:
                self.queue.clear(); self.pending.clear()
                self.latched = True; self.synced = False; self.capable = False
                self.confirmed.clear(); self.last_state_ms = -1
                self.message = "Device rebooted; outputs start OFF. Press ALL OFF to re-sync."
            first_hello = packet["type"] == "hello" and not self.initial_sync_started
            self.boot = boot
            if packet["type"] == "hello":
                self.capable = packet.get("actuator_control") is True and packet.get("control_protocol") == 1
                if first_hello and self.capable:
                    self.initial_sync_started = True
                    self.synced = False
                    self._enqueue("ALL_OFF")
            stamp = packet.get("device_ms", packet.get("device_cycle_end_ms", packet.get("uptime_ms", 0)))
            if all(key in packet for key in ("pump_pwm_pct", "valve_energized", "control_ready")) and stamp >= self.last_state_ms:
                self.last_state_ms = stamp
                self.confirmed = {key: packet.get(key) for key in (
                    "pump_pwm_pct", "pump_pwm_duty", "valve_energized", "failsafe_active",
                    "control_ready", "control_revision")}
                self.confirmed["received_at"] = now
            if packet["type"] == "ack":
                request = self.pending.get(packet["request_id"])
                if request is not None and packet["command"] == request["command"]:
                    self.pending.pop(packet["request_id"])
                    matches = ((request["command"] == "PUMP" and packet["pump_pwm_pct"] == request["requested_value"])
                               or (request["command"] == "VALVE" and packet["valve_energized"] == bool(request["requested_value"]))
                               or (request["command"] == "ALL_OFF" and packet["pump_pwm_pct"] == 0 and not packet["valve_energized"]))
                    if packet["ok"] and matches:
                        if packet["command"] == "ALL_OFF":
                            self.synced = True; self.latched = False
                        self.message = f"ACK: {packet['command']} applied by firmware (commanded state)"
                    else:
                        self.latched = True; self.synced = False
                        self._enqueue("ALL_OFF")
                        self.message = "Device rejected command or ACK state mismatch: " + packet["error"]
            if packet.get("failsafe_active") is True:
                self.latched = True; self.synced = False
                self.message = "Firmware watchdog tripped: outputs OFF. Press ALL OFF to re-sync."

    def snapshot(self):
        with self.lock:
            return {"enabled": self.enabled(), "message": self.message,
                    "confirmed": dict(self.confirmed), "pending": bool(self.pending or self.queue),
                    "last_rx": self.last_rx, "last_live_rx": self.last_live_rx}

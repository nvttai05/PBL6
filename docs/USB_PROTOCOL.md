# USB dataset protocol v1

Firmware kind `robonose_dataset_s3`, version `3.0.0`; wire **`robonose.usb.v1`**; CSV schema **`robonose.dataset.v1`**. ControlTest 2.1 is a historical reference, not a compatible protocol. Hardware has one phase/deadline owner: the MCU. Host hardware code projects `DeviceState` and never runs the simulation StateMachine.

## Framing

Device → host: UTF-8 flat JSON + LF. Firmware emits fewer than 8192 bytes including LF; host allows at most 8191 payload bytes plus LF. Oversized frames are discarded through LF. Invalid UTF-8/JSON, duplicate keys, NaN/Infinity, arrays and boot chatter become parser events, never samples. Original RX/TX bytes are preserved losslessly as hex chunks in `session/wire.jsonl`, with direction/host monotonic time. Parser resynchronizes at LF; absence of valid telemetry causes the receive timeout.

Recognized plain console fatal messages (`Guru Meditation Error:`, brownout,
assertion and corrupt heap) instead produce an internal `device_fault` with
source `usb_plain_text`. Detection also works after a truncated JSON prefix;
valid JSON containing that text remains JSON. The serial owner immediately
latches the MCU cause and requests bounded emergency OFF. Subsequent register,
backtrace and ROM lines stay in wire without flooding the event queue. Repeated
fatal headers remain visible; valid JSON restores normal parsing. This is host
diagnostic handling, not a new MCU wire command or an acknowledged OFF.

Each frame in a read chunk is processed independently. A protocol fault latches the session error but does not discard later frames in that same chunk, including a valid OFF ACK. A fault first discovered during shutdown still makes the session ERROR even if commanded OFF is acknowledged.

Failed host writes also produce a best-effort TX record: `bytes_hex` contains
only a driver-confirmed prefix, while `attempted_bytes_hex` is the requested
packet. `accepted_bytes` is null if an exception leaves the count unknown;
`requested_bytes`, `write_outcome` and `error` explain the failure. A successful
driver write alone does not confirm device receipt or physical OFF. The final
terminal line includes the session fault reason; unacknowledged OFF and the
last reported PWM must be interpreted as an unconfirmed current device state.

Host → device: bounded ASCII, normally fewer than 192 bytes including LF. Firmware bounds tokens, identifiers, 32-bit positive request IDs, integer durations and input control bytes. Names/notes remain host UTF-8 metadata; START sends only the trial UUID. No arbitrary PWM/GPIO command exists.

```text
HELLO
@<id> <boot> <session_uuid> BEGIN <begin_ticket>
@<id> <boot> <session_uuid> START <trial_uuid>
@<id> <boot> <session_uuid> EXPOSE
@<id> <boot> <session_uuid> RECOVER
@<id> <boot> <session_uuid> EXTEND <milliseconds>
@<id> <boot> <session_uuid> FINISH
@<id> <boot> <session_uuid> ABORT
@<id> <boot> <session_uuid> NEXT
@<id> <boot> <session_uuid> MARK
@<id> <boot> <session_uuid> STATUS
@<id> <boot> <session_uuid> PING
@<id> <boot> <session_uuid> OFF
@<id> <boot> <session_uuid> FAULT
ALL_OFF
```

OFF/FAULT bypass boot/session/ID checks and the normal RX queue. OFF ends a clean session; FAULT/emergency ALL_OFF latch error. Unbound ALL_OFF is a last best effort and cannot provide a normal correlated OFF ACK.

## Handshake and automatic BEGIN

1. MCU boot/reset sets commanded outputs OFF before USB/sensors/tasks. Serial Monitor/HELLO alone cannot start the pump.
2. HELLO reports firmware/protocol/schema, boot/device IDs/reset reason, channel map, ADS FSR/LSB/divider/mode/rate/VDD requested, I2C pins/address/timeouts, BME profile/chip/variant/requested/applied/readback, output pins/PWM settings/readiness/OFF and a one-use begin_ticket.
3. Host requires exactly `A0=tgs2602,A1=mq3_1,A2=mq135_2,A3=mq3_2`, ±6.144 V, 0.0001875 V/count, divider 1, 128 SPS and the agreed pins/routes. BME requested is 300°C/100 ms T2/H2/P4; applied oversampling/heater wait and readback registers are recorded. Requested °C is not a measured heater temperature; Pi profile and production_profile=null remain distinct.
4. Host creates logs, records a fresh healthy preflight scan and waits until that seq has been **written and synced**, then sends BEGIN automatically with its session UUID/ticket. No Start Session or pump opt-in is added.
5. BEGIN consumes the ticket, commands SAMPLE/80% and MONITOR. A new clean host session requires a new HELLO/ticket/session UUID; old BEGIN replay cannot create an ON effect. Latched MCU faults require reset/readiness verification; heartbeat/reconnect cannot revive outputs.

Full HELLO is metadata. Configuration hash excludes connection ticket/boot/time/session identity and includes requested/applied measurement settings. Board/flash/PSRAM are never inferred from this handshake.

The current fix identifies itself in HELLO as
`firmware_revision="usb_irq_handoff.v3"`, retaining firmware version 3.0.0
and the v1 wire/CSV schema. It includes the earlier watchdog timing and IDF
stream fixes. Hardware `info` displays revision, actual serial transport,
initialization status and IRQ snapshots so the loaded build can be checked.

For CDC-on/USBMode=hwcdc, firmware installs the existing ESP-IDF USB Serial/JTAG
driver with 16384-byte TX and 1024-byte RX buffers. It does not call Arduino
HWCDC Serial.begin or share that peripheral's ISR with it. TX is single-owner,
sends at most 64 bytes per write with up to 20 ms per driver call and a 1 s
frame/drain budget. Exact accepted counts advance the frame offset. A failure
requests output-owner OFF and adds an LF before a later frame to resynchronize.
UART and USB-OTG remain separate compile-time paths; UART is covered by the
CDC-off build. The HELLO serial buffer fields are explicitly requested values;
the IDF path applies them on successful driver installation.

Before installing that driver, firmware snapshots the native USB enabled and
pending interrupt masks, disables inherited IRQ enables, and clears unsupported
pending bits. It preserves pending RX/TX bits so the first stream transfer is
not lost. The installed ISR services RX (0x4) and TX (0x8) only; an inherited
enabled BUS_RESET (0x200) must not reach it. Firmware refuses an already
installed driver without changing its registers. No Arduino core/SDK patch or
watchdog relaxation is used.

HELLO fields `serial_irq_diagnostics_available`, `serial_irq_enabled_before`,
`serial_irq_pending_before`, `serial_irq_enabled_after_init` and
`serial_irq_owned_mask` describe this initialization snapshot. Native IDF owns
0xC (12); the initial enabled mask is normally RX-only 0x4. Runtime TX enables
are dynamic, so this snapshot is not a live register measurement. Host v3
handshake requires diagnostics, RX enabled and no enabled bits outside 0xC;
otherwise it refuses BEGIN. UART/OTG report diagnostics unavailable. These
fields do not identify physical flash/PSRAM or guarantee electrical USB health.

## ACK, events, retry and context

ACK fields: type, request_id, accepted/reason, applied_ms, barrier_seq and state snapshot: phase, context_epoch, segment_id, phase_started_ms, deadline_ms/null, trial_id/null/index/status, PWM, valve, air_path_commanded. `device_ms` is serialization time; applied_ms is command effect time. Acceptance is not reported before ACK. Invalid commands leave route/deadline unchanged apart from natural timer expiry.

Correlated ACKs require a positive 32-bit integer request_id, boolean accepted, string reason and nonnegative integer applied_ms/barrier_seq. applied_ms cannot be later than device_ms. Ordinary ACKs and active telemetry require the exact host session UUID; empty/missing session IDs are not active-session wildcards. Idle preflight and old idle uncorrelated ACKs retain their documented exception. During priority OFF, terminal CLOSED/ERROR events and the correlated OFF ACK may report the MCU's preceding/unbound session, because OFF itself bypasses that scope; boot identity and OFF output/context checks still apply.

One ordinary request is in flight. Default timeout 0.8 s, one identical-byte/ID retry. MCU caches 16 results per session namespace: exact repeats return the original ACK without another transition/ON pulse; changed ID content and expired IDs are rejected. A new ID namespace requires a valid fresh BEGIN ticket. Old boot/session commands are refused; OFF remains prioritized.

Phase events report previous_phase/previous_trial_id, new snapshot, effective_ms, processed_ms and barrier_seq. Timed phases end at their actual monotonic deadline then remain WAIT. START/EXPOSE/RECOVER/EXTEND/FINISH/ABORT/NEXT are MCU decisions. Name/notes update host metadata only in MCU-reported WAIT_NAME. MARK text stays host-side; its marker uses ACK applied_ms, not receive time.

Patched state snapshots also report optional `fault_reason` (null or a string
of at most 63 characters). The MCU retains the first latched reason, such as
`lease_expired`, `usb_task_stalled_or_queue_full`, or `required_sensor_failure`;
a subsequent host FAULT does not overwrite it. Host phase-event logs and final
session fault text preserve it. Older frames without this field remain valid;
their exact MCU stop branch cannot be recovered from a generic ERROR alone.

A scan job captures immutable phase/trial/output context. Old-epoch, new-seq samples completing after a newer ACK remain in raw, but cannot roll current UI state backward. Duplicate phase events are logged/ignored; missing phase epochs/unannounced sample context fault instead of inventing phase intervals.

barrier_seq identifies the latest scan issued at a transition. Host postpones trial export finalization/analysis until all scans through that watermark are ingested, including a scan finishing after NEXT ACK. OFF does not wait for I2C. Shutdown waits finitely for its ACK **and** outstanding scan watermark, then reports missing confirmation/drain rather than inventing a sample or stop.

## Samples and canonical v1 adapter

Telemetry continues at 1 Hz through OFF/MONITOR/WAIT/name/between: boot/session/seq/time, captured phase/segment/epoch, scan start/end/lag/skipped/straddle, commanded outputs, all count/V pairs, BME Ω/°C/%RH/hPa, fresh/valid/error/status/index and timing per device. Count/V use the same ADS conversion; Pa→hPa once. ERROR/STALE values are null; ADC_LIMIT retains raw count/V with valid=false; signed negative counts are preserved with NEGATIVE status. Gas-invalid alone does not invalidate T/RH/P or stop a session.

CSV columns stay v1. Adapter adds host session/config hash/receive fields and estimated wall-time mapping. `mono_s`/device timings are MCU boot seconds; `received_mono_s` is host process monotonic seconds. HELLO receive anchors the mapping with unmeasured USB/queue uncertainty; receive time is not gas arrival time. Windows wall-clock jumps never drive MCU deadlines.

Increasing seq is canonical. Gaps are logged without backfill. Duplicate/reordered seq remain in wire/parser logs and are excluded from canonical CSV. OFF/CLOSED preflight from the preceding clean session may be logged under the new host session, retaining original wire session ID in wire.jsonl; foreign **active** sessions are refused. There is no hardware-to-simulation fallback.

## Health/failure policy

PING every 2 s requires valid receive, writer progress, recent sync, controller and UI snapshot access. Invalid commands never renew the 15 s MCU lease. Expired lease, output failure, task stall or queue failure latch OFF. Firmware watches sensor/TX progress at 2 s and three consecutive bad required scans. These are configured software thresholds, not measured timing guarantees.

The control loop refreshes its timestamp after command handling and the TX
progress snapshot. Age checks guard against a newer timestamp from another
task so unsigned subtraction cannot report a false stall. Real USB/sensor
stalls and the 15 s heartbeat deadline still latch OFF.

Host valid-sample timeout is 5 s; handshake 8 s plus bounded preflight/sync allowance. Three required-device invalid/stale scans fault; a single gas-invalid/drift warning does not. Reset/ACK mismatch or timeout, transport/disk/sync/queue failure requests priority OFF, ERROR/PARTIAL and no automatic resume.

Shutdown allows 1.5 s by default for OFF/drain; writer close has a 10 s bound.
The serial owner retains the existing COM handle after a read/write fault only
for bounded emergency OFF, ACK and in-flight samples. It never reopens a port,
resumes PING or sends BEGIN/ordinary commands after that fault. OFF/FAULT has
at most 3 attempts, spaced at least 0.1 s, within the shutdown budget, with the
same request ID. A partly accepted or unknown write first gets
`!`+LF+ALL_OFF+LF to invalidate and terminate the residual command, followed
by a correlated FAULT request. Plain LF is insufficient: it could complete
a partly written BEGIN and turn the pump ON after the host has faulted.
An echoed MCU host_off fault does not overwrite the original transport error.

Reports distinguish OFF requested, **commanded OFF acknowledged**, and physical
stop unmeasured. Logging failure cannot prevent the bounded OFF attempt or ACK
parsing. Permanent disconnection still reports OFF unconfirmed and ERROR.
Unconfirmed trial finalization uses MCU-mapped clock time and marks
`host_shutdown_clock_estimate`; it is not a measured MCU OFF transition.

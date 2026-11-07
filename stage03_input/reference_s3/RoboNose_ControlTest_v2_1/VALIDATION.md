# Validation — RoboNose Control Test v2.1

Date: 2026-11-06.

## Version 2.1 checks

- All 27 tests passed together under Linux, Python 3.12.14, Matplotlib 3.10.8 and pyserial 3.5. No tests were skipped. Command: `PYTHONPATH=<pyserial installation directory> MPLBACKEND=Agg python3 -m unittest discover -s tests -v`.
- Tests include native C++ ADS single-ended A0–A3/voltage scaling and failure cases, actuator watchdog/parser, mocked PWM APIs 2/3, real pyserial over POSIX pseudo-terminals, recorder validation, and actual Matplotlib slider/button events against the demo worker.
- The new dataset tests verify known A2 counts/volts are saved as TGS2602, the removed MQ135 #2 column is absent, and coil OFF/ON/OFF produces FILTERED_AIR/SAMPLE/FILTERED_AIR in both sensor rows and command acknowledgements. Metadata retains the A2 sensor identity and valve mapping.
- Old v2.0 firmware packets and old MQ135 CSVs are rejected rather than silently relabelled. The schema is now `robonose.control_test.v2.1`; flash and host software must be updated together.
- Demo preview regenerated with the TGS2602 card and the Khí lọc / Lấy mẫu buttons. It is simulated data, not a TGS2602 measurement.
- The firmware source changes in this release are sensor names, version/schema strings, hardware identity and emitted valve mapping metadata. A full ESP32-S3 compile/link/upload was not performed for version 2.1. Native driver/controller mocks do not validate physical hardware.
- The user has reported v2.0 operating and confirmed valve OFF connects the chamber to the filter, ON to the sample inlet. This confirms the configured plumbing mapping for that setup; the new TGS2602 module and v2.1 firmware still need a physical run after upload.

## Historical version 2.0 checks (2026-10-31)

## Completed checks

- 23 parser/recorder/control/integration tests passed together; one additional dashboard mouse-event integration test passed separately (24 test cases total).
- ADS driver checks cover single-ended A0–A3 MUX selection, gain/rate bits, direct AO scaling, signed near-zero counts, NACK/short reads, configuration mismatch and conversion timeout.
- The native C++ actuator model verifies startup OFF, PWM mapping, independent valve changes, all-off, heartbeat timeout, no automatic restart after heartbeat resumes, invalid-value rejection and output-driver failure handling. Its strict command parser rejects negative, fractional, oversized and extra arguments.
- The PWM hardware adapter was compiled/executed against API-shaped stubs for Arduino-ESP32 major versions 2 and 3. It verifies the 2.x channel-based versus 3.x pin-based calls, inactive fallback after attach failure and, where the API reports it, write failure. These are mock API checks, not an actual Arduino-ESP32 3.x build.
- Client checks cover initial ALL OFF/ACK synchronization (including a sample arriving before INFO), queued commands, ALL OFF preemption even with a full queue, stale connection rejection, ACK/state mismatch, ACK timeout and reboot without restoring previous targets.
- A POSIX pseudo-terminal emulated an ESP while the real pyserial acquisition thread changed pump PWM to 65%, energized the valve, continued recording samples, accepted ALL OFF and confirmed OFF again at shutdown. Sensor rows and command CSV were checked. No physical load was connected.
- A separate serial test supplied fragmented frames, boot chatter, missing measurements, invalid gas, missing/duplicate sequence numbers and a changed boot ID. Raw-byte retention, summaries, chart export and shutdown ACK were checked.
- The actual Matplotlib Slider and Button mouse events were exercised against the demo acquisition worker: selecting 60% alone did not send it, Apply Pump changed the demo target, Valve B energized the demo valve, and ALL OFF cleared both. Data and command logging continued.
- All 7 application translation units (the .ino wrapper, sensor_test.cpp, actuators.cpp, output_hardware.cpp, command_parser.cpp, ads1115_reader.cpp and Bosch bme68x.c) compiled successfully into ESP32-S3 object files with the real Xtensa GCC 8.4.0 toolchain and Arduino-ESP32 2.0.17 headers, for both native CDC on and USB-UART mode (14 successful compilations). Direct offline compiler calls were used.
- Dashboard PNG export was visually checked. docs/DEMO_preview.png shows deliberately simulated sensor data and simulated output changes; it is not a measurement result.

## Practical limits

- The user's physical ESP board, MOSFET modules, pump, valve and TGS2602 module were not available here. Physical voltage/noise, PWM compatibility and minimum working duty are outside these software tests. The configured valve mapping comes from the user's reported test.
- The firmware verification above is object compilation, not a completed full Arduino IDE link, upload or boot test. No board-specific flash image is supplied. Select the user's actual flash/PSRAM and USB configuration in Arduino IDE.
- The source includes a compatibility branch for core 3.x; the genuine SDK compilation used core 2.0.17, while the 3.x PWM interface was checked with stubs and Espressif's published API.
- The Windows native GUI/backend and USB driver were not executed here. Data/serial logic, rendering and mouse-event callbacks were tested under Linux with the Agg canvas.
- No RPM, flow or mechanical valve feedback exists. Every output field describes a firmware command/state, not measured motor speed, air flow or valve position.
- Software OFF/watchdog requires the ESP to be powered and executing firmware. Inactive levels before startup/reset depend on the physical input pulls and power circuit.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Optional native tests are skipped without g++; POSIX pseudo-terminal tests are skipped on Windows. The standard parser/recorder and dashboard-demo tests do not require a physical device.

The Bosch driver remains unchanged under its BSD-3-Clause license; BOSCH_UPSTREAM.json records the original commit and SHA-256 checksums.

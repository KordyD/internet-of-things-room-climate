# Decision Log

## 2026-04-26 — Use direct Python integration instead of Home Assistant

Decision:
Use direct local Xiaomi communication through Python scripts for the first implementation stage.

Reason:
The project should demonstrate custom IoT communication code and not depend on Home Assistant as the primary implementation.

Consequences:
Home Assistant remains a possible fallback, but the current codebase focuses on custom diagnostics first.

## 2026-04-26 — Use python-miio for local Xiaomi access

Decision:
Use `python-miio` and its generic `Device` class for IP/token access and MIoT `get_properties`/`set_properties`.

Reason:
The existing humidifier test already returned successful local responses through `python-miio`.

Consequences:
The first stage can stay small and avoid introducing a backend, database, dashboard, or automation framework.

## 2026-04-26 — Store device secrets in .env

Decision:
Read device IPs, models, and tokens from `.env`, with `.env.example` as the committed template.

Reason:
Tokens are credentials and must not be committed or printed in full.

Consequences:
Scripts show masked token summaries only. Users must create `.env` locally before running diagnostics.

## 2026-04-26 — Keep control commands manual and isolated

Decision:
Place humidifier control checks behind an explicit `CONTROL` confirmation before any `set_properties`.

Reason:
Control commands can change the state of a physical device.

Consequences:
Read-only diagnostics can be run safely, while control tests require manual intent.

## 2026-04-26 — Keep MIoT discovery read-only

Decision:
Make MIoT discovery send only `get_properties` requests over a small siid/piid range.

Reason:
Discovery should help identify available properties without changing physical device state.

Consequences:
Only properties returning `code=0` are printed and saved to `artifacts/` without tokens.

## 2026-04-26 — Split MIoT discovery into small batches

Decision:
Discovery sends `get_properties` in small batches and retries failed batches one property at a time.

Reason:
Some Xiaomi devices fail or time out when a large `get_properties` payload is sent, even though small property checks and `info()` work.

Consequences:
Discovery is slower but more reliable. The `--batch-size` option can be reduced to `1` for the most conservative scan.

## 2026-04-26 — Start with diagnostics before backend work

Decision:
Build diagnostic scripts and shared helpers before adding FastAPI, SQLite, a dashboard, or automations.

Reason:
The local protocol details and property mappings must be confirmed first.

Consequences:
Later backend code can depend on confirmed device behavior rather than guesses.

## 2026-04-26 — Confirm known humidifier properties

Decision:
Record the `deerma.humidifier.jsq2w` mappings from python-miio and local diagnostics:

- `power` = siid `2` / piid `1`
- `fault` = siid `2` / piid `2`
- `mode` = siid `2` / piid `5`
- `target_humidity` = siid `2` / piid `6`
- `relative_humidity` = siid `3` / piid `1`
- `temperature` = siid `3` / piid `7`

Reason:
The previous local script labeled `2/2` as `mode`, but the python-miio mapping identifies it as `fault`; mode is `2/5`.

Consequences:
The read-only script now reads the broader known mapping, and the control script uses `2/5` for manual mode changes.

## 2026-04-26 — Add purifier read mapping from discovery and sources

Decision:
Update the purifier read-only script for `xiaomi.airp.cpa4` to read only properties that returned `code=0` on the local device.

Reason:
Local checks showed some source-based candidates return `-4001` or `-4003` on this exact purifier, while useful properties such as `power=2/1`, `mode=2/4`, `pm25=3/4`, filter values under service `4`, `buzzer=6/1`, `child_lock=8/1`, `motor_speed=9/1`, `aqi_realtime_update_duration=11/4`, and `led_brightness=13/2` are readable.

Consequences:
The normal purifier read path now produces a clean state snapshot without expected MIoT errors. Unsupported candidates remain discoverable through `python scripts/miot.py discover purifier`.

## 2026-04-26 — Hide full tokens in device info output

Decision:
Print `safe_info()` instead of raw `python-miio` `info()` output in diagnostics.

Reason:
The raw `info()` string includes the full local device token.

Consequences:
Read-only diagnostics still show model/version/IP, but tokens are masked in console output.

## 2026-04-26 — Batch normal property reads

Decision:
Use small batched `get_properties` calls for longer read-only property lists.

Reason:
Large MIoT property requests can fail even when device info and small property checks work.

Consequences:
Full state reads are more reliable and remain read-only.

## 2026-04-26 — Move from diagnostics to a production-like app structure

Decision:
Add a FastAPI application, SQLite persistence, a static dashboard, and a background polling loop.

Reason:
The project goal is a readable demo system for room climate control, not a collection of one-off scripts.

Consequences:
Runtime code now lives under `src/`, the dashboard is served from `src/static/`, and data is stored in `data/climate.sqlite3`.

## 2026-04-26 — Keep only one MIoT CLI script

Decision:
Replace separate diagnostic scripts with `scripts/miot.py`.

Reason:
The project should keep a minimal script surface while still allowing safe device info checks, property reads, discovery, and confirmed manual control.

Consequences:
Old `scripts/test_*`, `scripts/check_device_info.py`, and `scripts/discover_miot_props.py` entry points were removed. Use `python scripts/miot.py --help`.

## 2026-04-26 — Default physical control to disabled

Decision:
Automation rules can plan commands by default, but physical `set_properties` calls require `control_enabled`.

Reason:
This keeps the application safe to run while developing and reviewing threshold behavior.

Consequences:
The dashboard stores planned commands in SQLite until physical control is explicitly enabled.

# Room Climate Control

Demo application for local room climate monitoring and simple automation with Xiaomi MIoT devices.

## Structure

- `src/app.py` - FastAPI application and API routes.
- `src/collector.py` - polling loop, automation rules, and command dispatch.
- `src/db.py` - SQLite schema, settings, measurements, events, and commands.
- `src/devices.py` - confirmed MIoT property mappings.
- `src/static/` - dashboard served by FastAPI.
- `scripts/miot.py` - single CLI for diagnostics, discovery, and confirmed manual control.

## Run

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env` with local device IPs and tokens, then start the app:

```powershell
make run
```

Dashboard: `http://127.0.0.1:8000`

## Make Targets

- `make run` - start the FastAPI app.
- `make dev` - start with reload.
- `make poll` - run one collection cycle.
- `make info` - read safe device info.
- `make read-purifier` / `make read-humidifier` - read configured properties.
- `make discover-purifier` / `make discover-humidifier` - read-only MIoT discovery.
- `make check` - compile Python modules.

## Automation Safety

Automations are enabled by default, but physical commands are not sent until `control_enabled` is enabled in the dashboard. Before that, commands are stored as `planned` in SQLite so behavior can be reviewed safely.

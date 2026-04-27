# Xiaomi Local Diagnostics

The project now has a FastAPI app, SQLite storage, dashboard, and automation loop.
Device diagnostics are kept in one CLI: `scripts/miot.py`.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create local configuration:

```powershell
Copy-Item .env.example .env
```

Fill `.env` with local IP addresses and tokens:

```dotenv
PURIFIER_IP=192.168.x.x
PURIFIER_TOKEN=your_32_character_token
PURIFIER_MODEL=

HUMIDIFIER_IP=192.168.10.108
HUMIDIFIER_TOKEN=your_32_character_token
HUMIDIFIER_MODEL=deerma.humidifier.jsq2w
```

Never commit `.env` or real tokens.

## Recommended Order

1. Read device info only:

```powershell
python scripts/miot.py info
```

2. Read confirmed humidifier properties:

```powershell
python scripts/miot.py read humidifier
```

This reads the known `deerma.humidifier.jsq2w` MIoT mapping: power, fault, mode, target humidity, current humidity, temperature, buzzer, LED, and water/protection flags. Extra local properties are printed only if they returned `code=0` on the real device.

3. Read purifier readable properties:

```powershell
python scripts/miot.py read purifier
```

This reads the locally confirmed `xiaomi.airp.cpa4` property set: power, fault, mode, PM2.5, filter values, buzzer, child lock, motor speed, AQI update duration, and LED brightness. Unsupported source-based candidates are left to discovery, not the normal read script.

4. Run limited read-only discovery if the candidate list is incomplete:

```powershell
python scripts/miot.py discover humidifier
```

Discovery uses small `get_properties` batches. If the device still times out, reduce the batch size:

```powershell
python scripts/miot.py discover humidifier --batch-size 1
```

5. Run manual control only when intentionally testing a device:

```powershell
python scripts/miot.py control humidifier turn-on
```

The CLI asks for confirmation before sending `set_properties`.

## Interpreting Results

`code=0` means the device accepted the MIoT property request and returned a value.
Any non-zero `code` means the property is unavailable, unsupported, or invalid for this model/firmware.

If a request times out:

- Check that the computer and device are on the same local network/VLAN.
- Check that the IP address did not change.
- Check that the token is current.
- Try `python scripts/miot.py info` before property tests.

If `code != 0`, do not treat that siid/piid as confirmed. Use `python scripts/miot.py discover <device>` to scan the small read-only range and record only successful properties.

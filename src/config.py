from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import os

try:
    from dotenv import load_dotenv as _python_dotenv_load
except ModuleNotFoundError:
    _python_dotenv_load = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DeviceConfig:
    name: str
    ip: str | None
    token: str | None
    model: str | None

    @property
    def is_configured(self) -> bool:
        return bool(self.ip and self.token)

    def missing_required(self) -> list[str]:
        prefix = self.name.upper()
        missing: list[str] = []
        if not self.ip:
            missing.append(f"{prefix}_IP")
        if not self.token:
            missing.append(f"{prefix}_TOKEN")
        return missing

    def safe_summary(self) -> str:
        token = mask_token(self.token)
        model = self.model or "<not set>"
        ip = self.ip or "<not set>"
        return f"{self.name}: ip={ip}, token={token}, model={model}"


@dataclass(frozen=True)
class AppConfig:
    purifier: DeviceConfig
    humidifier: DeviceConfig


def mask_token(token: str | None) -> str:
    if not token:
        return "<not set>"
    if len(token) <= 8:
        return "<masked>"
    return f"{token[:4]}...{token[-4:]}"


def load_config() -> AppConfig:
    _load_env_file(PROJECT_ROOT / ".env")
    return AppConfig(
        purifier=DeviceConfig(
            name="purifier",
            ip=_get_env("PURIFIER_IP"),
            token=_get_env("PURIFIER_TOKEN"),
            model=_get_env("PURIFIER_MODEL"),
        ),
        humidifier=DeviceConfig(
            name="humidifier",
            ip=_get_env("HUMIDIFIER_IP"),
            token=_get_env("HUMIDIFIER_TOKEN"),
            model=_get_env("HUMIDIFIER_MODEL"),
        ),
    )


def print_config_summary(config: AppConfig) -> None:
    print("Loaded device configuration:")
    print(f"- {config.purifier.safe_summary()}")
    print(f"- {config.humidifier.safe_summary()}")


def print_missing_variables(device: DeviceConfig, required: Iterable[str] | None = None) -> None:
    missing = list(required) if required is not None else device.missing_required()
    if not missing:
        return
    print(f"Missing required variables for {device.name}: {', '.join(missing)}")
    print("Create .env from .env.example and fill IP/token values. Do not commit .env.")


def require_device(config: AppConfig, device_name: str) -> DeviceConfig:
    device = get_device_config(config, device_name)
    missing = device.missing_required()
    if missing:
        print_missing_variables(device, missing)
        raise SystemExit(2)
    return device


def get_device_config(config: AppConfig, device_name: str) -> DeviceConfig:
    if device_name == "purifier":
        return config.purifier
    if device_name == "humidifier":
        return config.humidifier
    raise ValueError(f"Unknown device name: {device_name}")


def _get_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _load_env_file(path: Path) -> None:
    if _python_dotenv_load is not None:
        _python_dotenv_load(path)
        return
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

from __future__ import annotations

from typing import Any

from miio.device import Device

from src.config import DeviceConfig, mask_token


class MiotClientError(RuntimeError):
    """Raised when a MIoT request fails after adding safe device context."""


class MiotClient:
    def __init__(self, config: DeviceConfig) -> None:
        if not config.ip or not config.token:
            raise ValueError(f"{config.name} requires IP and token")
        self.config = config
        self._device = Device(config.ip, config.token)

    def info(self) -> Any:
        return self._call("info", self._device.info)

    def safe_info(self) -> str:
        info = self.info()
        return str(info).replace(self.config.token or "", mask_token(self.config.token))

    def ping(self) -> bool:
        try:
            self.info()
            return True
        except MiotClientError:
            return False

    def get_properties(self, props: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._call("get_properties", self._device.send, "get_properties", props)

    def get_properties_batched(self, props: list[dict[str, Any]], batch_size: int = 8) -> list[dict[str, Any]]:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        results: list[dict[str, Any]] = []
        for index in range(0, len(props), batch_size):
            batch = props[index : index + batch_size]
            results.extend(self.get_properties(batch))
        return results

    def set_property(self, siid: int, piid: int, value: Any, did: str | None = None) -> list[dict[str, Any]]:
        prop: dict[str, Any] = {"siid": siid, "piid": piid, "value": value}
        if did:
            prop["did"] = did
        return self.set_properties([prop])

    def set_properties(self, props: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._call("set_properties", self._device.send, "set_properties", props)

    def _call(self, action: str, func: Any, *args: Any) -> Any:
        try:
            return func(*args)
        except Exception as exc:  # python-miio raises several transport/protocol exceptions.
            safe_message = (
                f"{self.config.name} {action} failed "
                f"(ip={self.config.ip}, token={mask_token(self.config.token)}): "
                f"{type(exc).__name__}: {exc}"
            )
            raise MiotClientError(safe_message) from exc


def print_property_results(results: list[dict[str, Any]]) -> None:
    for item in results:
        code = item.get("code")
        status = "OK" if code == 0 else "ERROR"
        print(
            "did={did} siid={siid} piid={piid} code={code} value={value!r} status={status}".format(
                did=item.get("did", "<none>"),
                siid=item.get("siid", "<none>"),
                piid=item.get("piid", "<none>"),
                code=code,
                value=item.get("value"),
                status=status,
            )
        )


def print_error(exc: Exception) -> None:
    print(f"ERROR: {exc}")

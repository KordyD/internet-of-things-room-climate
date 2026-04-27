from __future__ import annotations

import argparse
from datetime import datetime
import json
from typing import Any

import _bootstrap  # noqa: F401

from src.config import PROJECT_ROOT, get_device_config, load_config, print_config_summary, print_missing_variables
from src.devices import DEVICE_PROPS, specs_as_props
from src.miot_client import MiotClient, print_error, print_property_results


SIID_RANGE = range(1, 9)
PIID_RANGE = range(1, 21)
DEFAULT_BATCH_SIZE = 8


def build_probe_props() -> list[dict[str, int | str]]:
    return [
        {"did": f"s{siid}_p{piid}", "siid": siid, "piid": piid}
        for siid in SIID_RANGE
        for piid in PIID_RANGE
    ]


def chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def require_client(device_name: str) -> MiotClient:
    config = load_config()
    device_config = get_device_config(config, device_name)
    missing = device_config.missing_required()
    if missing:
        print_missing_variables(device_config, missing)
        raise SystemExit(2)
    return MiotClient(device_config)


def read_info(_: argparse.Namespace) -> None:
    config = load_config()
    print_config_summary(config)
    for device_config in (config.purifier, config.humidifier):
        if not device_config.is_configured:
            print(f"\nSkipping {device_config.name}: IP/token are not configured.")
            continue
        print(f"\n{device_config.name} info:")
        try:
            print(MiotClient(device_config).safe_info())
        except Exception as exc:
            print_error(exc)


def read_props(args: argparse.Namespace) -> None:
    client = require_client(args.device)
    props = specs_as_props(DEVICE_PROPS[args.device])
    print_property_results(client.get_properties_batched(props, args.batch_size))


def discover(args: argparse.Namespace) -> None:
    client = require_client(args.device)
    results: list[dict[str, Any]] = []
    props = build_probe_props()

    for batch in chunks(props, args.batch_size):
        try:
            results.extend(client.get_properties(batch))
        except Exception as exc:
            print(f"Batch failed for {batch[0]['did']}..{batch[-1]['did']}; retrying one-by-one.")
            print_error(exc)
            for prop in batch:
                try:
                    results.extend(client.get_properties([prop]))
                except Exception as prop_exc:
                    print(f"Skipping {prop['did']} after request error.")
                    print_error(prop_exc)

    ok_results = [item for item in results if item.get("code") == 0]
    print_property_results(ok_results)

    artifacts_dir = PROJECT_ROOT / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / f"miot_discovery_{args.device}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps({"device": args.device, "results": ok_results}, indent=2), encoding="utf-8")
    print(f"\nSaved discovery result without token: {output_path}")


def control(args: argparse.Namespace) -> None:
    print("WARNING: this command can change the state of a physical device.")
    if input("Type CONTROL to continue: ").strip() != "CONTROL":
        print("No command was sent.")
        return

    client = require_client(args.device)
    if args.command == "turn-on":
        result = client.set_property(2, 1, True, did="power")
    elif args.command == "turn-off":
        result = client.set_property(2, 1, False, did="power")
    else:
        raise ValueError(f"Unsupported command: {args.command}")
    print_property_results(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MIoT diagnostics and manual control.")
    subparsers = parser.add_subparsers(dest="command_name", required=True)

    info_parser = subparsers.add_parser("info", help="Read device info.")
    info_parser.set_defaults(func=read_info)

    read_parser = subparsers.add_parser("read", help="Read configured properties.")
    read_parser.add_argument("device", choices=["purifier", "humidifier"])
    read_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    read_parser.set_defaults(func=read_props)

    discover_parser = subparsers.add_parser("discover", help="Run read-only property discovery.")
    discover_parser.add_argument("device", choices=["purifier", "humidifier"])
    discover_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    discover_parser.set_defaults(func=discover)

    control_parser = subparsers.add_parser("control", help="Send a confirmed manual control command.")
    control_parser.add_argument("device", choices=["purifier", "humidifier"])
    control_parser.add_argument("command", choices=["turn-on", "turn-off"])
    control_parser.set_defaults(func=control)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if getattr(args, "batch_size", 1) < 1:
        raise SystemExit("batch-size must be >= 1")
    args.func(args)


if __name__ == "__main__":
    main()

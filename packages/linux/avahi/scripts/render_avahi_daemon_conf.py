#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


PLACEHOLDER = "__DOTMAN_AVAHI_ALLOWED_INTERFACES__"
PLACEHOLDER_LINE = f"allow-interfaces={PLACEHOLDER}"


def is_lan_interface(interface_path: Path) -> bool:
    if interface_path.name == "lo":
        return False

    # Docker bridges/veth links have no backing hardware device here.
    if not (interface_path / "device").exists():
        return False

    if (interface_path / "wireless").exists():
        return True

    try:
        return (interface_path / "type").read_text(encoding="utf-8").strip() == "1"
    except OSError:
        return False


def find_lan_interfaces(sys_class_net: Path) -> list[str]:
    return sorted(
        interface.name
        for interface in sys_class_net.iterdir()
        if is_lan_interface(interface)
    )


def render(repo_path: Path, sys_class_net: Path) -> str:
    interfaces = find_lan_interfaces(sys_class_net)
    if not interfaces:
        raise RuntimeError("no physical Ethernet/Wi-Fi interfaces found")

    template = repo_path.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise RuntimeError(f"missing placeholder: {PLACEHOLDER}")

    return template.replace(PLACEHOLDER, ",".join(interfaces))


def capture(live_path: Path) -> str:
    lines = live_path.read_text(encoding="utf-8").splitlines()
    active_indexes = [
        index for index, line in enumerate(lines) if line.strip().startswith("allow-interfaces=")
    ]
    if len(active_indexes) > 1:
        raise RuntimeError("multiple active allow-interfaces lines found")

    if active_indexes:
        lines[active_indexes[0]] = PLACEHOLDER_LINE
    else:
        try:
            sample_index = next(
                index
                for index, line in enumerate(lines)
                if line.strip().startswith("#allow-interfaces=")
            )
        except StopIteration as error:
            raise RuntimeError("missing allow-interfaces sample line") from error
        lines.insert(sample_index + 1, PLACEHOLDER_LINE)

    return "\n".join(lines).rstrip("\n") + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fill Avahi allow-interfaces from physical LAN interfaces.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("repo_path", type=Path)
    render_parser.add_argument("--sys-class-net", type=Path, default=Path("/sys/class/net"))

    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("live_path", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        if args.command == "render":
            sys.stdout.write(render(args.repo_path, args.sys_class_net))
        elif args.command == "capture":
            sys.stdout.write(capture(args.live_path))
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

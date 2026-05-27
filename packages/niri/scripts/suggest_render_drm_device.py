#!/usr/bin/env python3
"""Suggest a stable DRM render-node path for Niri's render-drm-device.

This is intentionally a host-inspection helper, not a renderer. It avoids
vendor-specific assumptions and prints enough metadata for a human to choose.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEV_DRI = Path("/dev/dri")
DEV_DRI_BY_PATH = DEV_DRI / "by-path"
SYS_DRM = Path("/sys/class/drm")
PCI_ADDRESS_RE = re.compile(r"^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$")

CLASS_NAMES = {
    "0x030000": "VGA controller",
    "0x030200": "3D controller",
    "0x038000": "display controller",
}

VENDOR_NAMES = {
    "0x1002": "AMD",
    "0x10de": "NVIDIA",
    "0x8086": "Intel",
}


@dataclass(frozen=True)
class RenderNode:
    node: Path
    stable_path: Path
    pci_address: str | None
    vendor_id: str | None
    vendor_name: str | None
    device_id: str | None
    class_id: str | None
    class_name: str | None
    boot_vga: str | None
    cards: tuple[str, ...]

    @property
    def display_path(self) -> Path:
        return self.stable_path

    @property
    def is_boot_vga(self) -> bool | None:
        if self.boot_vga == "1":
            return True
        if self.boot_vga == "0":
            return False
        return None


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def stable_path_for(node: Path) -> Path:
    if DEV_DRI_BY_PATH.is_dir():
        for symlink in sorted(DEV_DRI_BY_PATH.glob("*-render")):
            try:
                if symlink.resolve() == node.resolve():
                    return symlink
            except OSError:
                continue
    return node


def pci_address_for(device_sysfs: Path) -> str | None:
    for part in reversed(device_sysfs.resolve().parts):
        if PCI_ADDRESS_RE.match(part):
            return part
    return None


def cards_for(device_sysfs: Path) -> tuple[str, ...]:
    cards: list[str] = []
    for card in sorted(SYS_DRM.glob("card[0-9]*")):
        device = card / "device"
        try:
            if device.exists() and device.resolve() == device_sysfs.resolve():
                cards.append(card.name)
        except OSError:
            continue
    return tuple(cards)


def discover_render_nodes() -> list[RenderNode]:
    nodes: list[RenderNode] = []
    for render_sysfs in sorted(SYS_DRM.glob("renderD*")):
        node = DEV_DRI / render_sysfs.name
        device_sysfs = render_sysfs / "device"
        if not node.exists() or not device_sysfs.exists():
            continue
        vendor_id = read_text(device_sysfs / "vendor")
        class_id = read_text(device_sysfs / "class")
        nodes.append(
            RenderNode(
                node=node,
                stable_path=stable_path_for(node),
                pci_address=pci_address_for(device_sysfs),
                vendor_id=vendor_id,
                vendor_name=VENDOR_NAMES.get(vendor_id or ""),
                device_id=read_text(device_sysfs / "device"),
                class_id=class_id,
                class_name=CLASS_NAMES.get(class_id or ""),
                boot_vga=read_text(device_sysfs / "boot_vga"),
                cards=cards_for(device_sysfs),
            )
        )
    return nodes


def choose_recommendation(nodes: list[RenderNode]) -> tuple[RenderNode | None, str]:
    if len(nodes) == 1:
        return nodes[0], "only render node"

    non_boot = [node for node in nodes if node.is_boot_vga is False]
    boot = [node for node in nodes if node.is_boot_vga is True]
    if len(non_boot) == 1 and boot:
        return non_boot[0], "only non-boot-VGA render node; common secondary-GPU hint"

    return None, "ambiguous; choose manually from candidates"


def format_candidate(node: RenderNode) -> str:
    metadata = [
        f"node={node.node}",
        f"pci={node.pci_address or '?'}",
        f"vendor={node.vendor_name or node.vendor_id or '?'}",
        f"device={node.device_id or '?'}",
        f"class={node.class_name or node.class_id or '?'}",
        f"boot_vga={node.boot_vga or '?'}",
    ]
    if node.cards:
        metadata.append(f"cards={','.join(node.cards)}")
    return f"- {node.display_path} ({'; '.join(metadata)})"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Suggest stable /dev/dri/by-path/*-render candidates for vars.niri.render_drm_device."
    )
    parser.add_argument(
        "--value-only",
        action="store_true",
        help="Print only the recommended path. Fails if recommendation is ambiguous.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    nodes = discover_render_nodes()
    recommendation, reason = choose_recommendation(nodes)

    if args.value_only:
        if recommendation is None:
            print(reason, file=sys.stderr)
            return 2
        print(recommendation.display_path)
        return 0

    if not nodes:
        print("No DRM render nodes found under /dev/dri.", file=sys.stderr)
        return 1

    if recommendation is not None:
        print(f"recommended: {recommendation.display_path}")
        print(f"reason: {reason}")
        print()
        print("local.toml:")
        print("[vars.niri]")
        print(f'render_drm_device = "{recommendation.display_path}"')
    else:
        print(f"recommended: <none>")
        print(f"reason: {reason}")
    print()
    print("candidates:")
    for node in nodes:
        print(format_candidate(node))

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

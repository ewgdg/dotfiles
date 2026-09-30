#!/usr/bin/env python3
"""Select the host's render GPU: the one compositors render on and Sunshine captures/encodes on.

Rule:
1. Prefer GPUs whose Vulkan driver reports a discrete device type.
2. Among those (or among all GPUs when none is discrete), the largest memory window
   (largest prefetchable PCI BAR) wins. A tie fails instead of guessing.

`vars.render_gpu.pci` (a PCI address such as `0000:01:00.0`) overrides detection.

Everything here is readable without root: sysfs for devices and BARs, and Vulkan
physical-device properties (no logical device is created).
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from collections.abc import Sequence


SYSFS_ROOT = Path("/sys")
OVERRIDE_ENV = "DOTMAN_VAR_render_gpu__pci"  # dotman exports `vars.render_gpu.pci` under this name
DISPLAY_CLASS_PREFIX = "0x03"
VENDOR_NAMES = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}

# Linux `include/linux/ioport.h`
IORESOURCE_MEM = 0x200
IORESOURCE_PREFETCH = 0x2000
# sysfs `resource` lines 0-5 are BARs; later lines are the expansion ROM and bridge windows.
PCI_BAR_COUNT = 6


class GpuSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Gpu:
    pci: str
    vendor: str
    kind: str | None  # Vulkan device type ("discrete", "integrated", ...); None when unknown
    memory_window: int  # bytes


def read_memory_window(resource_path: Path) -> int:
    largest = 0
    for line in resource_path.read_text().splitlines()[:PCI_BAR_COUNT]:
        start, end, flags = (int(field, 16) for field in line.split())
        is_prefetchable_memory = flags & IORESOURCE_MEM and flags & IORESOURCE_PREFETCH
        if is_prefetchable_memory and end > start:
            largest = max(largest, end - start + 1)
    return largest


def discover_gpus(sysfs_root: Path, vulkan_kinds: dict[str, str]) -> list[Gpu]:
    gpus: dict[str, Gpu] = {}
    for render_node in sorted((sysfs_root / "class/drm").glob("renderD*")):
        device = (render_node / "device").resolve()
        if not (device / "class").read_text().strip().startswith(DISPLAY_CLASS_PREFIX):
            continue
        vendor_id = (device / "vendor").read_text().strip()
        gpus[device.name] = Gpu(
            pci=device.name,
            vendor=VENDOR_NAMES.get(vendor_id, "unknown"),
            kind=vulkan_kinds.get(device.name),
            memory_window=read_memory_window(device / "resource"),
        )
    return list(gpus.values())


def select_primary_gpu(gpus: Sequence[Gpu], override_pci: str | None = None) -> Gpu:
    if override_pci:
        for gpu in gpus:
            if gpu.pci == override_pci:
                return gpu
        raise GpuSelectionError(f"vars.render_gpu.pci = {override_pci} does not match any GPU")

    if not gpus:
        raise GpuSelectionError("no GPU render nodes found under /sys/class/drm")

    discrete = [gpu for gpu in gpus if gpu.kind == "discrete"]
    pool = discrete or list(gpus)
    largest = max(gpu.memory_window for gpu in pool)
    winners = [gpu for gpu in pool if gpu.memory_window == largest]
    if len(winners) > 1:
        tied = ", ".join(gpu.pci for gpu in winners)
        raise GpuSelectionError(f"GPUs tie on memory window ({tied}); set vars.render_gpu.pci in local vars")
    return winners[0]


# --- Vulkan (properties only) -------------------------------------------------------

VK_SUCCESS = 0
VK_API_VERSION_1_1 = (1 << 22) | (1 << 12)
VK_STRUCTURE_TYPE_APPLICATION_INFO = 0
VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO = 1
VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2 = 1000059001
VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PCI_BUS_INFO_PROPERTIES_EXT = 1000212000
VK_EXT_PCI_BUS_INFO = b"VK_EXT_pci_bus_info"
VK_DEVICE_TYPES = {0: "other", 1: "integrated", 2: "discrete", 3: "virtual", 4: "cpu"}


class VkApplicationInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("pApplicationName", ctypes.c_char_p),
        ("applicationVersion", ctypes.c_uint32),
        ("pEngineName", ctypes.c_char_p),
        ("engineVersion", ctypes.c_uint32),
        ("apiVersion", ctypes.c_uint32),
    ]


class VkInstanceCreateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("flags", ctypes.c_uint32),
        ("pApplicationInfo", ctypes.POINTER(VkApplicationInfo)),
        ("enabledLayerCount", ctypes.c_uint32),
        ("ppEnabledLayerNames", ctypes.c_void_p),
        ("enabledExtensionCount", ctypes.c_uint32),
        ("ppEnabledExtensionNames", ctypes.c_void_p),
    ]


class VkExtensionProperties(ctypes.Structure):
    _fields_ = [("extensionName", ctypes.c_char * 256), ("specVersion", ctypes.c_uint32)]


class VkPhysicalDevicePCIBusInfoProperties(ctypes.Structure):
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("pciDomain", ctypes.c_uint32),
        ("pciBus", ctypes.c_uint32),
        ("pciDevice", ctypes.c_uint32),
        ("pciFunction", ctypes.c_uint32),
    ]


class VkPhysicalDeviceProperties2(ctypes.Structure):
    # Only the leading VkPhysicalDeviceProperties fields are read; the tail reserves room
    # for the rest of the struct (limits, sparse properties) that the driver writes.
    _fields_ = [
        ("sType", ctypes.c_uint32),
        ("pNext", ctypes.c_void_p),
        ("apiVersion", ctypes.c_uint32),
        ("driverVersion", ctypes.c_uint32),
        ("vendorID", ctypes.c_uint32),
        ("deviceID", ctypes.c_uint32),
        ("deviceType", ctypes.c_int32),
        ("deviceName", ctypes.c_char * 256),
        ("_rest", ctypes.c_uint8 * 4096),
    ]


def _supports_pci_bus_info(vulkan: ctypes.CDLL, device: ctypes.c_void_p) -> bool:
    count = ctypes.c_uint32(0)
    vulkan.vkEnumerateDeviceExtensionProperties(device, None, ctypes.byref(count), None)
    extensions = (VkExtensionProperties * count.value)()
    vulkan.vkEnumerateDeviceExtensionProperties(device, None, ctypes.byref(count), extensions)
    return any(extension.extensionName == VK_EXT_PCI_BUS_INFO for extension in extensions)


def read_vulkan_kinds() -> dict[str, str]:
    """Map PCI address -> Vulkan device type. Empty when Vulkan is unavailable."""
    try:
        vulkan = ctypes.CDLL("libvulkan.so.1")
    except OSError as error:
        print(f"select_render_gpu: Vulkan unavailable ({error}); ranking by memory window only", file=sys.stderr)
        return {}

    app_info = VkApplicationInfo(sType=VK_STRUCTURE_TYPE_APPLICATION_INFO, apiVersion=VK_API_VERSION_1_1)
    create_info = VkInstanceCreateInfo(
        sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, pApplicationInfo=ctypes.pointer(app_info)
    )
    instance = ctypes.c_void_p()
    result = vulkan.vkCreateInstance(ctypes.byref(create_info), None, ctypes.byref(instance))
    if result != VK_SUCCESS:
        print(f"select_render_gpu: vkCreateInstance failed ({result}); ranking by memory window only", file=sys.stderr)
        return {}

    kinds: dict[str, str] = {}
    try:
        count = ctypes.c_uint32(0)
        vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), None)
        devices = (ctypes.c_void_p * count.value)()
        vulkan.vkEnumeratePhysicalDevices(instance, ctypes.byref(count), devices)
        for device in devices:
            if not _supports_pci_bus_info(vulkan, device):
                continue
            pci_info = VkPhysicalDevicePCIBusInfoProperties(
                sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PCI_BUS_INFO_PROPERTIES_EXT
            )
            properties = VkPhysicalDeviceProperties2(
                sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2,
                pNext=ctypes.cast(ctypes.pointer(pci_info), ctypes.c_void_p),
            )
            vulkan.vkGetPhysicalDeviceProperties2(ctypes.c_void_p(device), ctypes.byref(properties))
            pci = (
                f"{pci_info.pciDomain:04x}:{pci_info.pciBus:02x}:"
                f"{pci_info.pciDevice:02x}.{pci_info.pciFunction:x}"
            )
            kinds.setdefault(pci, VK_DEVICE_TYPES.get(properties.deviceType, "other"))
    finally:
        vulkan.vkDestroyInstance(instance, None)
    return kinds


# --- CLI ------------------------------------------------------------------------------


def select_host_gpu() -> tuple[Gpu, list[Gpu]]:
    gpus = discover_gpus(SYSFS_ROOT, read_vulkan_kinds())
    return select_primary_gpu(gpus, os.environ.get(OVERRIDE_ENV)), gpus


def show() -> None:
    selected, gpus = select_host_gpu()
    for gpu in gpus:
        marker = "*" if gpu == selected else " "
        window_mib = gpu.memory_window // (1024 * 1024)
        print(f"{marker} {gpu.pci}  vendor={gpu.vendor}  vulkan={gpu.kind or 'unknown'}  window={window_mib} MiB")
    source = "vars.render_gpu.pci override" if os.environ.get(OVERRIDE_ENV) else "detected"
    print(f"selected: {selected.pci} ({source})")


def render(source: Path) -> None:
    selected, _ = select_host_gpu()
    # Inherits dotman's DOTMAN_* profile context; --var adds the selected GPU on top.
    command = [
        "dotman",
        "render",
        "jinja",
        "--var",
        f"render_gpu.pci={selected.pci}",
        "--var",
        f"render_gpu.vendor={selected.vendor}",
        str(source),
    ]
    os.execvp(command[0], command)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("show", help="List GPU candidates and the selected one")
    render_parser = commands.add_parser("render", help="Render a Jinja source with vars.render_gpu.pci and vars.render_gpu.vendor")
    render_parser.add_argument("source", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "show":
            show()
        else:
            render(args.source)
    except GpuSelectionError as error:
        print(f"select_render_gpu: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

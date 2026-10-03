from __future__ import annotations

import ctypes.util
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts/select_render_gpu.py"
MODULE_SPEC = spec_from_file_location("select_render_gpu", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
select_gpu = module_from_spec(MODULE_SPEC)
# dataclasses resolve annotations through sys.modules during class creation.
sys.modules[MODULE_SPEC.name] = select_gpu
MODULE_SPEC.loader.exec_module(select_gpu)

MiB = 1024 * 1024
Gpu = select_gpu.Gpu

NVIDIA_DGPU = Gpu(pci="0000:01:00.0", vendor="nvidia", kind="discrete", memory_window=16384 * MiB)
AMD_IGPU = Gpu(pci="0000:79:00.0", vendor="amd", kind="integrated", memory_window=256 * MiB)


def test_discrete_gpu_beats_integrated_gpu_with_larger_memory_window() -> None:
    big_igpu = Gpu(pci="0000:00:02.0", vendor="intel", kind="integrated", memory_window=32768 * MiB)
    small_dgpu = Gpu(pci="0000:03:00.0", vendor="amd", kind="discrete", memory_window=256 * MiB)

    assert select_gpu.select_primary_gpu([big_igpu, small_dgpu]) == small_dgpu


def test_largest_memory_window_wins_among_discrete_gpus() -> None:
    small_dgpu = Gpu(pci="0000:03:00.0", vendor="amd", kind="discrete", memory_window=256 * MiB)

    assert select_gpu.select_primary_gpu([small_dgpu, AMD_IGPU, NVIDIA_DGPU]) == NVIDIA_DGPU


def test_without_discrete_gpus_largest_memory_window_wins_among_all() -> None:
    # Vulkan unavailable or no discrete type reported: memory window decides alone.
    untyped_nvidia = Gpu(pci="0000:01:00.0", vendor="nvidia", kind=None, memory_window=16384 * MiB)
    untyped_amd = Gpu(pci="0000:79:00.0", vendor="amd", kind=None, memory_window=256 * MiB)

    assert select_gpu.select_primary_gpu([untyped_amd, untyped_nvidia]) == untyped_nvidia


def test_memory_window_tie_fails_and_names_the_override() -> None:
    first = Gpu(pci="0000:01:00.0", vendor="nvidia", kind="discrete", memory_window=256 * MiB)
    second = Gpu(pci="0000:02:00.0", vendor="nvidia", kind="discrete", memory_window=256 * MiB)

    with pytest.raises(select_gpu.GpuSelectionError, match="vars.render_gpu.pci"):
        select_gpu.select_primary_gpu([first, second])


def test_no_gpu_fails() -> None:
    with pytest.raises(select_gpu.GpuSelectionError):
        select_gpu.select_primary_gpu([])


def test_override_selects_named_gpu() -> None:
    assert select_gpu.select_primary_gpu([NVIDIA_DGPU, AMD_IGPU], override_pci="0000:79:00.0") == AMD_IGPU


def test_override_for_missing_gpu_fails() -> None:
    with pytest.raises(select_gpu.GpuSelectionError, match="0000:05:00.0"):
        select_gpu.select_primary_gpu([NVIDIA_DGPU], override_pci="0000:05:00.0")


def write_resource(path: Path, bars: list[tuple[int, int, int]]) -> None:
    lines = [f"0x{start:016x} 0x{end:016x} 0x{flags:016x}" for start, end, flags in bars]
    path.write_text("\n".join(lines) + "\n")


MEM_PREFETCH = 0x14220C
MEM_PLAIN = 0x40200
ROM = 0x46200  # expansion ROM slot (index 6); its prefetch bit must not count as a BAR


def test_memory_window_is_largest_prefetchable_bar(tmp_path: Path) -> None:
    resource = tmp_path / "resource"
    write_resource(
        resource,
        [
            (0xF000000000, 0xF000000000 + 64 * MiB - 1, MEM_PLAIN),
            (0x6000000000, 0x6000000000 + 16384 * MiB - 1, MEM_PREFETCH),
            (0x6400000000, 0x6400000000 + 32 * MiB - 1, MEM_PREFETCH),
            (0, 0, 0),
            (0, 0, 0),
            (0, 0, 0),
            (0xE000000000, 0xE000000000 + 32768 * MiB - 1, ROM),
        ],
    )

    assert select_gpu.read_memory_window(resource) == 16384 * MiB


def make_pci_device(sysfs: Path, pci: str, *, vendor: str, device_class: str, window: int) -> Path:
    device = sysfs / "bus/pci/devices" / pci
    device.mkdir(parents=True)
    (device / "vendor").write_text(vendor + "\n")
    (device / "class").write_text(device_class + "\n")
    write_resource(device / "resource", [(0x6000000000, 0x6000000000 + window - 1, MEM_PREFETCH)])
    return device


def link_render_node(sysfs: Path, node: str, device: Path) -> None:
    node_dir = sysfs / "class/drm" / node
    node_dir.mkdir(parents=True)
    (node_dir / "device").symlink_to(device)


def test_discover_gpus_reads_display_devices_behind_render_nodes(tmp_path: Path) -> None:
    sysfs = tmp_path / "sys"
    nvidia = make_pci_device(sysfs, "0000:01:00.0", vendor="0x10de", device_class="0x030000", window=16384 * MiB)
    amd = make_pci_device(sysfs, "0000:79:00.0", vendor="0x1002", device_class="0x030000", window=256 * MiB)
    accelerator = make_pci_device(sysfs, "0000:7a:00.0", vendor="0x1022", device_class="0x118000", window=MiB)
    link_render_node(sysfs, "renderD128", nvidia)
    link_render_node(sysfs, "renderD129", amd)
    link_render_node(sysfs, "renderD130", accelerator)

    gpus = select_gpu.discover_gpus(sysfs, vulkan_kinds={"0000:01:00.0": "discrete"})

    assert gpus == [
        Gpu(pci="0000:01:00.0", vendor="nvidia", kind="discrete", memory_window=16384 * MiB),
        Gpu(pci="0000:79:00.0", vendor="amd", kind=None, memory_window=256 * MiB),
    ]


def test_vulkan_probe_reads_this_hosts_devices_without_crashing() -> None:
    # Vulkan handles are 64-bit pointers. Undeclared ctypes signatures pass them as
    # 32-bit ints, which crashed the driver (exit 139) and failed every render.
    if ctypes.util.find_library("vulkan") is None:
        pytest.skip("libvulkan is not installed")
    completed = subprocess.run(
        [sys.executable, "-c", f"import runpy; runpy.run_path({str(MODULE_PATH)!r})['read_vulkan_kinds']()"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr


SUNSHINE_TEMPLATE = REPO_ROOT / "packages/linux/sunshine/files/sunshine.conf"


def render_sunshine(vendor: str) -> str:
    completed = subprocess.run(
        [
            "dotman",
            "render",
            "jinja",
            "--var",
            "desktop.session=hyprland",
            "--var",
            "render_gpu.pci=0000:01:00.0",
            "--var",
            f"render_gpu.vendor={vendor}",
            str(SUNSHINE_TEMPLATE),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout


@pytest.mark.skipif(shutil.which("dotman") is None, reason="dotman CLI not installed")
@pytest.mark.parametrize(("vendor", "encoder_line"), [("nvidia", "encoder = nvenc"), ("amd", "encoder = vaapi")])
def test_sunshine_encodes_and_captures_on_the_selected_gpu(vendor: str, encoder_line: str) -> None:
    rendered = render_sunshine(vendor).splitlines()

    assert "adapter_name = /dev/dri/by-path/pci-0000:01:00.0-render" in rendered
    assert encoder_line in rendered


@pytest.mark.skipif(shutil.which("dotman") is None, reason="dotman CLI not installed")
def test_sunshine_leaves_encoder_to_autodetect_for_unmapped_vendors() -> None:
    rendered = render_sunshine("unknown").splitlines()

    assert not any(line.startswith("encoder =") for line in rendered)

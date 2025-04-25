#!/usr/bin/env python3

"""
This script configures a monitor for Sunshine streaming and prevents system idle
Usage:
  sunshine-prep.py do --width WIDTH --height HEIGHT --fps FPS
  sunshine-prep.py undo
"""

import os
import sys
import json
import subprocess
import signal
import argparse

# Temporary files to store configuration
MONITOR_CONFIG_FILE = "/tmp/sunshine-prep/sunshine-monitor-config.json"
SELECTED_MONITOR_FILE = "/tmp/sunshine-prep/sunshine-selected-monitor"
INHIBIT_PID_FILE = "/tmp/sunshine-prep/sunshine-inhibit-pid"


def run_command(command):
    """Run a shell command and return its output"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}")
        print(f"Error message: {e.stderr}")
        return None


def save_monitor_config():
    """Save current monitor configuration to a temporary file"""
    print("Saving current monitor configuration...")
    json_output = run_command("kscreen-doctor --json")
    if not json_output:
        return None

    monitor_data = json.loads(json_output).get("outputs")
    if not monitor_data:
        return None

    # Ensure the directory exists
    directory = os.path.dirname(MONITOR_CONFIG_FILE)
    if not os.path.exists(directory):
        os.makedirs(directory)  # Create the directory if it doesn't exist
    with open(MONITOR_CONFIG_FILE, "w") as f:
        f.write(json.dumps(monitor_data))
    return monitor_data


def find_suitable_monitor(monitor_data, width, height, fps) -> None | tuple[str, str]:
    """Find a monitor that supports the requested resolution and refresh rate"""
    print(f"Looking for a monitor supporting {width}x{height}@{fps}...")

    if not monitor_data:
        return None
    try:
        # Iterate through monitors
        for monitor_info in sorted(
            monitor_data, key=lambda d: 0 if d.get("name").startswith("DP") else 1
        ):
            monitor_name = monitor_info.get("name")
            if not monitor_name:
                continue

            # Check if monitor is connected
            if not monitor_info.get("connected", False):
                continue

            # Check available modes
            modes = monitor_info.get("modes", [])
            for mode in modes:
                mode_size = mode.get("size", {})
                mode_width = mode_size.get("width")
                mode_height = mode_size.get("height")
                mode_refresh = mode.get("refreshRate")

                # Convert refresh rate to integer for comparison
                # Some displays report refresh rates like 59.94 instead of 60
                try:
                    mode_refresh_int = int(round(float(mode_refresh)))
                    target_fps_int = int(round(float(fps)))
                except (ValueError, TypeError):
                    continue

                if (
                    mode_width == int(width)
                    and mode_height == int(height)
                    and mode_refresh_int == target_fps_int
                ):
                    mode_id = mode.get("id")
                    if not mode_id:
                        continue
                    print(f"Found suitable monitor: {monitor_name}, mode: {mode_id}")
                    # with open(SELECTED_MONITOR_FILE, "w") as f:
                    #     f.write(monitor_name)
                    return monitor_name, mode_id

        print(f"No suitable monitor found supporting {width}x{height}@{fps}")
        return None

    except json.JSONDecodeError:
        print("Error parsing JSON output from kscreen-doctor")
        return None


def enable_monitor(monitor_data, monitor, mode):
    """Enable the selected monitor with specified settings and disable others"""
    print(f"Enabling monitor {monitor} with mode {mode}...")

    try:
        # Disable all other monitors
        for monitor_info in monitor_data:
            monitor_name = monitor_info.get("name")
            if not monitor_name or not monitor_info.get("connected", False):
                continue

            if monitor_name != monitor:
                print(f"Disabling monitor {monitor_name}...")
                run_command(f"kscreen-doctor output.{monitor_name}.disable")

        # Enable the target monitor, set it as primary, and configure the resolution and refresh rate
        # command = f"kscreen-doctor output.{monitor}.enable output.{monitor}.primary output.{monitor}.mode.{width}x{height}@{fps}"
        command = f"kscreen-doctor output.{monitor}.enable output.{monitor}.primary output.{monitor}.mode.{mode}"
        result = run_command(command)

        if result is None:
            print("Failed to enable monitor")
            return False
    except json.JSONDecodeError:
        print("Error parsing JSON output from kscreen-doctor")
        return False

    # Start systemd-inhibit to prevent system from going idle
    print("Starting systemd-inhibit to prevent system idle...")

    # Use Popen to start the process in the background
    inhibit_process = subprocess.Popen(
        [
            "systemd-inhibit",
            "--who=sunshine",
            "--what=idle",
            "--why=sunshine-connection",
            "--",
            "sleep",
            "infinity",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Save the PID
    with open(INHIBIT_PID_FILE, "w") as f:
        f.write(str(inhibit_process.pid))
    print(f"systemd-inhibit process id: {inhibit_process}")

    return True


def restore_monitor_config():
    """Restore previous monitor configuration"""
    print("Restoring previous monitor configuration...")

    # Kill the systemd-inhibit process
    if os.path.exists(INHIBIT_PID_FILE):
        try:
            with open(INHIBIT_PID_FILE, "r") as f:
                pid = int(f.read().strip())

            print(f"Killing systemd-inhibit process (PID: {pid})...")
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                # If direct kill fails, try pkill
                run_command("pkill -f sunshine-connection")

            os.remove(INHIBIT_PID_FILE)
        except (ValueError, OSError) as e:
            print(f"Error killing process: {e}")
    else:
        print("Killing systemd-inhibit process")
        run_command("pkill -f sunshine-connection")

    # Restore the saved monitor configuration
    if os.path.exists(MONITOR_CONFIG_FILE):
        try:
            with open(MONITOR_CONFIG_FILE, "r") as f:
                saved_config = json.load(f)

            # Build a kscreen-doctor command to restore all monitor states
            restore_command = "kscreen-doctor"

            for monitor_info in saved_config:
                monitor_name = monitor_info.get("name")

                if not monitor_name or not monitor_info.get("connected", False):
                    continue

                # Check if monitor is enabled in saved config
                if monitor_info.get("enabled", False):
                    # Get the current mode information
                    current_mode = monitor_info.get("currentModeId")
                    if current_mode:
                        restore_command += f" output.{monitor_name}.enable output.{monitor_name}.mode.{current_mode}"
                        # Set primary if it was primary
                        if monitor_info.get("primary", False):
                            restore_command += f" output.{monitor_name}.primary"
                        break
                else:
                    # Disable monitor if it was disabled
                    restore_command += f" output.{monitor_name}.disable"

            # Execute the restore command
            print("Restoring monitor configuration with command:")
            print(restore_command)
            run_command(restore_command)

            # Clean up saved configuration
            # os.remove(MONITOR_CONFIG_FILE)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error restoring monitor configuration: {e}")

    # Clean up selected monitor file
    if os.path.exists(SELECTED_MONITOR_FILE):
        os.remove(SELECTED_MONITOR_FILE)


def main():
    """Main function to handle script arguments"""
    parser = argparse.ArgumentParser(
        description="Configure a monitor for Sunshine streaming and prevent system idle"
    )
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Parser for the 'do' command
    do_parser = subparsers.add_parser("do", help="Enable a monitor for streaming")
    do_parser.add_argument("--width", type=int, help="Screen width in pixels")
    do_parser.add_argument("--height", type=int, help="Screen height in pixels")
    do_parser.add_argument("--fps", type=int, help="Screen refresh rate in Hz")

    # Parser for the 'undo' command
    undo_parser = subparsers.add_parser(
        "undo", help="Restore previous monitor configuration"
    )

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        sys.exit(1)

    if args.action == "do":
        # Check if required arguments are provided
        if not all([args.width, args.height, args.fps]):
            # Try to fall back to environment variables if arguments are not provided
            width = args.width or os.environ.get("SUNSHINE_CLIENT_WIDTH")
            height = args.height or os.environ.get("SUNSHINE_CLIENT_HEIGHT")
            fps = args.fps or os.environ.get("SUNSHINE_CLIENT_FPS")

            if not all([width, height, fps]):
                print("Error: Required parameters not provided.")
                print(
                    "Please specify --width, --height, and --fps, or set the corresponding environment variables."
                )
                do_parser.print_help()
                sys.exit(1)
        else:
            width = args.width
            height = args.height
            fps = args.fps

        # Save current configuration before making changes
        monitor_data = save_monitor_config()

        if not monitor_data:
            print("Failed to find monitor data. Exiting.")

        # Find a suitable monitor
        monitor_with_mode = find_suitable_monitor(monitor_data, width, height, fps)
        if monitor_with_mode:
            monitor, mode = monitor_with_mode
            # Enable the monitor with specified settings
            if not enable_monitor(monitor_data, monitor, mode):
                print("Failed to enable monitor. Exiting.")
                sys.exit(1)
        else:
            print("Failed to find a suitable monitor. Exiting.")
            sys.exit(1)

    elif args.action == "undo":
        # Restore previous configuration
        restore_monitor_config()


if __name__ == "__main__":
    main()

"""Stop any running AgentNebula workflow.

Usage:
    python tools/stop_workflow.py              # stop on default port 8765
    python tools/stop_workflow.py --port 9000  # stop on custom port
"""

import argparse
import platform
import socket
import subprocess
import sys
import time


def stop(port: int) -> None:
    system = platform.system()
    killed = []

    if system == "Windows":
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    print(f"Killing process on port {port} (PID {pid})")
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, timeout=5)
                    killed.append(pid)
        except Exception as e:
            print(f"Error: {e}")
    else:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5,
            )
            for pid in result.stdout.strip().split():
                if pid:
                    print(f"Killing process on port {port} (PID {pid})")
                    subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
                    killed.append(pid)
        except Exception:
            pass

    if not killed:
        print(f"No process found on port {port}")
        return

    # Wait for port to be free
    for i in range(10):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", port))
            s.close()
            print(f"Port {port} is now free")
            return
        except OSError:
            time.sleep(1)

    print(f"Warning: port {port} may still be in use")


def main():
    parser = argparse.ArgumentParser(description="Stop AgentNebula workflow")
    parser.add_argument("--port", type=int, default=8765, help="Dashboard port (default: 8765)")
    args = parser.parse_args()
    stop(args.port)


if __name__ == "__main__":
    main()

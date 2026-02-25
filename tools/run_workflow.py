"""Launch AgentNebula workflow for a project.

Usage:
    python tools/run_workflow.py                              # current dir's .agent-nebula/
    python tools/run_workflow.py /path/to/project             # specific project
    python tools/run_workflow.py /path/to/project --max 5     # limit to 5 sessions
    python tools/run_workflow.py --port 9000                  # custom dashboard port

The script:
  1. Stops any existing AgentNebula process and frees the dashboard port
  2. Unsets CLAUDECODE env var (allows running from within Claude Code)
  3. Starts the orchestrator with dashboard
"""

import argparse
import os
import platform
import socket
import subprocess
import sys
import time
from pathlib import Path

WORKFLOW_SUBDIR = ".agent-nebula"


def _kill_existing(port: int) -> None:
    """Stop any existing AgentNebula/uvicorn processes and free the port."""
    system = platform.system()

    # Kill known process names
    if system == "Windows":
        # Find PID on port
        try:
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.strip().split()[-1]
                    print(f"[AgentNebula] Stopping existing process on port {port} (PID {pid})")
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=5,
                    )
        except Exception:
            pass
    else:
        # Unix: kill by port
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5,
            )
            for pid in result.stdout.strip().split():
                if pid:
                    print(f"[AgentNebula] Stopping existing process on port {port} (PID {pid})")
                    subprocess.run(["kill", "-9", pid], capture_output=True, timeout=5)
        except Exception:
            pass

    # Wait for port to be free
    for _ in range(10):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("0.0.0.0", port))
            s.close()
            return  # Port is free
        except OSError:
            time.sleep(1)

    print(f"[WARN] Port {port} may still be in use")


def main():
    parser = argparse.ArgumentParser(
        description="Run AgentNebula workflow",
    )
    parser.add_argument(
        "project_dir", nargs="?", default=".",
        help="Project directory containing .agent-nebula/ (default: current dir)",
    )
    parser.add_argument("--max", type=int, default=None, help="Max sessions (-1 = infinite)")
    parser.add_argument("--port", type=int, default=8765, help="Dashboard port (default: 8765)")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable dashboard")
    parser.add_argument("--spec", type=str, default=None, help="Path to spec file")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    workflow_dir = project_dir / WORKFLOW_SUBDIR

    if not workflow_dir.is_dir():
        print(f"[ERROR] No {WORKFLOW_SUBDIR}/ found in {project_dir}")
        print(f"  Run first:  python tools/setup_workflow.py {project_dir}")
        sys.exit(1)

    # Stop existing processes on the dashboard port
    _kill_existing(args.port)

    # Build the command
    cmd = [
        sys.executable, "-m", "agent_nebula", "run",
        "-w", str(workflow_dir),
        "--port", str(args.port),
    ]
    if args.max is not None:
        cmd += ["--max-sessions", str(args.max)]
    if args.no_dashboard:
        cmd.append("--no-dashboard")
    if args.spec:
        cmd += ["--spec", args.spec]

    # Unset CLAUDECODE to allow nested sessions
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    print(f"[AgentNebula] Workflow: {workflow_dir}")
    print(f"[AgentNebula] Dashboard: http://localhost:{args.port}")
    print(f"[AgentNebula] Ctrl+C to stop gracefully")
    print()

    try:
        proc = subprocess.run(cmd, env=env)
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        print("\n[AgentNebula] Stopped.")


if __name__ == "__main__":
    main()

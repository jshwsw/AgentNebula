"""CLI interface: agent-nebula init | run | status."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def _add_workflow_dir_arg(parser: argparse.ArgumentParser) -> None:
    """Add the -w/--workflow-dir argument to a subparser."""
    parser.add_argument(
        "-w", "--workflow-dir",
        type=str,
        default=None,
        help="Workflow state directory (default: ./.agent-nebula/)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent-nebula",
        description="AgentNebula - Universal infinite-loop agent workflow",
    )
    sub = parser.add_subparsers(dest="command")

    # ── init ──
    p_init = sub.add_parser("init", help="Initialize a workflow")
    _add_workflow_dir_arg(p_init)
    p_init.add_argument("--cwd", type=str, default=None,
                        help="Working directory for Claude agent (default: current directory)")
    p_init.add_argument("--spec", type=str, help="Path to a spec file describing what to do")
    p_init.add_argument("--spec-text", type=str, help="Inline spec text")
    p_init.add_argument("--name", type=str, default=None, help="Project name")

    # ── run ──
    p_run = sub.add_parser("run", help="Start the infinite agent loop")
    _add_workflow_dir_arg(p_run)
    p_run.add_argument("--spec", type=str, help="Path to a spec file (used if no task list exists yet)")
    p_run.add_argument("--spec-text", type=str, help="Inline spec text")
    p_run.add_argument("--max-sessions", type=int, default=None, help="Override max sessions (-1 = infinite)")
    p_run.add_argument("--port", type=int, default=8765, help="Dashboard web port (default: 8765)")
    p_run.add_argument("--no-dashboard", action="store_true", help="Disable the web dashboard")

    # ── status ──
    p_status = sub.add_parser("status", help="Show current workflow status")
    _add_workflow_dir_arg(p_status)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        _cmd_init(args)
    elif args.command == "run":
        _cmd_run(args)
    elif args.command == "status":
        _cmd_status(args)


def _cmd_init(args) -> None:
    """Initialize the workflow directory with config."""
    from agent_nebula.config import (
        detect_project, ProjectConfig, resolve_workflow_dir, CONFIG_FILE,
    )
    from agent_nebula.state import ensure_dirs, write_spec

    workflow_dir = resolve_workflow_dir(args.workflow_dir)
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd().resolve()

    if (workflow_dir / CONFIG_FILE).exists():
        console.print(f"[yellow]Workflow already initialized at {workflow_dir}[/yellow]")
        config = ProjectConfig.load(workflow_dir)
    else:
        config = detect_project(cwd)
        config.cwd = str(cwd)
        if args.name:
            config.name = args.name
        ensure_dirs(workflow_dir)
        config.save(workflow_dir)

    console.print(Panel(
        f"Project: {config.name}\n"
        f"Type: {config.project_type}\n"
        f"Stack: {', '.join(config.tech_stack)}\n"
        f"CWD: {config.resolve_cwd(workflow_dir)}",
        title="AgentNebula Init", style="green",
    ))

    spec_text = _resolve_spec(args)
    if spec_text:
        write_spec(workflow_dir, spec_text)
        console.print(f"[green]Spec saved ({len(spec_text)} chars)[/green]")
    else:
        console.print("[dim]No spec provided. Use --spec or --spec-text when running.[/dim]")

    console.print(f"\n[green]Workflow dir: {workflow_dir}[/green]")
    console.print("Next: run [bold]agent-nebula run -w {workflow_dir}[/bold] to start.")


def _cmd_run(args) -> None:
    """Start the orchestrator loop."""
    from agent_nebula.orchestrator import run_workflow
    from agent_nebula.config import resolve_workflow_dir, ProjectConfig
    from agent_nebula.state import read_spec, write_spec

    workflow_dir = resolve_workflow_dir(args.workflow_dir)

    if args.max_sessions is not None:
        try:
            config = ProjectConfig.load(workflow_dir)
            config.workflow.max_sessions = args.max_sessions
            config.save(workflow_dir)
        except FileNotFoundError:
            pass

    spec_text = _resolve_spec(args)
    if spec_text:
        write_spec(workflow_dir, spec_text)
    else:
        spec_text = read_spec(workflow_dir)

    console.print(Panel(f"AgentNebula - Starting Workflow\nWorkflow: {workflow_dir}", style="bold cyan"))
    asyncio.run(run_workflow(
        workflow_dir, spec=spec_text or None,
        dashboard_port=args.port,
        no_dashboard=args.no_dashboard,
    ))


def _cmd_status(args) -> None:
    """Show current progress."""
    from agent_nebula.tasks import TaskList
    from agent_nebula.config import resolve_workflow_dir, ProjectConfig
    from agent_nebula.state import read_progress, next_session_number

    workflow_dir = resolve_workflow_dir(args.workflow_dir)
    task_list = TaskList(workflow_dir)

    if not task_list.exists():
        console.print(f"[yellow]No workflow found at {workflow_dir}. Run `agent-nebula init` first.[/yellow]")
        return

    done, total = task_list.stats()
    pending = task_list.pending()
    session_num = next_session_number(workflow_dir)

    # Load config for cwd info
    cwd_str = "N/A"
    try:
        config = ProjectConfig.load(workflow_dir)
        cwd_str = str(config.resolve_cwd(workflow_dir))
    except FileNotFoundError:
        pass

    table = Table(title="AgentNebula Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Workflow dir", str(workflow_dir))
    table.add_row("Working dir (cwd)", cwd_str)
    table.add_row("Sessions completed", str(session_num - 1))
    table.add_row("Tasks completed", f"{done}/{total}")
    table.add_row("Tasks remaining", str(len(pending)))
    if total > 0:
        table.add_row("Progress", f"{done/total*100:.1f}%")
    console.print(table)

    if pending:
        pt = Table(title="Next Pending Tasks")
        pt.add_column("ID", style="cyan")
        pt.add_column("Priority")
        pt.add_column("Category")
        pt.add_column("Description")
        for t in pending[:10]:
            pt.add_row(t.id, str(t.priority), t.category, t.description[:80])
        console.print(pt)

    progress = read_progress(workflow_dir)
    if progress:
        console.print(Panel(progress[:1000], title="Recent Progress Notes"))


def _resolve_spec(args) -> str:
    """Extract spec text from CLI args."""
    if hasattr(args, "spec_text") and args.spec_text:
        return args.spec_text
    if hasattr(args, "spec") and args.spec:
        spec_path = Path(args.spec)
        if spec_path.is_file():
            return spec_path.read_text(encoding="utf-8")
        console.print(f"[red]Spec file not found: {spec_path}[/red]")
        sys.exit(1)
    return ""


if __name__ == "__main__":
    main()

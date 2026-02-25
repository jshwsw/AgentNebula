"""CLI interface: agent-nebula init | run | status | resume."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent-nebula",
        description="AgentNebula - Universal infinite-loop agent workflow",
    )
    sub = parser.add_subparsers(dest="command")

    # ── init ──
    p_init = sub.add_parser("init", help="Initialize workflow in a project directory")
    p_init.add_argument("project_dir", nargs="?", default=".", help="Project directory (default: cwd)")
    p_init.add_argument("--spec", type=str, help="Path to a spec file describing what to do")
    p_init.add_argument("--spec-text", type=str, help="Inline spec text")

    # ── run ──
    p_run = sub.add_parser("run", help="Start the infinite agent loop")
    p_run.add_argument("project_dir", nargs="?", default=".", help="Project directory (default: cwd)")
    p_run.add_argument("--spec", type=str, help="Path to a spec file (used if no task list exists yet)")
    p_run.add_argument("--spec-text", type=str, help="Inline spec text")
    p_run.add_argument("--max-sessions", type=int, default=None, help="Override max sessions (-1 = infinite)")

    # ── status ──
    p_status = sub.add_parser("status", help="Show current workflow status")
    p_status.add_argument("project_dir", nargs="?", default=".", help="Project directory (default: cwd)")

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
    """Initialize the .agent-workflow/ directory with auto-detected config."""
    from agent_nebula.config import detect_project, ProjectConfig, WORKFLOW_DIR
    from agent_nebula.state import ensure_dirs, write_spec

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        console.print(f"[red]Not a directory: {project_dir}[/red]")
        sys.exit(1)

    workflow_path = project_dir / WORKFLOW_DIR
    if workflow_path.exists():
        console.print(f"[yellow]Workflow already initialized at {workflow_path}[/yellow]")
        # Reload existing
        config = ProjectConfig.load(project_dir)
    else:
        config = detect_project(project_dir)
        ensure_dirs(project_dir)
        config.save(project_dir)

    console.print(Panel(f"Project: {config.name}\nType: {config.project_type}\nStack: {', '.join(config.tech_stack)}",
                        title="AgentNebula Init", style="green"))

    # Handle spec
    spec_text = _resolve_spec(args)
    if spec_text:
        write_spec(project_dir, spec_text)
        console.print(f"[green]Spec saved ({len(spec_text)} chars)[/green]")
    else:
        console.print("[dim]No spec provided. Use --spec or --spec-text when running.[/dim]")

    console.print(f"\n[green]Initialized at {workflow_path}[/green]")
    console.print("Next: run [bold]agent-nebula run[/bold] to start the workflow.")


def _cmd_run(args) -> None:
    """Start the orchestrator loop."""
    from agent_nebula.orchestrator import run_workflow
    from agent_nebula.state import read_spec, write_spec

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        console.print(f"[red]Not a directory: {project_dir}[/red]")
        sys.exit(1)

    # Override max_sessions if provided
    if args.max_sessions is not None:
        from agent_nebula.config import ProjectConfig, WORKFLOW_DIR
        try:
            config = ProjectConfig.load(project_dir)
            config.workflow.max_sessions = args.max_sessions
            config.save(project_dir)
        except FileNotFoundError:
            pass  # Will be auto-detected in orchestrator

    # Resolve spec
    spec_text = _resolve_spec(args)
    if spec_text:
        write_spec(project_dir, spec_text)
    else:
        spec_text = read_spec(project_dir)

    console.print(Panel("AgentNebula - Starting Workflow", style="bold cyan"))
    asyncio.run(run_workflow(project_dir, spec=spec_text or None))


def _cmd_status(args) -> None:
    """Show current progress."""
    from agent_nebula.tasks import TaskList
    from agent_nebula.state import read_progress, next_session_number

    project_dir = Path(args.project_dir).resolve()
    task_list = TaskList(project_dir)

    if not task_list.exists():
        console.print("[yellow]No workflow found. Run `agent-nebula init` first.[/yellow]")
        return

    done, total = task_list.stats()
    pending = task_list.pending()
    session_num = next_session_number(project_dir)

    # Summary table
    table = Table(title="AgentNebula Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Project", str(project_dir))
    table.add_row("Sessions completed", str(session_num - 1))
    table.add_row("Tasks completed", f"{done}/{total}")
    table.add_row("Tasks remaining", str(len(pending)))
    if total > 0:
        table.add_row("Progress", f"{done/total*100:.1f}%")
    console.print(table)

    # Pending tasks
    if pending:
        pt = Table(title="Next Pending Tasks")
        pt.add_column("ID", style="cyan")
        pt.add_column("Priority")
        pt.add_column("Category")
        pt.add_column("Description")
        for t in pending[:10]:
            pt.add_row(t.id, str(t.priority), t.category, t.description[:80])
        console.print(pt)

    # Recent progress
    progress = read_progress(project_dir)
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

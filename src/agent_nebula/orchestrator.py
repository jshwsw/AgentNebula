"""Core orchestrator: the infinite session loop.

Key design: workflow_dir and cwd are independent.
- workflow_dir: where task_list.json, progress.md, session_history/ live
- cwd: where Claude agent reads/writes project files (from config.cwd)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from claude_code_sdk import (
    query,
    ClaudeCodeOptions,
    AssistantMessage,
    UserMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)

from agent_nebula.config import ProjectConfig
from agent_nebula.state import (
    ensure_dirs,
    next_session_number,
    save_session_summary,
)
from agent_nebula.tasks import TaskList
from agent_nebula.prompts.initializer import build_initializer_prompt
from agent_nebula.prompts.worker import build_worker_prompt

console = Console()


async def run_single_session(
    cwd: Path,
    config: ProjectConfig,
    prompt: str,
    model: str,
    session_num: int,
) -> tuple[str, ResultMessage | None]:
    """Run a single Claude Code SDK session."""

    options = ClaudeCodeOptions(
        model=model,
        cwd=str(cwd.resolve()),
        max_turns=config.workflow.max_turns_per_session,
        permission_mode=config.workflow.permission_mode,
        allowed_tools=config.security.allowed_tools,
    )

    console.print(f"\n[bold cyan]--- Session {session_num} started (model: {model}) ---[/bold cyan]")
    console.print(f"[dim]Working directory: {cwd}[/dim]")

    response_text = ""
    result_msg: ResultMessage | None = None

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    response_text += block.text
                    console.print(block.text, end="")
                elif isinstance(block, ToolUseBlock):
                    console.print(f"\n[dim][Tool: {block.name}][/dim]", end="")

        elif isinstance(message, UserMessage):
            if isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, ToolResultBlock) and block.is_error:
                        err_text = str(block.content)[:200] if block.content else "unknown error"
                        console.print(f"\n[red][Error] {err_text}[/red]")

        elif isinstance(message, ResultMessage):
            result_msg = message

    return response_text, result_msg


def _print_status(task_list: TaskList, session_num: int) -> None:
    done, total = task_list.stats()
    table = Table(title=f"Progress after session {session_num}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Completed", str(done))
    table.add_row("Total", str(total))
    table.add_row("Remaining", str(total - done))
    if total > 0:
        table.add_row("Percentage", f"{done/total*100:.1f}%")
    console.print(table)


async def run_workflow(
    workflow_dir: Path,
    spec: str | None = None,
) -> None:
    """Main entry point: run the full init-then-loop workflow.

    Args:
        workflow_dir: Directory containing config.yaml, task_list.json, etc.
        spec: User specification text (used only if no task list exists yet).
    """
    ensure_dirs(workflow_dir)
    config = _load_or_init_config(workflow_dir)
    cwd = config.resolve_cwd(workflow_dir)
    task_list = TaskList(workflow_dir)

    console.print(f"[dim]Workflow dir: {workflow_dir}[/dim]")
    console.print(f"[dim]Working dir:  {cwd}[/dim]")

    # Track interrupt requests
    interrupted = False

    def _on_interrupt(signum, frame):
        nonlocal interrupted
        if interrupted:
            console.print("\n[bold red]Force quit.[/bold red]")
            sys.exit(1)
        interrupted = True
        console.print(
            "\n[yellow]Interrupt received. Will stop after current session completes. "
            "Press Ctrl+C again to force quit.[/yellow]"
        )

    signal.signal(signal.SIGINT, _on_interrupt)

    # ── Phase 1: Initializer (if no task list exists) ────────────────────────
    if not task_list.exists():
        if not spec:
            console.print("[red]No task list found and no spec provided. Run `agent-nebula init` first.[/red]")
            return

        console.print(Panel("Phase 1: Initializer Agent", style="bold magenta"))
        session_num = next_session_number(workflow_dir)

        prompt = build_initializer_prompt(
            workflow_dir=workflow_dir,
            cwd=cwd,
            spec=spec,
            project_name=config.name,
            project_type=config.project_type,
            tech_stack=config.tech_stack,
        )

        response_text, result_msg = await run_single_session(
            cwd=cwd,
            config=config,
            prompt=prompt,
            model=config.workflow.model_complex,
            session_num=session_num,
        )

        task_list = TaskList(workflow_dir)
        done, total = task_list.stats()
        save_session_summary(
            workflow_dir=workflow_dir,
            session_num=session_num,
            model=config.workflow.model_complex,
            prompt_excerpt=prompt[:500],
            result_text=response_text,
            duration_ms=result_msg.duration_ms if result_msg else 0,
            num_turns=result_msg.num_turns if result_msg else 0,
            cost_usd=result_msg.total_cost_usd if result_msg and result_msg.total_cost_usd else 0.0,
            tasks_before=0,
            tasks_after=done,
            total_tasks=total,
        )

        _print_status(task_list, session_num)
        console.print("[green]Initializer complete. Starting worker loop...[/green]\n")

        if interrupted:
            console.print("[yellow]Stopping (interrupt received).[/yellow]")
            return

        await asyncio.sleep(config.workflow.session_delay_seconds)

    # ── Phase 2: Worker loop (infinite) ──────────────────────────────────────
    console.print(Panel("Phase 2: Worker Agent Loop", style="bold magenta"))
    max_sessions = config.workflow.max_sessions
    session_count = 0

    while True:
        if interrupted:
            console.print("[yellow]Stopping (interrupt received).[/yellow]")
            break

        task_list = TaskList(workflow_dir)
        done, total = task_list.stats()
        pending = task_list.pending()

        if not pending:
            console.print(Panel(
                f"[bold green]All {total} tasks completed![/bold green]",
                title="Workflow Complete",
            ))
            break

        if max_sessions > 0:
            session_count += 1
            if session_count > max_sessions:
                console.print(f"[yellow]Reached max sessions ({max_sessions}). Stopping.[/yellow]")
                break

        session_num = next_session_number(workflow_dir)
        tasks_before = done

        next_task = pending[0]
        model = _select_model(config, next_task)

        prompt = build_worker_prompt(
            workflow_dir=workflow_dir,
            cwd=cwd,
            config=config,
            session_num=session_num,
        )

        response_text, result_msg = await run_single_session(
            cwd=cwd,
            config=config,
            prompt=prompt,
            model=model,
            session_num=session_num,
        )

        task_list = TaskList(workflow_dir)
        done, total = task_list.stats()
        save_session_summary(
            workflow_dir=workflow_dir,
            session_num=session_num,
            model=model,
            prompt_excerpt=prompt[:500],
            result_text=response_text,
            duration_ms=result_msg.duration_ms if result_msg else 0,
            num_turns=result_msg.num_turns if result_msg else 0,
            cost_usd=result_msg.total_cost_usd if result_msg and result_msg.total_cost_usd else 0.0,
            tasks_before=tasks_before,
            tasks_after=done,
            total_tasks=total,
        )

        _print_status(task_list, session_num)

        if not interrupted:
            console.print(
                f"[dim]Next session in {config.workflow.session_delay_seconds}s "
                f"(Ctrl+C to stop)...[/dim]"
            )
            await asyncio.sleep(config.workflow.session_delay_seconds)


def _load_or_init_config(workflow_dir: Path) -> ProjectConfig:
    """Load config.yaml from workflow_dir, or return default config."""
    try:
        return ProjectConfig.load(workflow_dir)
    except FileNotFoundError:
        from agent_nebula.config import detect_project
        cwd = workflow_dir.parent
        return detect_project(cwd)


def _select_model(config: ProjectConfig, task) -> str:
    """Select opus for complex tasks, sonnet for simpler ones."""
    if task.priority <= 1 or task.category in ("analysis", "feature"):
        return config.workflow.model_complex
    return config.workflow.model_simple

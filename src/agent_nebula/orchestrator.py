"""Core orchestrator: the infinite session loop.

Key design: workflow_dir and cwd are independent.
- workflow_dir: where task_list.json, progress.md, session_history/ live
- cwd: where Claude agent reads/writes project files (from config.cwd)
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
import threading
from pathlib import Path

# Allow launching Claude Code sessions from within an existing session.
os.environ.pop("CLAUDECODE", None)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import json as _json

from claude_code_sdk import (
    query,
    ClaudeCodeOptions,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ThinkingBlock,
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

# ─── Dashboard integration ─────────────────────────────────────────────────
# Import lazily to keep dashboard optional
_dashboard = None

def _init_dashboard(workflow_dir: Path):
    global _dashboard
    try:
        from agent_nebula import dashboard
        dashboard.set_workflow_dir(workflow_dir)
        _dashboard = dashboard
    except ImportError:
        pass

def _dash_log(line: str):
    if _dashboard:
        try:
            _dashboard.append_log(line)
        except Exception:
            pass

def _dash_session(**kwargs):
    if _dashboard:
        try:
            _dashboard.update_session_state(**kwargs)
        except Exception:
            pass

def _dash_task_update():
    """Notify dashboard that task_list.json changed."""
    if _dashboard:
        try:
            asyncio.ensure_future(_dashboard._broadcast({"type": "task_update"}))
        except Exception:
            pass


# ─── Session runner ─────────────────────────────────────────────────────────

def _serialize_message(message) -> dict:
    """Serialize a Claude SDK message to a JSON-safe dict for JSONL storage."""
    if isinstance(message, AssistantMessage):
        blocks = []
        for b in message.content:
            if isinstance(b, TextBlock):
                blocks.append({"type": "text", "text": b.text})
            elif isinstance(b, ToolUseBlock):
                inp = b.input
                # Truncate very large tool inputs for storage
                inp_str = _json.dumps(inp, ensure_ascii=False, default=str)
                if len(inp_str) > 5000:
                    inp = {"_truncated": True, "_preview": inp_str[:2000]}
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": inp})
            elif isinstance(b, ThinkingBlock):
                blocks.append({"type": "thinking", "thinking": b.thinking[:3000]})
            else:
                blocks.append({"type": type(b).__name__})
        return {"role": "assistant", "model": getattr(message, "model", ""), "content": blocks}

    elif isinstance(message, UserMessage):
        blocks = []
        if isinstance(message.content, str):
            blocks.append({"type": "text", "text": message.content})
        elif isinstance(message.content, list):
            for b in message.content:
                if isinstance(b, ToolResultBlock):
                    content_str = str(b.content)[:3000] if b.content else ""
                    blocks.append({
                        "type": "tool_result", "tool_use_id": b.tool_use_id,
                        "is_error": b.is_error or False, "content": content_str,
                    })
                else:
                    blocks.append({"type": type(b).__name__})
        return {"role": "user", "content": blocks}

    elif isinstance(message, SystemMessage):
        return {"role": "system", "subtype": message.subtype, "data": message.data}

    elif isinstance(message, ResultMessage):
        return {
            "role": "result", "subtype": message.subtype,
            "is_error": message.is_error, "num_turns": message.num_turns,
            "duration_ms": message.duration_ms, "session_id": message.session_id,
            "total_cost_usd": message.total_cost_usd,
            "result": message.result[:2000] if message.result else None,
        }

    return {"role": "unknown", "type": type(message).__name__}


async def run_single_session(
    workflow_dir: Path,
    cwd: Path,
    config: ProjectConfig,
    prompt: str,
    model: str,
    session_num: int,
) -> tuple[str, ResultMessage | None]:
    """Run a single Claude Code SDK session with full JSONL recording."""

    options = ClaudeCodeOptions(
        model=model,
        cwd=str(cwd.resolve()),
        max_turns=config.workflow.max_turns_per_session,
        permission_mode=config.workflow.permission_mode,
        allowed_tools=config.security.allowed_tools,
    )

    console.print(f"\n[bold cyan]--- Session {session_num} started (model: {model}) ---[/bold cyan]")
    console.print(f"[dim]Working directory: {cwd}[/dim]")
    _dash_log(f"--- Session {session_num} started (model: {model}) ---")
    _dash_session(
        session_num=session_num, phase="working", model=model,
        started_at=time.time(),
    )

    # JSONL file for this session
    jsonl_dir = workflow_dir / "session_messages"
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = jsonl_dir / f"session_{session_num:04d}.jsonl"

    response_text = ""
    result_msg: ResultMessage | None = None
    msg_index = 0

    try:
        with open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
            # Record the prompt as the first entry
            jsonl_file.write(_json.dumps({
                "index": 0, "ts": time.time(), "role": "prompt",
                "content": prompt[:5000], "model": model,
            }, ensure_ascii=False, default=str) + "\n")
            jsonl_file.flush()

            # Do NOT break out of the generator — let it finish naturally.
            # Breaking causes anyio cancel scope errors that crash the event loop.
            async for message in query(prompt=prompt, options=options):
                msg_index += 1
                serialized = _serialize_message(message)
                serialized["index"] = msg_index
                serialized["ts"] = time.time()

                # Write to JSONL
                jsonl_file.write(_json.dumps(serialized, ensure_ascii=False, default=str) + "\n")
                jsonl_file.flush()

                # Broadcast to dashboard
                _dash_broadcast_msg(session_num, serialized)

                # Console output + log
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                            console.print(block.text, end="")
                            _dash_log(block.text)
                        elif isinstance(block, ToolUseBlock):
                            tool_info = f"[Tool: {block.name}]"
                            console.print(f"\n[dim]{tool_info}[/dim]", end="")
                            _dash_log(tool_info)

                elif isinstance(message, UserMessage):
                    if isinstance(message.content, list):
                        for block in message.content:
                            if isinstance(block, ToolResultBlock) and block.is_error:
                                err_text = str(block.content)[:200] if block.content else "unknown error"
                                console.print(f"\n[red][Error] {err_text}[/red]")
                                _dash_log(f"[Error] {err_text}")

                elif isinstance(message, ResultMessage):
                    result_msg = message
                    # Don't break — let the generator reach StopAsyncIteration naturally

    except Exception as e:
        if result_msg is not None:
            console.print(f"\n[dim](post-session cleanup: {type(e).__name__})[/dim]")
        else:
            console.print(f"\n[red]Session error: {e}[/red]")
            _dash_log(f"Session error: {e}")
            raise

    _dash_log(f"--- Session {session_num} finished ({msg_index} messages) ---")
    return response_text, result_msg


def _dash_broadcast_msg(session_num: int, serialized: dict):
    """Broadcast a structured message to dashboard WebSocket clients."""
    if _dashboard:
        try:
            asyncio.ensure_future(_dashboard._broadcast({
                "type": "session_message",
                "session_num": session_num,
                "message": serialized,
            }))
        except Exception:
            pass


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


# ─── Workflow loop ──────────────────────────────────────────────────────────

async def run_workflow(
    workflow_dir: Path,
    spec: str | None = None,
    dashboard_port: int = 8765,
    no_dashboard: bool = False,
) -> None:
    """Main entry point: run the full init-then-loop workflow.

    Args:
        workflow_dir: Directory containing config.yaml, task_list.json, etc.
        spec: User specification text (used only if no task list exists yet).
        dashboard_port: Port for the web dashboard (default: 8765).
        no_dashboard: If True, skip starting the dashboard server.
    """
    ensure_dirs(workflow_dir)
    config = _load_or_init_config(workflow_dir)
    cwd = config.resolve_cwd(workflow_dir)
    task_list = TaskList(workflow_dir)

    console.print(f"[dim]Workflow dir: {workflow_dir}[/dim]")
    console.print(f"[dim]Working dir:  {cwd}[/dim]")

    # Start dashboard server
    if not no_dashboard:
        _init_dashboard(workflow_dir)
        _start_dashboard_server(dashboard_port)
        console.print(f"[bold green]Dashboard: http://localhost:{dashboard_port}[/bold green]")

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

    # ── Phase 1: Initializer (if no task list exists) ─────────────────────
    if not task_list.exists():
        if not spec:
            console.print("[red]No task list found and no spec provided. Run `agent-nebula init` first.[/red]")
            return

        console.print(Panel("Phase 1: Initializer Agent", style="bold magenta"))
        _dash_session(phase="initializing", current_task_id=None)
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
            workflow_dir=workflow_dir,
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
        _dash_task_update()
        console.print("[green]Initializer complete. Starting worker loop...[/green]\n")

        if interrupted:
            console.print("[yellow]Stopping (interrupt received).[/yellow]")
            _dash_session(phase="idle")
            return

        await asyncio.sleep(config.workflow.session_delay_seconds)

    # ── Phase 2: Worker loop (infinite) ───────────────────────────────────
    console.print(Panel("Phase 2: Worker Agent Loop", style="bold magenta"))
    max_sessions = config.workflow.max_sessions
    session_count = 0

    while True:
        if interrupted:
            console.print("[yellow]Stopping (interrupt received).[/yellow]")
            _dash_session(phase="idle")
            break

        task_list = TaskList(workflow_dir)
        done, total = task_list.stats()
        pending = task_list.pending()

        if not pending:
            console.print(Panel(
                f"[bold green]All {total} tasks completed![/bold green]",
                title="Workflow Complete",
            ))
            _dash_session(phase="completed")
            break

        if max_sessions > 0:
            session_count += 1
            if session_count > max_sessions:
                console.print(f"[yellow]Reached max sessions ({max_sessions}). Stopping.[/yellow]")
                _dash_session(phase="idle")
                break

        session_num = next_session_number(workflow_dir)
        tasks_before = done

        next_task = pending[0]
        model = _select_model(config, next_task)

        _dash_session(
            phase="working",
            current_task_id=next_task.id,
            session_num=session_num,
            model=model,
            started_at=time.time(),
        )

        prompt = build_worker_prompt(
            workflow_dir=workflow_dir,
            cwd=cwd,
            config=config,
            session_num=session_num,
        )

        response_text, result_msg = await run_single_session(
            workflow_dir=workflow_dir,
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
        _dash_task_update()

        if not interrupted:
            console.print(
                f"[dim]Next session in {config.workflow.session_delay_seconds}s "
                f"(Ctrl+C to stop)...[/dim]"
            )
            try:
                await asyncio.sleep(config.workflow.session_delay_seconds)
            except (asyncio.CancelledError, RuntimeError):
                # SDK cancel scope may leak and cancel this sleep — safe to ignore
                await asyncio.sleep(0.1)  # Brief yield to let cleanup finish

    # Keep dashboard alive after workflow completes/stops
    if not no_dashboard:
        _dash_session(phase="idle")
        console.print(
            f"\n[bold green]Workflow finished. Dashboard still running at "
            f"http://localhost:{dashboard_port}[/bold green]"
        )
        console.print("[dim]Press Ctrl+C to shut down dashboard.[/dim]")
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, asyncio.CancelledError):
            console.print("\n[dim]Dashboard shut down.[/dim]")


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


def _start_dashboard_server(port: int) -> None:
    """Start the FastAPI dashboard in a background daemon thread."""
    import uvicorn
    from agent_nebula.dashboard import app

    config = uvicorn.Config(
        app, host="0.0.0.0", port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

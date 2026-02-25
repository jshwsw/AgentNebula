"""State management: workflow directory, progress notes, session history.

All functions take `workflow_dir` directly — the directory where AgentNebula
stores its state files. This is independent of the Claude agent's working
directory (cwd).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def ensure_dirs(workflow_dir: Path) -> None:
    """Create the workflow directory tree if not present."""
    (workflow_dir / "session_history").mkdir(parents=True, exist_ok=True)


# ── progress.md ──────────────────────────────────────────────────────────────

def read_progress(workflow_dir: Path) -> str:
    path = workflow_dir / "progress.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_progress(workflow_dir: Path, content: str) -> None:
    path = workflow_dir / "progress.md"
    path.write_text(content, encoding="utf-8")


# ── session history ──────────────────────────────────────────────────────────

def next_session_number(workflow_dir: Path) -> int:
    hist_dir = workflow_dir / "session_history"
    if not hist_dir.exists():
        return 1
    existing = list(hist_dir.glob("session_*.md"))
    if not existing:
        return 1
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem.split("_")[1]))
        except (IndexError, ValueError):
            pass
    return max(nums, default=0) + 1


def save_session_summary(
    workflow_dir: Path,
    session_num: int,
    model: str,
    prompt_excerpt: str,
    result_text: str,
    duration_ms: int,
    num_turns: int,
    cost_usd: float | None,
    tasks_before: int,
    tasks_after: int,
    total_tasks: int,
) -> Path:
    """Persist a one-page summary of a completed session."""
    hist_dir = workflow_dir / "session_history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    path = hist_dir / f"session_{session_num:04d}.md"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cost_str = f"${cost_usd:.4f}" if cost_usd is not None else "N/A"
    content = f"""# Session {session_num}

- **Time**: {ts}
- **Model**: {model}
- **Duration**: {duration_ms / 1000:.1f}s
- **Turns**: {num_turns}
- **Cost**: {cost_str} USD
- **Tasks completed this session**: {tasks_after - tasks_before}
- **Overall progress**: {tasks_after}/{total_tasks}

## Prompt excerpt
```
{prompt_excerpt[:500]}
```

## Result summary
{result_text[:2000]}
"""
    path.write_text(content, encoding="utf-8")
    return path


# ── spec file ────────────────────────────────────────────────────────────────

def read_spec(workflow_dir: Path) -> str:
    """Read the user-provided specification file."""
    path = workflow_dir / "spec.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_spec(workflow_dir: Path, content: str) -> None:
    path = workflow_dir / "spec.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

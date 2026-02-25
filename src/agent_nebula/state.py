"""State management: .agent-workflow/ directory, progress notes, session history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent_nebula.config import WORKFLOW_DIR


def workflow_dir(project_dir: Path) -> Path:
    return project_dir / WORKFLOW_DIR


def ensure_dirs(project_dir: Path) -> None:
    """Create the .agent-workflow/ directory tree if not present."""
    wd = workflow_dir(project_dir)
    (wd / "session_history").mkdir(parents=True, exist_ok=True)


# ── progress.md ──────────────────────────────────────────────────────────────

def read_progress(project_dir: Path) -> str:
    path = workflow_dir(project_dir) / "progress.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_progress(project_dir: Path, content: str) -> None:
    path = workflow_dir(project_dir) / "progress.md"
    path.write_text(content, encoding="utf-8")


# ── session history ──────────────────────────────────────────────────────────

def next_session_number(project_dir: Path) -> int:
    hist_dir = workflow_dir(project_dir) / "session_history"
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
    project_dir: Path,
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
    hist_dir = workflow_dir(project_dir) / "session_history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    path = hist_dir / f"session_{session_num:04d}.md"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = f"""# Session {session_num}

- **Time**: {ts}
- **Model**: {model}
- **Duration**: {duration_ms / 1000:.1f}s
- **Turns**: {num_turns}
- **Cost**: ${cost_usd:.4f} USD
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

def read_spec(project_dir: Path) -> str:
    """Read the user-provided specification file."""
    path = workflow_dir(project_dir) / "spec.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def write_spec(project_dir: Path, content: str) -> None:
    path = workflow_dir(project_dir) / "spec.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

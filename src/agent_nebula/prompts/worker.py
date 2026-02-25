"""Prompt template for the Worker session (Phase 2+).

Each Worker session:
1. Reads current state (progress.md + task_list.json)
2. Picks the next pending task
3. Implements it
4. Updates task_list.json (passes: true)
5. Updates progress.md
6. Optionally commits via git
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_nebula.config import WORKFLOW_DIR, ProjectConfig
from agent_nebula.tasks import TaskList


def build_worker_prompt(
    project_dir: Path,
    config: ProjectConfig,
    session_num: int,
) -> str:
    workflow_dir = project_dir / WORKFLOW_DIR
    task_list_path = workflow_dir / "task_list.json"
    progress_path = workflow_dir / "progress.md"

    # Load current state
    tl = TaskList(project_dir)
    done_count, total_count = tl.stats()
    pending = tl.pending()

    # Read progress notes
    progress_text = ""
    if progress_path.exists():
        progress_text = progress_path.read_text(encoding="utf-8")

    # Format pending tasks
    pending_section = ""
    if pending:
        pending_lines = []
        for i, t in enumerate(pending[:10]):  # show at most 10
            deps = f" (depends on: {', '.join(t.dependencies)})" if t.dependencies else ""
            pending_lines.append(
                f"  {i+1}. [{t.id}] (p{t.priority}, {t.category}) {t.description}{deps}"
            )
            if t.notes:
                pending_lines.append(f"     Note from previous session: {t.notes}")
        pending_section = "\n".join(pending_lines)
    else:
        pending_section = "  (no pending tasks — all work may be complete)"

    # Recent session history
    hist_dir = workflow_dir / "session_history"
    recent_sessions = ""
    if hist_dir.exists():
        session_files = sorted(hist_dir.glob("session_*.md"))[-3:]  # last 3
        for sf in session_files:
            recent_sessions += f"\n--- {sf.name} ---\n{sf.read_text(encoding='utf-8')[:800]}\n"

    return f"""You are the **Worker Agent** for the AgentNebula workflow system, Session #{session_num}.

## Context
- **Project directory**: {project_dir}
- **Project name**: {config.name}
- **Project type**: {config.project_type}
- **Tech stack**: {', '.join(config.tech_stack) if config.tech_stack else 'unknown'}
- **Overall progress**: {done_count}/{total_count} tasks completed
- **Session number**: {session_num}

## Current Progress Notes
{progress_text if progress_text else "(no progress notes yet)"}

## Recent Session History
{recent_sessions if recent_sessions else "(first worker session)"}

## Pending Tasks (next up)
{pending_section}

## Your Workflow (follow these steps precisely)

### Step 1: Orient
- Read the progress notes and recent session history above
- Understand what has been done and what remains

### Step 2: Select a task
- Pick the **first available task** from the pending list above (it's already priority-sorted)
- If no tasks are available, report completion and end

### Step 3: Implement
- Execute the task as described
- Follow the acceptance criteria carefully
- If the task has metadata (e.g., source file paths), use them

### Step 4: Verify
- Check that all acceptance criteria are met
- If there's a test/build command configured, run it

### Step 5: Update state files
After completing the task, you MUST update two files:

**a) Update task_list.json** (`{task_list_path}`):
- Read the current file
- Set `passes: true` for the completed task
- Set `session_attempted: {session_num}`
- Add any notes for future sessions in the `notes` field
- Write the file back (preserve all other tasks unchanged)

**b) Update progress.md** (`{progress_path}`):
- Add a section for this session at the top
- Include: what was done, any issues encountered, suggestions for next session
- Keep previous content intact

### Step 6: Git commit (if appropriate)
- If meaningful work was done, create a git commit with a descriptive message
- Format: `[AgentNebula S{session_num:04d}] <brief description of what was done>`

### Step 7: End session
- Report what was accomplished
- If you encountered blockers, note them clearly in progress.md

## Rules
- Complete **exactly ONE task** per session (focus is key)
- Do NOT modify tasks you're not working on
- If a task is too large, note this in progress.md — the orchestrator will handle replanning
- If you encounter errors, document them in the task's `notes` field and in progress.md
- Quality over speed: do the task correctly rather than rushing through it
"""

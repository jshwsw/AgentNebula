"""Prompt template for the Worker session (Phase 2+)."""

from __future__ import annotations

from pathlib import Path

from agent_nebula.config import ProjectConfig
from agent_nebula.tasks import TaskList


def build_worker_prompt(
    workflow_dir: Path,
    cwd: Path,
    config: ProjectConfig,
    session_num: int,
) -> tuple[str, str]:
    """Build worker prompt. Returns (user_prompt, system_prompt_extra).

    The spec content goes into system_prompt_extra (appended to system prompt)
    to avoid hitting Windows command line length limits. The user prompt
    contains only the current session's task and state information.
    """
    task_list_path = workflow_dir / "task_list.json"
    progress_path = workflow_dir / "progress.md"

    # Load current state
    tl = TaskList(workflow_dir)
    done_count, total_count = tl.stats()
    pending = tl.pending()

    # Read progress notes
    progress_text = ""
    if progress_path.exists():
        progress_text = progress_path.read_text(encoding="utf-8")

    # Read spec (task-specific execution instructions)
    spec_path = workflow_dir / "spec.md"
    spec_text = ""
    if spec_path.exists():
        spec_text = spec_path.read_text(encoding="utf-8")

    # Format pending tasks
    if pending:
        pending_lines = []
        for i, t in enumerate(pending[:10]):
            deps = f" (depends on: {', '.join(t.dependencies)})" if t.dependencies else ""
            pending_lines.append(
                f"  {i+1}. [{t.id}] (p{t.priority}, {t.category}) {t.description}{deps}"
            )
            if t.notes:
                pending_lines.append(f"     Note from previous session: {t.notes}")
            if t.metadata:
                meta_str = ", ".join(f"{k}={v}" for k, v in t.metadata.items() if isinstance(v, str))
                if meta_str:
                    pending_lines.append(f"     Metadata: {meta_str}")
        pending_section = "\n".join(pending_lines)
    else:
        pending_section = "  (no pending tasks -- all work may be complete)"

    # Recent session history
    hist_dir = workflow_dir / "session_history"
    recent_sessions = ""
    if hist_dir.exists():
        session_files = sorted(hist_dir.glob("session_*.md"))[-3:]
        for sf in session_files:
            recent_sessions += f"\n--- {sf.name} ---\n{sf.read_text(encoding='utf-8')[:800]}\n"

    prompt = f"""You are the **Worker Agent** for the AgentNebula workflow system, Session #{session_num}.

## Directory Layout
- **Working directory (cwd)**: {cwd}
  This is where you read/write project files.
- **Workflow state directory**: {workflow_dir}
  This is where task_list.json and progress.md live.

## Context
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
- **Read the Spec below** for task-specific instructions on how to execute this type of task

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
- If a task is too large, note this in progress.md -- the orchestrator will handle replanning
- If you encounter errors, document them in the task's `notes` field and in progress.md
- Quality over speed: do the task correctly rather than rushing through it
- The **Task Execution Guide** is in your system prompt — follow it carefully
"""

    # Spec goes into system prompt (avoids Windows command line length limits)
    system_extra = ""
    if spec_text:
        system_extra = f"""## Task Execution Guide

You are a Worker Agent in the AgentNebula workflow system. Follow the spec below to execute each task.

{spec_text}
"""

    return prompt, system_extra

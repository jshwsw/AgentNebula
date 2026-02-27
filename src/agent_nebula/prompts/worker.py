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
) -> str:
    """Build worker prompt.

    The spec content is NOT included in the prompt (too long for Windows CLI).
    Instead, the prompt instructs the agent to Read spec.md as its first action.
    """
    task_list_path = workflow_dir / "task_list.json"
    progress_path = workflow_dir / "progress.md"

    # Load current state
    tl = TaskList(workflow_dir)
    done_count, total_count = tl.stats()
    pending = tl.pending()

    # Read progress summary (should be short — agent overwrites it each session)
    progress_text = ""
    if progress_path.exists():
        progress_text = progress_path.read_text(encoding="utf-8")

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
        session_files = sorted(hist_dir.glob("session_*.md"))[-2:]  # Last 2 only
        for sf in session_files:
            recent_sessions += f"\n--- {sf.name} ---\n{sf.read_text(encoding='utf-8')[:500]}\n"

    prompt = f"""You are the **Worker Agent** for the AgentNebula workflow system, Session #{session_num}.

**IMPORTANT: Before doing anything else, Read the file `{workflow_dir / 'spec.md'}` — it contains the Task Execution Guide with step-by-step instructions for how to execute tasks in this workflow. You MUST follow it.**

## Directory Layout
- **Working directory (cwd)**: {cwd}
  This is where you read/write project files.
- **Workflow state directory**: {workflow_dir}
  This is where task_list.json and progress.md live.
  `discoveries.md` in this directory is an auto-archived log of all past session findings (read-only, do NOT write to it).

## Context
- **Project name**: {config.name}
- **Project type**: {config.project_type}
- **Tech stack**: {', '.join(config.tech_stack) if config.tech_stack else 'unknown'}
- **Overall progress**: {done_count}/{total_count} tasks completed
- **Session number**: {session_num}

## Progress Summary
{progress_text if progress_text else "(no progress summary yet)"}

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

**b) Overwrite progress.md** (`{progress_path}`):
- This is a **summary file** (NOT an append log). **Overwrite the entire file** each session.
- Keep it under 300 lines. Use this structure:

```markdown
# Progress: {{project_name}}

## Overall
- Completed: X / Y tasks (Z%)
- Sessions so far: N
- Current phase: [describe what stage the project is in]

## Last Session (#N)
- Task: [task ID and name]
- Result: [completed / blocked / partial]
- Key findings: [2-5 sentences summarizing what was learned]

## Key Discoveries
[Accumulate important cross-task findings, patterns, and insights discovered so far.
Keep this section growing across sessions — preserve valuable discoveries from previous progress.md.
Remove outdated or superseded entries. Aim for 10-30 bullet points.]

## Known Issues & TODOs
[Unresolved problems, recurring blockers, quality concerns, or improvement ideas.
Mark resolved items as done or remove them.]

## Next Up
- [next task ID and brief description]
```

### Step 6: End session
- Report what was accomplished
- If you encountered blockers, note them clearly in progress.md

## Rules
- Complete **exactly ONE task** per session (focus is key)
- Do NOT modify tasks you're not working on
- If a task is too large, note this in progress.md -- the orchestrator will handle replanning
- If you encounter errors, document them in the task's `notes` field and in progress.md
- Quality over speed: do the task correctly rather than rushing through it
- When using the Task tool to spawn sub-agents, ALWAYS set `model="sonnet"`. Do NOT use the default (haiku) model for sub-agents.
"""

    return prompt

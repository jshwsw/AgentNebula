# AgentNebula — Agent Handoff Document

This document captures the full development context for AgentNebula so a new agent can continue development seamlessly.

## 1. What AgentNebula Is

A universal infinite-loop workflow engine that drives Claude Code to autonomously execute large task lists. It implements the "shift engineer" pattern from Anthropic's official guidance: each session starts fresh, state is persisted to disk, and an orchestrator loop repeats until all tasks are done.

**Not a framework for a specific task** — AgentNebula is project-agnostic. All task-specific logic lives in the `.agent-nebula/` directory of each project (spec.md, tools, task_list.json).

## 2. Architecture

```
Orchestrator (orchestrator.py)
│
├── Phase 1: Initializer Agent
│   Reads spec.md → generates task_list.json
│
├── Phase 2: Worker Loop
│   while pending tasks:
│     1. Build worker prompt (session info, task list, progress)
│     2. Instruct agent to Read spec.md as first action
│     3. Launch Claude session via claude_code_sdk query()
│     4. Record all messages to JSONL
│     5. Broadcast to dashboard via WebSocket
│     6. Save session summary
│     7. Sleep 3s (interrupt window)
│
└── Dashboard (dashboard.py)
    FastAPI server on :8765, runs in background thread
    ├── GET /           → Task grid page
    ├── GET /session/{n} → Agent conversation detail page
    ├── GET /api/state   → Full state JSON
    ├── GET /api/session/{n}/messages → JSONL messages
    └── WS  /ws          → Real-time updates
```

### Key Files

| File | Role |
|------|------|
| `orchestrator.py` | Core loop, Claude SDK integration, JSONL recording |
| `dashboard.py` | FastAPI web UI (embedded HTML/CSS/JS), WebSocket broadcast |
| `cli.py` | CLI entry: init, run, status |
| `config.py` | Config management, workflow_dir/cwd separation, auto-detection |
| `tasks.py` | task_list.json CRUD, DAG dependency resolution |
| `state.py` | progress.md, session_history/, spec management |
| `prompts/worker.py` | Worker prompt template (instructs agent to Read spec.md) |
| `prompts/initializer.py` | Initializer prompt (generates task_list from spec) |

### Tools (user-facing scripts)

| Script | Purpose |
|--------|---------|
| `tools/setup_workflow.py` | Copy templates to project, patch config with cwd/name |
| `tools/run_workflow.py` | Auto-kill old processes, unset CLAUDECODE, launch orchestrator |
| `tools/stop_workflow.py` | Kill process on dashboard port |

## 3. Critical Design Decisions & Why

### spec.md is NOT injected into the prompt
**Problem**: Windows has a 32KB command line limit. The SDK passes all options (including system_prompt, append_system_prompt) as CLI arguments to the `claude` binary.
**Solution**: The worker prompt just says "Read spec.md at {path}". The agent reads it as its first action. This keeps the prompt short.

### No break from query() generator
**Problem**: Breaking out of `async for message in query()` causes anyio cancel scope errors that crash the event loop and prevent multi-session runs.
**Solution**: After receiving ResultMessage, we don't break — we let the generator reach StopAsyncIteration naturally. The `asyncio.sleep` between sessions is also wrapped in try/except CancelledError.

### No git commit in worker sessions
**Problem**: Output files typically land in git submodules. Committing from the parent repo fails with "pathspec in submodule" errors.
**Solution**: Worker prompt has no git commit step. spec.md explicitly says "DO NOT run git commit".

### workflow_dir vs cwd separation
**Problem**: Users want to run workflows from anywhere, and the workflow state directory may differ from where Claude should work.
**Solution**: `config.yaml` has a `cwd` field. The orchestrator passes `cwd` to Claude SDK, while reading state from `workflow_dir`.

### Task-specific tools live in .agent-nebula/tools/
**Problem**: Early versions put task-specific tools (like extract_script_usage.py) in the AgentNebula repo.
**Solution**: AgentNebula repo contains only framework code. All task-specific logic belongs in the project's `.agent-nebula/` directory.

## 4. Known Issues & Workarounds

| Issue | Status | Workaround |
|-------|--------|------------|
| Read tool 25000 token limit | Won't fix (Claude Code limitation) | spec.md instructs agent to read in chunks with offset/limit |
| Windows cp1252 encoding in python -c | Won't fix (OS limitation) | spec.md tells agent to use `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')` |
| Dashboard port conflict on restart | Fixed | run_workflow.py auto-kills existing process |
| CLAUDECODE env var blocks nested sessions | Fixed | `os.environ.pop("CLAUDECODE", None)` at module level |
| SDK cancel scope crash on multi-session | Fixed | Don't break from generator, protect sleep with try/except |
| Agent writes too-short Analysis docs | Fixed | spec.md has per-section quality requirements and 2000-2500 line target |

## 5. Production Validation

AgentNebula has been validated with a real 152-task workflow generating documentation for game engine scripts. As of session 14:

- **11 tasks completed** (T001-T011), each producing Analysis (1200-1875 lines) + Reference (273-480 lines)
- **Continuous multi-session runs** working after cancel scope fix
- **Dashboard** fully functional with real-time task grid, session detail, live log
- **extract_script_usage.py** reliably processes 17 roles of game data per script
- **Average session**: ~40 turns, completes 1 task per session

Key quality metrics from completed tasks:
- Analysis doc average: ~1450 lines (target: 2000-2500, improving with spec refinement)
- All sessions read C++ source code completely
- All sessions run extract tool and read all per-role files
- Zero data loss across sessions

## 6. What to Improve Next

### High Priority
- **Analysis doc length**: Current average ~1450 lines vs target 2000-2500. The spec has quality requirements but agents still write shorter than p0/p1/p2 benchmarks. May need to add a post-generation length check and retry mechanism.
- **Large file handling**: Some ScriptUsageLookup per-role files exceed 25000 tokens. Agent handles this via chunked reading, but it's slow. Could pre-split large files in extract_script_usage.py.

### Medium Priority
- **Parallel task execution**: Currently one task at a time. Independent tasks (no dependency overlap) could run in parallel with multiple Claude sessions.
- **Dashboard start/stop buttons**: Currently must use CLI. Web UI could have start/stop/pause controls.
- **Cost tracking aggregation**: Each session reports cost in ResultMessage but there's no cross-session total.
- **Task retry on failure**: If a session fails, the task stays pending and gets retried. But there's no backoff or max-retry limit.

### Low Priority
- **Session resume**: If a session is interrupted mid-task, it starts over. Could save partial state and resume.
- **Task reordering in dashboard**: Currently fixed by priority/ID. Could add drag-and-drop reorder.
- **Multi-workflow dashboard**: Dashboard shows one workflow at a time. Could support switching between workflows.

## 7. Repository Structure

```
AgentNebula/
├── src/agent_nebula/
│   ├── orchestrator.py      # Core loop + SDK integration
│   ├── dashboard.py         # FastAPI web UI (HTML embedded)
│   ├── cli.py               # init/run/status commands
│   ├── config.py            # Config + auto-detection
│   ├── tasks.py             # task_list.json management
│   ├── state.py             # progress.md + session history
│   └── prompts/
│       ├── initializer.py   # Phase 1 prompt
│       └── worker.py        # Phase 2 prompt
├── tools/
│   ├── setup_workflow.py    # Initialize .agent-nebula/ in project
│   ├── run_workflow.py      # Launch with auto-cleanup
│   └── stop_workflow.py     # Kill running workflow
├── docs/
│   ├── QUICKSTART.md        # Setup guide
│   ├── TASK_FORMAT.md       # task_list.json reference
│   ├── HANDOFF.md           # THIS FILE
│   ├── images/              # Dashboard screenshots
│   └── templates/           # Config, spec, task list templates
├── examples/
│   └── .agent-nebula/       # Real-world TitusEditor example
├── README.md
└── pyproject.toml
```

## 8. Dependencies

```
claude-code-sdk>=0.0.25   # Claude Code SDK (spawns claude CLI as subprocess)
pyyaml>=6.0               # Config file parsing
rich>=13.0                 # Terminal output formatting
fastapi>=0.100.0           # Dashboard web server
uvicorn>=0.20.0            # ASGI server for FastAPI
websockets>=11.0           # WebSocket support
```

Requires: Python 3.10+, Claude Code CLI (`npm install -g @anthropic-ai/claude-code`), active Claude subscription.

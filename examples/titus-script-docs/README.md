# Example: TitusEditor Script Documentation Workflow

This is a real-world example of an AgentNebula workflow that generates comprehensive documentation for 150+ script types in a game engine.

## What This Workflow Does

Generates two documents per script type:
- **_Analysis.md** (~2000-2500 lines): Deep analysis with C++ source code, KFD attributes, execution logic, real usage examples
- **_Reference.md** (~200-500 lines): Condensed quick reference for AI skill generation

## Files

| File | Purpose |
|------|---------|
| `config.yaml` | Workflow configuration — models, sessions, permissions |
| `spec.md` | Task execution instructions — how to generate each doc (read by worker agent) |
| `task_list_sample.json` | First 5 tasks from the full 152-task list |
| `progress.md` | Session progress notes |
| `HANDOFF.md` | Complete handoff document for agent continuity |
| `tools/extract_script_usage.py` | Pre-extracts per-script usage data from role analysis files |

## Key Design Patterns

1. **spec.md as the task manual** — All task-specific logic lives in spec.md, not in AgentNebula code
2. **Workflow-local tools** — `extract_script_usage.py` is specific to this workflow, not part of AgentNebula
3. **Per-section quality requirements** — spec.md specifies exact content expectations for each document section
4. **Pre-extracted data** — Worker agent runs a tool to extract focused data instead of parsing massive JSON files

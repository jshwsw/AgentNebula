# Task Format Reference

## task_list.json Structure

```json
{
  "tasks": [
    {
      "id":                  "T001",
      "category":            "docs",
      "priority":            0,
      "description":         "Generate documentation for UserService",
      "acceptance_criteria":  ["File exists", "Contains API examples"],
      "dependencies":        ["T000"],
      "passes":              false,
      "session_attempted":   null,
      "notes":               "",
      "metadata":            {}
    }
  ]
}
```

## Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique task identifier. Convention: T001, T002, ... |
| `category` | string | Yes | Task type. See categories below. |
| `priority` | int | Yes | Lower = higher priority. 0 is most urgent. |
| `description` | string | Yes | What the agent should do. Be specific. |
| `acceptance_criteria` | string[] | No | How to verify the task is done correctly. |
| `dependencies` | string[] | No | IDs of tasks that must complete first. |
| `passes` | bool | Auto | Set to `true` by the worker agent when done. |
| `session_attempted` | int\|null | Auto | Session number that completed this task. |
| `notes` | string | Auto | Notes left by the agent for future sessions. |
| `metadata` | object | No | Arbitrary key-value pairs for domain-specific context. |

## Categories

| Category | When to use |
|----------|-------------|
| `setup` | Project scaffolding, directory creation, config |
| `feature` | New functionality implementation |
| `bugfix` | Bug fixes |
| `refactor` | Code restructuring without behavior change |
| `docs` | Documentation generation or updates |
| `analysis` | Code analysis, research, investigation |
| `generation` | File generation (templates, configs, data) |
| `test` | Test writing or test infrastructure |

## Priority Levels

| Priority | Meaning | Model used |
|----------|---------|------------|
| 0 | Critical / must do first | `model_complex` (opus) |
| 1 | High importance | `model_complex` (opus) |
| 2 | Medium importance | `model_simple` (sonnet) |
| 3+ | Low importance | `model_simple` (sonnet) |

The orchestrator uses priority + category to select the model:
- Priority 0-1 or category `analysis`/`feature` → `model_complex`
- Everything else → `model_simple`

## Dependencies

Tasks form a DAG (Directed Acyclic Graph). A task only becomes available when ALL its dependencies have `passes: true`.

```json
{
  "id": "T003",
  "dependencies": ["T001", "T002"]
}
```
T003 will not run until both T001 and T002 are complete.

## Metadata

Use `metadata` for any domain-specific information the agent needs. Common patterns:

```json
{
  "metadata": {
    "source_file": "src/components/Button.tsx",
    "output_file": "docs/components/Button.md",
    "related_files": ["src/styles/button.css"],
    "script_name": "GSPlayVisualFXScriptData",
    "usage_count": 56,
    "usage_roles": ["60001", "60002", "60003"]
  }
}
```

The worker agent prompt includes metadata for the current task, so put anything the agent needs to know here.

## How the Worker Agent Uses task_list.json

1. Reads the file at the start of each session
2. Picks the first pending task (sorted by priority, then ID)
3. Executes the task following the description and acceptance criteria
4. Updates the file: sets `passes: true`, `session_attempted`, and `notes`
5. Saves the file back

The agent is instructed to modify ONLY the task it's working on and leave all others unchanged.

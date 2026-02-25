# Workflow-Local Tools

These tools are specific to the TitusEditor-ScriptDocs workflow. They are NOT part of AgentNebula framework.

## extract_script_usage.py

Extracts per-script usage data from all role analysis files into small, agent-friendly lookup files.

### What it does

Reads all `ExistSkillObjRef/<roleID>/role_<roleID>_analysis.json` files and for each script type:
- Aggregates total usage count across all roles
- Collects configuration samples (params from real game data)
- Extracts combination patterns (what other scripts appear alongside this one in the same keyframe)

Output: `ExistSkillObjRef/ScriptUsageLookup/<ScriptName>.json` (one small file per script type)

### When to run

- After adding new role data to `ExistSkillObjRef/` (e.g., generating analysis for roles 60012+)
- After modifying any `role_XXXXX_analysis.json` file
- Before starting the AgentNebula workflow if ScriptUsageLookup/ doesn't exist yet

### How to run

```bash
cd c:\Work\ProjAI\Claude_Sango
python .agent-nebula/tools/extract_script_usage.py
```

### Output format

Each `ScriptUsageLookup/<ScriptName>.json` contains:

```json
{
  "script_name": "GSLogScriptData",
  "total_count": 19,
  "roles": [
    {"role_id": "60001", "count": 5},
    {"role_id": "60002", "count": 3}
  ],
  "samples": [
    {
      "role_id": "60002",
      "state": 6000002,
      "frame": 1,
      "params": {"text": "..."}
    }
  ],
  "state_contexts": [
    {
      "role_id": "60004",
      "state": 1201,
      "frame": 92,
      "params": {"text": "..."},
      "companion_scripts": ["TSSetEffectParamUsingCurveData", "GSPlayVisualFXScriptData"]
    }
  ]
}
```

### Why this exists

The `role_XXXXX_full.json` files are tens of MB each. When the worker agent tries to read them to find usage examples for a specific script, it wastes most of its session parsing irrelevant data. This tool pre-extracts exactly what the agent needs into small, focused files (~200-400 lines each).

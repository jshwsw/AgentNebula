# TitusEditor Script Documentation Completion

## Goal
Generate comprehensive documentation for ALL undocumented script data types in the KF8 game engine.
Currently 31 out of ~140+ script types have documentation. This workflow will complete the remaining ones.

## What Already Exists

### Documented Scripts (31 total, DO NOT regenerate these)
Located in `Code/TitusEditor/docs/DataGeneration_AI/PreLearning/ScriptReadme/`
- p0/ (8 scripts): TSMoveScriptData, TSHitTestScriptData, TSAcceptVKeyScriptData, TSControl3DScriptData, TSSearchTargetScriptData, TSCancelActionScriptData, GSPlayVisualFXScriptData, TSPlayAudioData
- p1/ (11 scripts): GSClearAimsData, GSAddSStatusData, GSHandleEntityEnvInteractionData, GSControlCameraData, TSHitRuleData, GSBranchScriptData, GSCondBranchScriptData, TSNextStateScriptData, GSVariableScriptData, GSCreateEntityData, TSSetHiddenData
- p2/ (12 scripts): TSSetEffectParamUsingCurveData, GSCreateEnvItemData, TSLandScriptData, GSDelSStatusData, TSAcceptEventData, TSNextActionScriptData, TSMoveByCurveData, GSSetFxParamData, TSTrackTargetScriptData, GSAnimationModifyBoneData, TSUIControlData, TSAddFaceAnimationData

### Reference documents (simplified versions)
Located in `.claude/skills/slash-tituseditor-skill-generator/ScriptReference/`
Same 31 scripts have corresponding _Reference.md files.

## Source Code Locations

### C++ Script Source Files
Base path: `Code/Titus/Plugins/Kungfu8/Source/kf8GamePlay/Script/`
- Data definitions (headers): `Script/Data/` (e.g., TSMoveData.h)
- Target Script implementations: `Script/Target/` (e.g., TSMoveScript.cpp)
- Global Script implementations: `Script/Global/` (e.g., GSClearAimsScript.cpp)
- Camera scripts: `Script/Target/Camera/`
- Trigger scripts: `Script/Trigger/`
- BehaviorTree scripts: `Script/Data/BTS*.h`
- Condition scripts: `Script/Condition/`
- Progress scripts: `Script/Target/Progress/`
- Virgation scripts: `Script/Target/TSVirgationScripts.h`
- SimpleScriptDataDef: `Script/Data/SimpleScriptDataDef.h` (contains multiple simple script definitions)

### Real Usage Data (JSON)
Base path: `Code/TitusEditor/docs/DataGeneration_AI/Workflow/ExistSkillObjRef/`
- 10 roles available: 60001-60010
- Each role has `role_XXXXX_full.json` (complete skill data) and `role_XXXXX_analysis.json` (script usage statistics)
- Use these to find real-world usage examples for each script type

## Output Requirements

### For each undocumented script, generate TWO files:

#### 1. Analysis Document (_Analysis.md)
**Output path**: `Code/TitusEditor/docs/DataGeneration_AI/PreLearning/ScriptReadme/p3/<ScriptName>_Analysis.md`
(Use p3/ for all new scripts since p0/p1/p2 are already complete)

**Required sections** (follow the format of existing Analysis docs):
1. Basic Information (script type, class hierarchy, usage frequency from ExistSkillObjRef data, typical scenarios)
2. KFD Attribute Complete List (all parameters with types, defaults, enums)
3. Core Execution Logic (C++ code analysis, step-by-step flow)
4. Parameter Detailed Explanation (per parameter with usage examples)
5. Usage Scenarios (real cases from ExistSkillObjRef roles)
6. Configuration Examples (actual JSON configs from roles 60001-60010)
7. Related Scripts / Associations
8. Caveats and Notes
9. Patterns and Rules
10. Open Questions

**Target length**: 800-2500 lines per document (depends on script complexity)

#### 2. Reference Document (_Reference.md)
**Output path**: `.claude/skills/slash-tituseditor-skill-generator/ScriptReference/p3/<ScriptName>_Reference.md`

**Required sections** (follow the format of existing Reference docs):
1. Overview (purpose, frequency, core functions, typical scenarios)
2. JSON Data Structure (complete JSON with all fields, enum definitions)
3. Parameter Quick-Reference Table (merged table with grouped headers)
4. Typical Configuration Templates (3-4 ready-to-copy JSON templates)
5. Common Combination Patterns (how this script combines with others)
6. Caveats (common errors, best practices)

**Target length**: 200-500 lines per document

## Task Priorities

### Priority 0 (critical) - Primary Scripts used in game data
Focus on scripts that appear in ExistSkillObjRef data across multiple roles. Check role_XXXXX_analysis.json files to find which scripts are actually used.

### Priority 1 (high) - Global Scripts (GS*)
These provide game-wide functionality like conditions, loops, environment control.

### Priority 2 (medium) - Target Scripts (TS*) and Camera Scripts
Character-specific scripts and camera control.

### Priority 3 (low) - BehaviorTree (BTS*), Trigger, Condition, Progress scripts
Specialized subsystems.

## How to Execute Each Task (step by step)

For each script documentation task, follow this exact process:

### Step A: Read C++ Source Code (MUST do BOTH files)
1. Read the **header file** from task metadata `source_header` — this contains the data class definition, KFD attributes, enums
2. Read the **implementation file** from task metadata `source_impl` — this contains Execute() logic, helper methods
3. Read BOTH files **completely** — do not skim

**Handling large files**: If the Read tool reports "exceeds maximum allowed tokens", read the file in chunks:
```
Read file_path, offset=1, limit=1000      # lines 1-1000
Read file_path, offset=1001, limit=1000    # lines 1001-2000
Read file_path, offset=2001, limit=1000    # lines 2001-3000
... continue until the entire file is read
```
You MUST read ALL chunks — do not skip any part of the file.

### Step B: Extract and Read Usage Data
1. Run the extraction tool to generate per-role usage data for your script:
   ```bash
   python .agent-nebula/tools/extract_script_usage.py <ScriptName>
   ```
   For example: `python .agent-nebula/tools/extract_script_usage.py GSLogScriptData`

2. This generates a directory: `Code/TitusEditor/docs/DataGeneration_AI/Workflow/ExistSkillObjRef/ScriptUsageLookup/<ScriptName>/`
   containing:
   - `summary.json` — cross-role statistics: total count, per-role counts, top companion scripts, unique param keys
   - `60001_<ScriptName>.json` — every occurrence in role 60001 with full context
   - `60002_<ScriptName>.json` — every occurrence in role 60002 with full context
   - ... (one file per role that uses this script)

3. Read `summary.json` first to understand overall usage patterns. The `total_count` field is the **exact number of times this script appears** across all roles — use this number as the usage frequency in your document, do not count lines or array items yourself

4. **CRITICAL: You MUST read EVERY per-role file in the directory.** Use Glob to list all `60xxx_<ScriptName>.json` files, then Read each one completely. These files are small (a few KB each) and contain irreplaceable real-world usage data. Skipping any role means missing usage patterns that may be unique to that character. For each file, study:
   - Every occurrence's params (what values are actually used in real game data)
   - Companion scripts in the same keyframe (what scripts are commonly combined with this one)
   - Full keyframe context (all scripts and their params at that keyframe — this shows real script orchestration patterns)
   - State context (which state ID, frame number, state length, loop settings — this reveals timing patterns)

5. Only after reading ALL role files should you begin writing. Your Analysis document must reference specific examples from multiple roles to demonstrate the script's usage breadth.

6. **DO NOT** try to read `role_XXXXX_full.json` files — they are too large and will waste your session

### Step C: Read Format Examples
1. Read at least ONE existing Analysis doc from `p0/` or `p1/` (e.g., `GSPlayVisualFXScriptData_Analysis.md`) to match the exact format
2. Read at least ONE existing Reference doc from `p0/` (e.g., `GSPlayVisualFXScriptData_Reference.md`)

### Step D: Write the Analysis Document
1. Follow the 10-section format exactly
2. **Target 2000-2500 lines minimum** — existing p0/p1/p2 docs average 2500 lines. Your output MUST match this level of detail. Do NOT write a short summary.
3. Include real C++ code snippets from the source — copy the Execute() function, key helper methods, and KFD macro definitions verbatim
4. Include real JSON configuration examples from ScriptUsageLookup — use complete JSON blocks showing the full keyframe context (not just the target script's params, but ALL companion scripts in the same keyframe)
5. Include combination patterns (what other scripts are used together with this one, with complete JSON examples)

**Quality requirements for each section (study p0/p1/p2 examples to match their depth)**:
- **Section 3 (执行逻辑)**: Copy and analyze the ENTIRE Execute() function line by line. Include helper method code. Draw execution flow diagrams.
- **Section 4 (参数说明)**: For EACH parameter, include: type, default, range, enum values, real usage examples from multiple roles, **common mistakes with wrong vs correct JSON examples**, and C++ source code tracing showing how the parameter is used in Execute().
- **Section 5 (使用场景)**: Write 3-5 complete scenario analyses. Each scenario must include: full JSON config with all companion scripts, multi-frame execution timeline (e.g., "Frame 0: ScriptA → Frame 5: ScriptB → Frame 10: target script"), and explanation of WHY this combination is used.
- **Section 6 (配置示例)**: Provide 4-6 complete JSON configuration examples copied directly from ScriptUsageLookup role data. Include the surrounding keyframe context. Add Chinese comments explaining each field.
- **Section 7 (Script关联)**: For each companion script, explain the dependency relationship and provide a combined usage example with complete JSON.
- **Section 8 (注意事项)**: List 5+ common mistakes. Each mistake must have: wrong JSON config, consequence, and correct JSON config.
- **Section 9 (配置规律)**: Summarize parameter patterns observed across ALL roles with statistical analysis.

### Step E: Write the Reference Document
1. Follow the 6-section format exactly
2. Target 200-500 lines

## Important Rules

1. Each task should cover EXACTLY ONE script type (both Analysis + Reference)
2. Always read the C++ header AND implementation files for complete understanding
3. Use ScriptUsageLookup for usage data — NOT the massive role_XXXXX_full.json files
4. Do NOT modify or regenerate any existing p0/p1/p2 documents
5. Keep document format consistent with existing examples
6. Write all documents in Chinese (following existing convention)
7. If a script's header/source cannot be found, note this and skip it

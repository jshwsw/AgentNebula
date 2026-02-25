"""Extract per-script usage data from all role analysis files.

Creates a lookup directory where each script type has a small JSON file
containing usage statistics and real configuration examples from all roles.

Usage:
    python tools/extract_script_usage.py

Output: ExistSkillObjRef/ScriptUsageLookup/<ScriptName>.json
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Paths
BASE = Path("c:/Work/ProjAI/Claude_Sango/Code/TitusEditor/docs/DataGeneration_AI/Workflow")
EXIST_REF = BASE / "ExistSkillObjRef"
ANALYZED = BASE / "output" / "analyzed"
OUTPUT_DIR = EXIST_REF / "ScriptUsageLookup"


def extract_from_analysis_json(role_id: str, analysis_path: Path, result: dict):
    """Extract script usage data from a role_XXXXX_analysis.json file."""
    with open(analysis_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scripts = data.get("scripts", {})
    for script_name, info in scripts.items():
        if script_name not in result:
            result[script_name] = {
                "script_name": script_name,
                "total_count": 0,
                "roles": [],
                "samples": [],
                "state_contexts": [],
            }
        entry = result[script_name]
        count = info.get("count", 0)
        entry["total_count"] += count
        entry["roles"].append({"role_id": role_id, "count": count})

        # Collect samples (limit per role to avoid bloat)
        for sample in info.get("samples", [])[:5]:
            entry["samples"].append({
                "role_id": role_id,
                "state": sample.get("state"),
                "frame": sample.get("frame"),
                "params": sample.get("params", {}),
            })


def extract_from_full_json(role_id: str, full_path: Path, result: dict):
    """Extract script context data from role_XXXXX_full.json.

    Finds each script occurrence with its surrounding scripts in the same
    state/keyframe to capture combination patterns.
    """
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, MemoryError):
        print(f"  [WARN] Could not parse {full_path.name}")
        return

    # Navigate the data structure to find states with scripts
    # Structure: data -> states[] -> keyframes[] -> scripts[]
    states = []
    if isinstance(data, dict):
        states = data.get("states", [])
    if not states and isinstance(data, list):
        states = data

    for state in states:
        if not isinstance(state, dict):
            continue
        state_id = state.get("id") or state.get("name", "unknown")
        keyframes = state.get("keyframes", [])

        for kf in keyframes:
            if not isinstance(kf, dict):
                continue
            frame = kf.get("frame", 0)
            scripts_in_kf = kf.get("scripts", [])

            if not scripts_in_kf or len(scripts_in_kf) == 0:
                continue

            # For each script, record its combination context
            script_types_in_kf = [s.get("type", "") for s in scripts_in_kf if isinstance(s, dict)]

            for script in scripts_in_kf:
                if not isinstance(script, dict):
                    continue
                stype = script.get("type", "")
                if not stype or stype not in result:
                    continue

                entry = result[stype]
                # Limit state_contexts to avoid huge files
                if len(entry["state_contexts"]) < 20:
                    companions = [t for t in script_types_in_kf if t != stype]
                    entry["state_contexts"].append({
                        "role_id": role_id,
                        "state": state_id,
                        "frame": frame,
                        "params": script.get("params", {}),
                        "companion_scripts": companions[:10],
                    })


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result: dict = {}

    # Step 1: Process all analysis.json files
    print("Step 1: Extracting from analysis.json files...")
    for role_dir in sorted(EXIST_REF.iterdir()):
        if not role_dir.is_dir() or role_dir.name == "ScriptUsageLookup":
            continue
        role_id = role_dir.name
        analysis_file = role_dir / f"role_{role_id}_analysis.json"
        if analysis_file.exists():
            print(f"  Processing {role_id} analysis...")
            extract_from_analysis_json(role_id, analysis_file, result)

    # Also check output/analyzed/ directory
    if ANALYZED.exists():
        for f in sorted(ANALYZED.glob("role_*_analysis.json")):
            role_id = f.stem.split("_")[1]
            if any(role_id == r["role_id"] for entry in result.values() for r in entry.get("roles", [])):
                continue  # Already processed
            print(f"  Processing {role_id} from output/analyzed/...")
            extract_from_analysis_json(role_id, f, result)

    # Step 2: Process full.json files for combination context
    print("\nStep 2: Extracting combination contexts from analysis.json states...")
    for role_dir in sorted(EXIST_REF.iterdir()):
        if not role_dir.is_dir() or role_dir.name == "ScriptUsageLookup":
            continue
        role_id = role_dir.name
        analysis_file = role_dir / f"role_{role_id}_analysis.json"
        if analysis_file.exists():
            print(f"  Extracting contexts from {role_id}...")
            # Use analysis.json for state contexts (it has keyframes with scripts)
            try:
                with open(analysis_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                states = data.get("states", [])
                for state in states:
                    if not isinstance(state, dict):
                        continue
                    state_id = state.get("id", "?")
                    for kf in state.get("keyframes", []):
                        if not isinstance(kf, dict):
                            continue
                        scripts_in_kf = kf.get("scripts", [])
                        if not scripts_in_kf:
                            continue
                        script_types = [s.get("type", "") for s in scripts_in_kf if isinstance(s, dict)]
                        for script in scripts_in_kf:
                            if not isinstance(script, dict):
                                continue
                            stype = script.get("type", "")
                            if stype not in result:
                                continue
                            entry = result[stype]
                            if len(entry["state_contexts"]) < 20:
                                companions = [t for t in script_types if t != stype]
                                if companions:  # Only record when there are companion scripts
                                    entry["state_contexts"].append({
                                        "role_id": role_id,
                                        "state": state_id,
                                        "frame": kf.get("frame", 0),
                                        "params": script.get("params", {}),
                                        "companion_scripts": companions[:10],
                                    })
            except Exception as e:
                print(f"    [WARN] {e}")

    # Step 3: Write per-script lookup files
    print(f"\nStep 3: Writing {len(result)} script lookup files...")
    for script_name, entry in sorted(result.items()):
        # Sort roles by count descending
        entry["roles"].sort(key=lambda r: r["count"], reverse=True)
        # Deduplicate state_contexts
        seen = set()
        unique_contexts = []
        for ctx in entry["state_contexts"]:
            key = f"{ctx['role_id']}_{ctx['state']}_{ctx['frame']}"
            if key not in seen:
                seen.add(key)
                unique_contexts.append(ctx)
        entry["state_contexts"] = unique_contexts[:20]

        out_path = OUTPUT_DIR / f"{script_name}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

    print(f"\nDone! {len(result)} files written to {OUTPUT_DIR}")

    # Summary
    print("\nTop 20 scripts by usage:")
    sorted_scripts = sorted(result.items(), key=lambda x: x[1]["total_count"], reverse=True)
    for name, entry in sorted_scripts[:20]:
        roles = len(entry["roles"])
        print(f"  {name}: {entry['total_count']} uses across {roles} roles, {len(entry['samples'])} samples, {len(entry['state_contexts'])} contexts")


if __name__ == "__main__":
    main()

"""Extract per-script, per-role usage data from role analysis files.

For a given script name, scans ALL role analysis files and generates:
  ScriptUsageLookup/<ScriptName>/
    ├── summary.json              # Cross-role statistics
    ├── 60001_<ScriptName>.json   # Every occurrence in role 60001
    ├── 60002_<ScriptName>.json   # Every occurrence in role 60002
    └── ...

Usage:
    python .agent-nebula/tools/extract_script_usage.py <ScriptName>
    python .agent-nebula/tools/extract_script_usage.py --all

Run from project root (cwd).
"""

import json
import sys
from pathlib import Path
from collections import Counter

BASE = Path("Code/TitusEditor/docs/DataGeneration_AI/Workflow")
EXIST_REF = BASE / "ExistSkillObjRef"
ANALYZED = BASE / "output" / "analyzed"
OUTPUT_BASE = EXIST_REF / "ScriptUsageLookup"


def find_all_analysis_files() -> list[tuple[str, Path]]:
    """Find all role analysis JSON files."""
    sources = []
    seen = set()
    if EXIST_REF.exists():
        for d in sorted(EXIST_REF.iterdir()):
            if not d.is_dir() or d.name == "ScriptUsageLookup":
                continue
            af = d / f"role_{d.name}_analysis.json"
            if af.exists():
                sources.append((d.name, af))
                seen.add(d.name)
    if ANALYZED.exists():
        for f in sorted(ANALYZED.glob("role_*_analysis.json")):
            rid = f.stem.split("_")[1]
            if rid not in seen:
                sources.append((rid, f))
    return sources


def extract_one_script(script_name: str, sources: list[tuple[str, Path]]) -> dict:
    """Extract all occurrences of a script from all roles.

    Returns:
        {
            "summary": { cross-role stats },
            "roles": { "60001": { per-role detail }, ... }
        }
    """
    roles_data = {}
    total_count = 0
    all_companion_counts = Counter()

    for role_id, path in sources:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Collect every keyframe occurrence with full context + surrounding frames
        occurrences = []
        for state in data.get("states", []):
            if not isinstance(state, dict):
                continue
            state_id = state.get("id", "?")
            state_name = state.get("name", "")
            state_length = state.get("length", 0)
            state_loop = state.get("loop", False)

            # Build indexed keyframe list for this state (for nearby frame lookup)
            all_keyframes = []
            for kf in state.get("keyframes", []):
                if not isinstance(kf, dict):
                    continue
                kf_scripts = kf.get("scripts", [])
                if kf_scripts:
                    all_keyframes.append({
                        "frame": kf.get("frame", 0),
                        "scripts": [
                            {"type": s.get("type", ""), "params": s.get("params", {})}
                            for s in kf_scripts if isinstance(s, dict)
                        ],
                    })

            for kf_idx, kf_entry in enumerate(all_keyframes):
                # Check if target script is in this keyframe
                target_scripts = [
                    s for s in kf_entry["scripts"] if s["type"] == script_name
                ]
                if not target_scripts:
                    continue

                for scr in target_scripts:
                    # Same-frame companions
                    companions = [s["type"] for s in kf_entry["scripts"] if s["type"] != script_name]
                    for c in companions:
                        all_companion_counts[c] += 1

                    # Nearby frames: 3 before + 3 after
                    nearby_before = []
                    for i in range(max(0, kf_idx - 3), kf_idx):
                        nb = all_keyframes[i]
                        nearby_before.append({
                            "frame": nb["frame"],
                            "scripts": nb["scripts"],
                        })

                    nearby_after = []
                    for i in range(kf_idx + 1, min(len(all_keyframes), kf_idx + 4)):
                        nb = all_keyframes[i]
                        nearby_after.append({
                            "frame": nb["frame"],
                            "scripts": nb["scripts"],
                        })

                    occurrences.append({
                        "state_id": state_id,
                        "state_name": state_name,
                        "state_length": state_length,
                        "state_loop": state_loop,
                        "frame": kf_entry["frame"],
                        "params": scr["params"],
                        "group": scr.get("group", 0),
                        "companion_scripts": companions,
                        "keyframe_full_context": kf_entry["scripts"],
                        "nearby_frames_before": nearby_before,
                        "nearby_frames_after": nearby_after,
                    })

        if not occurrences:
            continue

        role_count = len(occurrences)
        total_count += role_count

        # Analyze parameter patterns for this role
        param_patterns = Counter()
        for occ in occurrences:
            params = occ["params"]
            # Create a pattern key from param keys + value types
            pattern = tuple(sorted(f"{k}={type(v).__name__}" for k, v in params.items()))
            param_patterns[pattern] += 1

        roles_data[role_id] = {
            "role_id": role_id,
            "count": role_count,
            "occurrences": occurrences,
            "param_patterns": [
                {"pattern": dict(kv.split("=") for kv in p), "count": c}
                for p, c in param_patterns.most_common(10)
            ],
        }

    # Build cross-role summary
    summary = {
        "script_name": script_name,
        "total_count": total_count,
        "roles_used": len(roles_data),
        "per_role_counts": {rid: rd["count"] for rid, rd in sorted(roles_data.items())},
        "top_companion_scripts": [
            {"script": name, "co_occurrence_count": cnt}
            for name, cnt in all_companion_counts.most_common(20)
        ],
        "unique_param_keys": sorted(set(
            k for rd in roles_data.values()
            for occ in rd["occurrences"]
            for k in occ["params"].keys()
        )),
    }

    return {"summary": summary, "roles": roles_data}


def write_output(script_name: str, result: dict):
    """Write per-role files + summary to ScriptUsageLookup/<ScriptName>/."""
    out_dir = OUTPUT_BASE / script_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write summary
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(result["summary"], f, indent=2, ensure_ascii=False)

    # Write per-role files
    for role_id, role_data in result["roles"].items():
        fname = f"{role_id}_{script_name}.json"
        with open(out_dir / fname, "w", encoding="utf-8") as f:
            json.dump(role_data, f, indent=2, ensure_ascii=False)

    s = result["summary"]
    print(f"{script_name}: {s['total_count']} occurrences across {s['roles_used']} roles")
    print(f"  Top companions: {', '.join(c['script'] for c in s['top_companion_scripts'][:5])}")
    print(f"  Param keys: {s['unique_param_keys']}")
    print(f"  Output: {out_dir}/")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python .agent-nebula/tools/extract_script_usage.py <ScriptName>")
        print("  python .agent-nebula/tools/extract_script_usage.py --all")
        sys.exit(1)

    sources = find_all_analysis_files()
    if not sources:
        print("[ERROR] No role analysis files found. Check ExistSkillObjRef/ and output/analyzed/")
        sys.exit(1)
    print(f"Found {len(sources)} role analysis files: {', '.join(s[0] for s in sources)}")

    arg = sys.argv[1]

    if arg == "--all":
        # Discover all script names across all roles
        all_scripts = set()
        for _, path in sources:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            all_scripts.update(data.get("scripts", {}).keys())
        print(f"Found {len(all_scripts)} unique script types\n")
        for name in sorted(all_scripts):
            result = extract_one_script(name, sources)
            if result["summary"]["total_count"] > 0:
                write_output(name, result)
    else:
        result = extract_one_script(arg, sources)
        if result["summary"]["total_count"] > 0:
            write_output(arg, result)
        else:
            print(f"[WARN] {arg} not found in any role data")


if __name__ == "__main__":
    main()

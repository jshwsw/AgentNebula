"""Set up a new AgentNebula workflow in any project directory.

Usage:
    python tools/setup_workflow.py                          # current directory
    python tools/setup_workflow.py /path/to/project         # specific directory
    python tools/setup_workflow.py /path/to/project --name "My Project"

This creates a .agent-nebula/ directory with config.yaml and template files,
ready for you to edit spec.md or task_list.json and start running.
"""

import argparse
import shutil
import sys
from pathlib import Path

# Resolve paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TEMPLATES_DIR = REPO_ROOT / "docs" / "templates"

WORKFLOW_SUBDIR = ".agent-nebula"


def setup(project_dir: Path, name: str | None = None) -> None:
    workflow_dir = project_dir / WORKFLOW_SUBDIR

    if workflow_dir.exists():
        print(f"[WARN] {workflow_dir} already exists. Skipping files that already exist.")
    else:
        workflow_dir.mkdir(parents=True)
        print(f"[OK] Created {workflow_dir}")

    # Copy templates (skip if already exists)
    copies = [
        (TEMPLATES_DIR / "config_template.yaml", workflow_dir / "config.yaml"),
        (TEMPLATES_DIR / "spec_template.md", workflow_dir / "spec.md"),
        (TEMPLATES_DIR / "task_list_template.json", workflow_dir / "task_list_template.json"),
    ]

    for src, dst in copies:
        if dst.exists():
            print(f"[SKIP] {dst.name} already exists")
            continue
        if not src.exists():
            print(f"[WARN] Template not found: {src}")
            continue
        shutil.copy2(src, dst)
        print(f"[OK] Copied {dst.name}")

    # Patch config.yaml with actual project path and name
    config_path = workflow_dir / "config.yaml"
    if config_path.exists():
        text = config_path.read_text(encoding="utf-8")
        text = text.replace(
            "cwd: /path/to/your/project",
            f"cwd: {project_dir.resolve()}",
        )
        project_name = name or project_dir.resolve().name
        text = text.replace(
            'name: "My Project Name"',
            f'name: "{project_name}"',
        )
        config_path.write_text(text, encoding="utf-8")
        print(f"[OK] Patched config.yaml (cwd={project_dir.resolve()}, name={project_name})")

    # Create subdirectories
    for subdir in ["session_history", "session_messages"]:
        d = workflow_dir / subdir
        d.mkdir(exist_ok=True)

    # Create progress.md with summary template
    progress = workflow_dir / "progress.md"
    if not progress.exists():
        project_name = name or project_dir.resolve().name
        progress.write_text(
            f"# Progress: {project_name}\n\n"
            "## Overall\n"
            "- Completed: 0 / 0 tasks (0%)\n"
            "- Sessions so far: 0\n"
            "- Current phase: Not started\n\n"
            "## Last Session\n"
            "- (no sessions yet)\n\n"
            "## Key Discoveries\n"
            "- (none yet)\n\n"
            "## Known Issues & TODOs\n"
            "- (none yet)\n\n"
            "## Next Up\n"
            "- (waiting for task list generation)\n",
            encoding="utf-8",
        )
        print(f"[OK] Created progress.md")

    print(f"""
========================================
Setup complete: {workflow_dir}
========================================

Next steps:
  1. Edit {workflow_dir / 'config.yaml'} (review model, permissions)
  2. Edit {workflow_dir / 'spec.md'} (describe what you want done)
     OR rename task_list_template.json to task_list.json and fill in tasks
  3. Run:  python tools/run_workflow.py {project_dir}
""")


def main():
    parser = argparse.ArgumentParser(
        description="Set up AgentNebula workflow in a project directory",
    )
    parser.add_argument(
        "project_dir", nargs="?", default=".",
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--name", type=str, default=None,
        help="Project name (default: directory name)",
    )
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"[ERROR] Not a directory: {project_dir}")
        sys.exit(1)

    setup(project_dir, args.name)


if __name__ == "__main__":
    main()

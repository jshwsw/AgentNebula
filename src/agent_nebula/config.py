"""Project configuration: auto-detection + manual override via config.yaml.

Key concept: workflow_dir vs cwd
- workflow_dir: where AgentNebula state lives (config.yaml, task_list.json, progress.md, etc.)
- cwd: where the Claude agent actually works (reads/writes project files)
These are independent. A workflow in ~/workflows/titus-docs/ can drive Claude
to work in c:/Work/ProjAI/Claude_Sango/.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


WORKFLOW_SUBDIR = ".agent-nebula"
CONFIG_FILE = "config.yaml"

# Markers used to auto-detect project type and tech stack.
_DETECT_RULES: list[tuple[str, list[str], str]] = [
    ("package.json", ["node"], ""),
    ("tsconfig.json", ["typescript"], ""),
    ("angular.json", ["angular"], "web-app"),
    ("next.config.js", ["next.js"], "web-app"),
    ("next.config.ts", ["next.js"], "web-app"),
    ("vite.config.ts", ["vite"], "web-app"),
    ("requirements.txt", ["python"], ""),
    ("pyproject.toml", ["python"], ""),
    ("setup.py", ["python"], ""),
    ("Cargo.toml", ["rust"], ""),
    ("go.mod", ["go"], ""),
    ("pom.xml", ["java", "maven"], ""),
    ("build.gradle", ["java", "gradle"], ""),
    ("CMakeLists.txt", ["cmake", "c++"], ""),
    ("Makefile", [], ""),
    ("Dockerfile", ["docker"], ""),
    (".uproject", ["unreal-engine", "c++"], "game"),
]


@dataclass
class WorkflowConfig:
    model_complex: str = "claude-opus-4-6"
    model_simple: str = "claude-sonnet-4-6"
    max_sessions: int = -1  # -1 = infinite
    session_delay_seconds: int = 3
    auto_commit: bool = True
    max_turns_per_session: int = 200
    permission_mode: str = "bypassPermissions"


@dataclass
class SecurityConfig:
    sandbox_to_project: bool = True
    allowed_tools: list[str] = field(default_factory=lambda: [
        "Read", "Write", "Edit", "Glob", "Grep", "Bash",
        "Task", "TodoWrite",
    ])


@dataclass
class VerificationConfig:
    strategy: str = "auto"  # auto | manual | script | none
    test_command: str = ""
    build_command: str = ""


@dataclass
class ProjectConfig:
    """Full project configuration.

    The `cwd` field is the key addition: it tells the Claude agent which
    directory to treat as its working directory. This allows the workflow
    state (task_list.json, progress.md, etc.) to live in a completely
    separate directory from the project files.
    """

    name: str = ""
    project_type: str = ""
    tech_stack: list[str] = field(default_factory=list)
    cwd: str = ""  # Claude agent working directory; empty = same as workflow_dir parent
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)

    def resolve_cwd(self, workflow_dir: Path) -> Path:
        """Return the resolved working directory for Claude sessions."""
        if self.cwd:
            return Path(self.cwd).resolve()
        return workflow_dir.parent.resolve()

    # --- persistence ---

    @staticmethod
    def config_path(workflow_dir: Path) -> Path:
        return workflow_dir / CONFIG_FILE

    def save(self, workflow_dir: Path) -> None:
        path = self.config_path(workflow_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "project": {
                "name": self.name,
                "type": self.project_type,
                "tech_stack": self.tech_stack,
                "cwd": self.cwd,
            },
            "workflow": {
                "model_complex": self.workflow.model_complex,
                "model_simple": self.workflow.model_simple,
                "max_sessions": self.workflow.max_sessions,
                "session_delay_seconds": self.workflow.session_delay_seconds,
                "auto_commit": self.workflow.auto_commit,
                "max_turns_per_session": self.workflow.max_turns_per_session,
                "permission_mode": self.workflow.permission_mode,
            },
            "security": {
                "sandbox_to_project": self.security.sandbox_to_project,
                "allowed_tools": self.security.allowed_tools,
            },
            "verification": {
                "strategy": self.verification.strategy,
                "test_command": self.verification.test_command,
                "build_command": self.verification.build_command,
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    @classmethod
    def load(cls, workflow_dir: Path) -> ProjectConfig:
        path = cls.config_path(workflow_dir)
        if not path.exists():
            raise FileNotFoundError(f"No config found at {path}. Run `agent-nebula init` first.")
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        proj = data.get("project", {})
        wf = data.get("workflow", {})
        sec = data.get("security", {})
        ver = data.get("verification", {})

        cfg = cls(
            name=proj.get("name", ""),
            project_type=proj.get("type", ""),
            tech_stack=proj.get("tech_stack", []),
            cwd=proj.get("cwd", ""),
        )
        for k, v in wf.items():
            if hasattr(cfg.workflow, k):
                setattr(cfg.workflow, k, v)
        for k, v in sec.items():
            if hasattr(cfg.security, k):
                setattr(cfg.security, k, v)
        for k, v in ver.items():
            if hasattr(cfg.verification, k):
                setattr(cfg.verification, k, v)
        return cfg


def detect_project(cwd: Path) -> ProjectConfig:
    """Auto-detect project type and tech stack from filesystem markers."""
    cfg = ProjectConfig(name=cwd.name, cwd=str(cwd.resolve()))
    seen_tech: set[str] = set()

    for marker, techs, ptype in _DETECT_RULES:
        if (cwd / marker).exists():
            for t in techs:
                seen_tech.add(t)
            if ptype and not cfg.project_type:
                cfg.project_type = ptype

    pkg_json = cwd / "package.json"
    if pkg_json.exists():
        try:
            import json
            with open(pkg_json, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "react" in all_deps:
                seen_tech.add("react")
                cfg.project_type = cfg.project_type or "web-app"
            if "vue" in all_deps:
                seen_tech.add("vue")
                cfg.project_type = cfg.project_type or "web-app"
            if "express" in all_deps or "fastify" in all_deps:
                seen_tech.add("node")
                cfg.project_type = cfg.project_type or "api"
        except Exception:
            pass

    cfg.tech_stack = sorted(seen_tech)
    cfg.project_type = cfg.project_type or "generic"
    return cfg


def resolve_workflow_dir(workflow_dir_arg: str | None, fallback_cwd: str = ".") -> Path:
    """Resolve the workflow directory from CLI args.

    Priority:
    1. Explicit -w/--workflow-dir argument
    2. AGENT_NEBULA_WORKFLOW_DIR environment variable
    3. <fallback_cwd>/.agent-nebula/
    """
    if workflow_dir_arg:
        p = Path(workflow_dir_arg).resolve()
        if (p / CONFIG_FILE).exists():
            return p
        if (p / WORKFLOW_SUBDIR).exists():
            return p / WORKFLOW_SUBDIR
        return p

    env_val = os.environ.get("AGENT_NEBULA_WORKFLOW_DIR")
    if env_val:
        return Path(env_val).resolve()

    return Path(fallback_cwd).resolve() / WORKFLOW_SUBDIR

"""Project configuration: auto-detection + manual override via config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


WORKFLOW_DIR = ".agent-workflow"
CONFIG_FILE = "config.yaml"

# Markers used to auto-detect project type and tech stack.
_DETECT_RULES: list[tuple[str, list[str], str]] = [
    # (marker file, tech_stack entries, project_type)
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

_SRC_GLOBS: dict[str, list[str]] = {
    "react": ["**/src/**/*.tsx", "**/src/**/*.jsx"],
    "vue": ["**/*.vue"],
    "python": ["**/*.py"],
    "c++": ["**/*.cpp", "**/*.h"],
}


@dataclass
class WorkflowConfig:
    model_complex: str = "claude-opus-4-20250514"
    model_simple: str = "claude-sonnet-4-20250514"
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
    """Full project configuration."""

    name: str = ""
    project_type: str = ""  # web-app, api, cli, library, game, docs, etc.
    tech_stack: list[str] = field(default_factory=list)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)

    # --- persistence ---

    @staticmethod
    def config_path(project_dir: Path) -> Path:
        return project_dir / WORKFLOW_DIR / CONFIG_FILE

    def save(self, project_dir: Path) -> None:
        path = self.config_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "project": {
                "name": self.name,
                "type": self.project_type,
                "tech_stack": self.tech_stack,
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
    def load(cls, project_dir: Path) -> ProjectConfig:
        path = cls.config_path(project_dir)
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


def detect_project(project_dir: Path) -> ProjectConfig:
    """Auto-detect project type and tech stack from filesystem markers."""
    cfg = ProjectConfig(name=project_dir.name)
    seen_tech: set[str] = set()

    for marker, techs, ptype in _DETECT_RULES:
        if (project_dir / marker).exists():
            for t in techs:
                seen_tech.add(t)
            if ptype and not cfg.project_type:
                cfg.project_type = ptype

    # Deeper scan: check for frameworks inside package.json
    pkg_json = project_dir / "package.json"
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

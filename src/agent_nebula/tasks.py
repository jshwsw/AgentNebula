"""Task list management: task_list.json CRUD operations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class Task:
    id: str
    category: str  # feature | bugfix | refactor | test | docs | analysis | generation
    priority: int  # lower = higher priority
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # task IDs
    passes: bool = False
    session_attempted: int | None = None
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        return cls(
            id=d["id"],
            category=d.get("category", "feature"),
            priority=d.get("priority", 99),
            description=d.get("description", ""),
            acceptance_criteria=d.get("acceptance_criteria", []),
            dependencies=d.get("dependencies", []),
            passes=d.get("passes", False),
            session_attempted=d.get("session_attempted"),
            notes=d.get("notes", ""),
            metadata=d.get("metadata", {}),
        )


class TaskList:
    """Manages task_list.json — the single source of truth for work items.

    Takes `workflow_dir` directly — the directory where task_list.json lives.
    """

    def __init__(self, workflow_dir: Path):
        self.path = workflow_dir / "task_list.json"
        self._tasks: list[Task] = []
        if self.path.exists():
            self._load()

    def _load(self) -> None:
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._tasks = [Task.from_dict(t) for t in data.get("tasks", [])]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"tasks": [t.to_dict() for t in self._tasks]}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @property
    def tasks(self) -> list[Task]:
        return list(self._tasks)

    def add(self, task: Task) -> None:
        self._tasks.append(task)

    def add_many(self, tasks: list[Task]) -> None:
        self._tasks.extend(tasks)

    def get(self, task_id: str) -> Task | None:
        for t in self._tasks:
            if t.id == task_id:
                return t
        return None

    def mark_done(self, task_id: str, session_num: int | None = None, notes: str = "") -> bool:
        task = self.get(task_id)
        if task is None:
            return False
        task.passes = True
        if session_num is not None:
            task.session_attempted = session_num
        if notes:
            task.notes = notes
        return True

    def pending(self) -> list[Task]:
        """Return tasks that are not done, sorted by priority then ID."""
        done_ids = {t.id for t in self._tasks if t.passes}
        result = []
        for t in self._tasks:
            if t.passes:
                continue
            if any(dep not in done_ids for dep in t.dependencies):
                continue
            result.append(t)
        result.sort(key=lambda t: (t.priority, t.id))
        return result

    def completed(self) -> list[Task]:
        return [t for t in self._tasks if t.passes]

    def stats(self) -> tuple[int, int]:
        """Return (completed_count, total_count)."""
        return len(self.completed()), len(self._tasks)

    def exists(self) -> bool:
        return self.path.exists() and len(self._tasks) > 0

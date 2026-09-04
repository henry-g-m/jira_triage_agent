from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Match:
    project: str
    issue_key: str
    issue_title: str
    issue_summary: str
    body: str = ""
    comments: str = ""
    similarity: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Recommendation:
    project: str
    confidence: float
    rationale: str
    matches: list[Match]
    guidance: list[str]

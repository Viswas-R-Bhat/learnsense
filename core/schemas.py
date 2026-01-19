from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Literal

Mode = Literal["DIAGNOSE", "SOCRATIC", "RUBRIC", "EXAM"]

@dataclass
class Misconception:
    concept: str
    why_wrong: str
    hints: List[str]
    diagnostic_question: str
    severity: str
    teaching: Dict[str, str]
    final_answer: str
    memory: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["memory"] is None:
            d["memory"] = []
        hints = d.get("hints") or []
        while len(hints) < 3:
            hints.append("Start from the definition and test with a simple example.")
        d["hints"] = hints[:3]
        return d

@dataclass
class Artifacts:
    steps: Optional[List[str]] = None
    wrong_step_index: Optional[int] = None
    fix: Optional[str] = None

    rubric: Optional[List[Dict[str, Any]]] = None
    solution_steps: Optional[List[str]] = None
    minimal_fix: Optional[str] = None

    concept_dashboard: Optional[Dict[str, Any]] = None

    # Exam artifacts
    exam_questions: Optional[List[Dict[str, Any]]] = None
    exam_results: Optional[List[Dict[str, Any]]] = None
    exam_report: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class TutorResponse:
    mode: Mode
    is_correct: bool
    confidence: float
    attempts_used: int
    hint_level: int
    messages: List[Dict[str, str]]
    misconceptions: List[Misconception]
    artifacts: Artifacts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "is_correct": bool(self.is_correct),
            "confidence": float(self.confidence or 0.0),
            "attempts_used": int(self.attempts_used or 0),
            "hint_level": int(self.hint_level or 1),
            "messages": self.messages or [],
            "misconceptions": [m.to_dict() for m in (self.misconceptions or [])],
            "artifacts": self.artifacts.to_dict() if self.artifacts else {},
        }

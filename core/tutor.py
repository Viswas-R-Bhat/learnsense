from typing import Optional, List, Dict, Any
from .schemas import TutorResponse, Misconception, Artifacts
from .utils import is_academic_only, clamp
from .diagnose import diagnose
from .socratic import socratic_turn
from .rubric import generate_rubric

from db import (
    get_user_history,
    record_attempt,
    update_user_concepts,
    get_concept_dashboard,
)

MAX_ATTEMPTS_BEFORE_RUBRIC = 4

def _memory_block(user_id: str) -> str:
    hist = get_user_history(user_id) or []
    lines = []
    for h in hist[:6]:
        try:
            lines.append(f"- {h[0]}: mastery {h[1]}% ({h[2]}) on {h[3]}")
        except Exception:
            continue
    return "\n".join(lines) if lines else "No prior history."

def _normalize_misconceptions(items: Any, is_correct: bool) -> List[Misconception]:
    if not isinstance(items, list):
        items = []
    if is_correct and not items:
        items = [{
            "concept": "No misconception",
            "why_wrong": "✅ Your answer looks correct.",
            "hints": ["Try a harder variant.", "Explain your reasoning in 1–2 sentences.", "Give a counterexample and why it fails."],
            "diagnostic_question": "Can you justify it in one sentence?",
            "severity": "low",
            "teaching": {"explanation": "Nice — that matches the expected concept.", "analogy": "", "follow_up_question": "Want a follow-up?"},
            "final_answer": "You're correct. Want to try a harder variant?"
        }]

    out: List[Misconception] = []
    for m in items[:3]:
        t = m.get("teaching") if isinstance(m, dict) else {}
        if not isinstance(t, dict):
            t = {}
        out.append(Misconception(
            concept=(m.get("concept") if isinstance(m, dict) else None) or ("No misconception" if is_correct else "Conceptual misunderstanding"),
            why_wrong=(m.get("why_wrong") if isinstance(m, dict) else None) or ("Your answer is correct." if is_correct else "There is a misunderstanding."),
            hints=((m.get("hints") if isinstance(m, dict) else None) or [])[:3],
            diagnostic_question=(m.get("diagnostic_question") if isinstance(m, dict) else None) or "Can you explain the key definition in one sentence?",
            severity=(m.get("severity") if isinstance(m, dict) else None) or ("low" if is_correct else "medium"),
            teaching={
                "explanation": t.get("explanation") or ("✅ Looks correct." if is_correct else "Let’s fix this step by step."),
                "analogy": t.get("analogy") or "",
                "follow_up_question": t.get("follow_up_question") or "Try again in your own words.",
            },
            final_answer=(m.get("final_answer") if isinstance(m, dict) else None) or "",
            memory=[]
        ))
    return out

def handle_turn(
    user_id: str,
    question: str,
    student_input: str,
    mode: str,
    topic: str,
    hint_level: int = 1,
    give_up: bool = False,
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
) -> Dict[str, Any]:

    # Guardrails
    if not is_academic_only(question) or not is_academic_only(student_input):
        tr = TutorResponse(
            mode="SOCRATIC",
            is_correct=False,
            confidence=0.0,
            attempts_used=0,
            hint_level=1,
            messages=[{"role": "assistant", "text": "I can help only with academic/learning questions."}],
            misconceptions=[],
            artifacts=Artifacts(concept_dashboard=get_concept_dashboard(user_id))
        )
        return tr.to_dict()

    if not question or len(question.strip()) < 5:
        tr = TutorResponse(
            mode="SOCRATIC",
            is_correct=False,
            confidence=0.0,
            attempts_used=0,
            hint_level=1,
            messages=[{"role": "assistant", "text": "Please provide the question/problem statement in the left panel."}],
            misconceptions=[],
            artifacts=Artifacts(concept_dashboard=get_concept_dashboard(user_id))
        )
        return tr.to_dict()

    attempts_used = record_attempt(
        user_id=user_id,
        question=question,
        student_input=student_input,
        has_image=bool(image_bytes)
    )

    mem = _memory_block(user_id)

    # Give-up / auto-rubric
    if give_up or attempts_used >= MAX_ATTEMPTS_BEFORE_RUBRIC:
        rb = generate_rubric(question, student_input, topic, mode)
        if rb.get("error"):
            tr = TutorResponse(
                mode="RUBRIC",
                is_correct=False,
                confidence=0.0,
                attempts_used=attempts_used,
                hint_level=4,
                messages=[{"role": "assistant", "text": rb.get("error_message", "Unable to generate the answer right now.")}],
                misconceptions=[],
                artifacts=Artifacts(concept_dashboard=get_concept_dashboard(user_id))
            )
            return tr.to_dict()

        update_user_concepts(user_id, [{"concept": "Answer Reveal"}], is_correct=False)

        tr = TutorResponse(
            mode="RUBRIC",
            is_correct=False,
            confidence=0.8,
            attempts_used=attempts_used,
            hint_level=4,
            messages=[{"role": "assistant", "text": rb.get("final_answer", "") or "Here’s the correct answer and rubric."}],
            misconceptions=[],
            artifacts=Artifacts(
                solution_steps=rb.get("solution_steps") or [],
                rubric=rb.get("rubric") or [],
                minimal_fix=rb.get("minimal_fix") or "",
                concept_dashboard=get_concept_dashboard(user_id)
            )
        )
        return tr.to_dict()

    # Image present => Mistake Microscope (DIAGNOSE)
    if image_bytes:
        dg = diagnose(question, student_input, mem, mode, topic, image_bytes=image_bytes, image_mime=image_mime)
        if dg.get("error"):
            tr = TutorResponse(
                mode="DIAGNOSE",
                is_correct=False,
                confidence=0.0,
                attempts_used=attempts_used,
                hint_level=hint_level,
                messages=[{"role": "assistant", "text": dg.get("error_message", "Unable to analyze right now.")}],
                misconceptions=[],
                artifacts=Artifacts(concept_dashboard=get_concept_dashboard(user_id))
            )
            return tr.to_dict()

        is_correct = bool(dg.get("is_correct", False))
        misconceptions = _normalize_misconceptions(dg.get("misconceptions", []), is_correct=is_correct)

        update_user_concepts(user_id, [m.to_dict() for m in misconceptions], is_correct=is_correct)

        fix = (dg.get("fix") or "").strip()
        ask = misconceptions[0].diagnostic_question if misconceptions else "What definition are you using?"
        text = (fix + "\n\n" if fix else "") + ask

        tr = TutorResponse(
            mode="DIAGNOSE",
            is_correct=is_correct,
            confidence=clamp(dg.get("confidence", 0.5), 0.0, 1.0),
            attempts_used=attempts_used,
            hint_level=hint_level,
            messages=[{"role": "assistant", "text": text}],
            misconceptions=misconceptions,
            artifacts=Artifacts(
                steps=dg.get("steps") or [],
                wrong_step_index=int(dg.get("wrong_step_index", -1)),
                fix=fix,
                concept_dashboard=get_concept_dashboard(user_id)
            )
        )
        return tr.to_dict()

    # Text-only => SOCRATIC
    sc = socratic_turn(question, student_input, mem, hint_level, mode, topic)
    if sc.get("error"):
        tr = TutorResponse(
            mode="SOCRATIC",
            is_correct=False,
            confidence=0.0,
            attempts_used=attempts_used,
            hint_level=hint_level,
            messages=[{"role": "assistant", "text": sc.get("error_message", "Unable to respond right now.")}],
            misconceptions=[],
            artifacts=Artifacts(concept_dashboard=get_concept_dashboard(user_id))
        )
        return tr.to_dict()

    is_correct = bool(sc.get("is_correct", False))
    misconceptions = _normalize_misconceptions(sc.get("misconceptions", []), is_correct=is_correct)
    update_user_concepts(user_id, [m.to_dict() for m in misconceptions], is_correct=is_correct)

    msg = ""
    if misconceptions:
        idx = max(0, min(2, hint_level - 1))
        hint = misconceptions[0].hints[idx] if misconceptions[0].hints else ""
        if hint_level < 4 and hint:
            msg += f"### Hint\n{hint}\n\n"

    next_q = (sc.get("next_question") or (misconceptions[0].diagnostic_question if misconceptions else "")).strip()
    if hint_level < 4:
        msg += f"### Try this\n{next_q or 'Explain your reasoning briefly.'}"
    else:
        final = misconceptions[0].final_answer if misconceptions else ""
        msg = final or "Here’s the correct solution idea."

    tr = TutorResponse(
        mode="SOCRATIC",
        is_correct=is_correct,
        confidence=clamp(sc.get("confidence", 0.5), 0.0, 1.0),
        attempts_used=attempts_used,
        hint_level=hint_level,
        messages=[{"role": "assistant", "text": msg}],
        misconceptions=misconceptions,
        artifacts=Artifacts(concept_dashboard=get_concept_dashboard(user_id))
    )
    return tr.to_dict()

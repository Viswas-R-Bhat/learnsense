from typing import Optional, List, Dict, Any
from google.genai.errors import ClientError

from core.tutor import handle_turn
from core.utils import is_academic_only, safe_json_load
from core.gemini_client import get_client, MODEL_FAST
from core.exam import generate_exam_questions, build_exam_report


def tutor_turn(
    user_id: str,
    question: str,
    student_input: str,
    mode: str,
    topic: str,
    hint_level: int = 1,
    give_up: bool = False,
    image_bytes: Optional[bytes] = None,
    image_mime: Optional[str] = None,
) -> dict:
    return handle_turn(
        user_id=user_id,
        question=question,
        student_input=student_input,
        mode=mode,
        topic=topic,
        hint_level=hint_level,
        give_up=give_up,
        image_bytes=image_bytes,
        image_mime=image_mime,
    )


def generate_questions_from_notes(notes_text: str, topic: str = "General", mode: str = "Exam") -> dict:
    client = get_client()
    if client is None:
        return {"questions": []}

    if not notes_text or len(notes_text.strip()) < 30:
        return {"questions": []}

    if not is_academic_only(notes_text):
        return {"questions": []}

    prompt = f"""
You are a study assistant. Create practice questions ONLY for academic learning.

Topic: {topic}
Preferred style: {mode}

From the notes below, generate 10 questions as JSON.
Include a mix:
- 4 conceptual
- 4 application/problem-solving
- 2 tricky misconception-trap questions

Return ONLY JSON:
{{
  "questions": [
    {{
      "q": "",
      "topic": "{topic}",
      "difficulty": "easy|medium|hard",
      "type": "concept|application|trap"
    }}
  ]
}}

Notes:
\"\"\"{notes_text}\"\"\"
""".strip()

    try:
        resp = client.models.generate_content(model=MODEL_FAST, contents=prompt)
        parsed = safe_json_load(getattr(resp, "text", "") or "")
        if not parsed or "questions" not in parsed:
            return {"questions": []}
        if not isinstance(parsed.get("questions"), list):
            return {"questions": []}
        return parsed
    except ClientError:
        return {"questions": []}
    except Exception:
        return {"questions": []}


def start_exam(topic: str, style: str, n: int = 5) -> dict:
    return generate_exam_questions(topic=topic, style=style, n=n)


def finish_exam(topic: str, qa_pairs: List[Dict[str, str]]) -> dict:
    return build_exam_report(topic=topic, qa_pairs=qa_pairs)

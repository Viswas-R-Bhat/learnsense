from google.genai.errors import ClientError

from .gemini_client import get_client, MODEL_FAST, MODEL_DEEP
from .utils import safe_json_load, clamp
from .prompts import prompt_socratic

def socratic_turn(
    question: str,
    student_text: str,
    memory_block: str,
    hint_level: int,
    mode: str,
    topic: str,
) -> dict:
    client = get_client()
    if client is None:
        return {"error": True, "error_message": "Model unavailable."}

    prompt = prompt_socratic(question, student_text, memory_block, hint_level, mode, topic)
    model = MODEL_FAST if hint_level < 4 else MODEL_DEEP

    try:
        resp = client.models.generate_content(model=model, contents=prompt)
        parsed = safe_json_load(getattr(resp, "text", "") or "")
        if not parsed:
            return {"error": True, "error_message": "Invalid model JSON."}

        parsed["confidence"] = clamp(parsed.get("confidence", 0.5), 0.0, 1.0)
        parsed.setdefault("next_question", "Can you explain your reasoning in one sentence?")
        parsed.setdefault("misconceptions", [])
        return parsed

    except ClientError:
        return {"error": True, "error_message": "Model busy, try again."}
    except Exception:
        return {"error": True, "error_message": "Socratic step failed."}

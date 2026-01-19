from google.genai.errors import ClientError

from .gemini_client import get_client, MODEL_DEEP
from .utils import safe_json_load
from .prompts import prompt_rubric

def generate_rubric(question: str, student_attempt: str, topic: str, mode: str) -> dict:
    client = get_client()
    if client is None:
        return {"error": True, "error_message": "Model unavailable."}

    prompt = prompt_rubric(question, student_attempt, topic, mode)

    try:
        resp = client.models.generate_content(model=MODEL_DEEP, contents=prompt)
        raw_text = getattr(resp, "text", "") or ""
        parsed = safe_json_load(raw_text)

        # ---------- HARD FALLBACK FOR GIVE-UP ----------
        if not parsed:
            # Last-resort fallback: wrap raw text into a valid rubric response
            return {
                "solution_steps": [
                    s.strip() for s in raw_text.split("\n") if s.strip()
                ][:6],  # keep it short
                "rubric": [
                    {
                        "step": "Overall understanding",
                        "marks": 10,
                        "expected": "Correct explanation of the concept",
                        "common_errors": "Confusing definitions or order of operations",
                        "student_error": "Gave up before articulating the concept",
                    }
                ],
                "minimal_fix": "Focus on the core definition first, then contrast it with the alternative.",
                "final_answer": raw_text.strip() or "Here is the correct explanation of the concept.",
            }

        parsed.setdefault("solution_steps", [])
        parsed.setdefault("rubric", [])
        parsed.setdefault("minimal_fix", "")
        parsed.setdefault("final_answer", "")
        return parsed

    except ClientError:
        return {"error": True, "error_message": "Model busy, try again."}
    except Exception:
        return {"error": True, "error_message": "Rubric generation failed."}

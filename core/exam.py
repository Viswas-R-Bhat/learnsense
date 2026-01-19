from typing import List, Dict, Any
from google.genai.errors import ClientError

from .gemini_client import get_client, MODEL_FAST
from .utils import safe_json_load
from .prompts import prompt_generate_exam, prompt_exam_report

def generate_exam_questions(topic: str, style: str, n: int = 5) -> Dict[str, Any]:
    client = get_client()
    if client is None:
        return {"error": True, "error_message": "Model unavailable.", "questions": []}

    prompt = prompt_generate_exam(topic=topic, style=style, n=n)
    try:
        resp = client.models.generate_content(model=MODEL_FAST, contents=prompt)
        parsed = safe_json_load(getattr(resp, "text", "") or "")
        if not parsed or "questions" not in parsed or not isinstance(parsed.get("questions"), list):
            return {"error": True, "error_message": "Invalid exam JSON.", "questions": []}
        return {"questions": parsed["questions"][:n]}
    except ClientError:
        return {"error": True, "error_message": "Model busy, try again.", "questions": []}
    except Exception:
        return {"error": True, "error_message": "Exam generation failed.", "questions": []}

def build_exam_report(topic: str, qa_pairs: List[Dict[str, str]]) -> Dict[str, Any]:
    client = get_client()
    if client is None:
        return {"error": True, "error_message": "Model unavailable."}

    qa_text = "\n\n".join([f"Q: {x.get('q','')}\nA: {x.get('a','')}" for x in qa_pairs])
    prompt = prompt_exam_report(topic, qa_text)

    try:
        resp = client.models.generate_content(model=MODEL_FAST, contents=prompt)
        parsed = safe_json_load(getattr(resp, "text", "") or "")
        if not parsed:
            return {"error": True, "error_message": "Invalid report JSON."}
        return parsed
    except ClientError:
        return {"error": True, "error_message": "Model busy, try again."}
    except Exception:
        return {"error": True, "error_message": "Exam report failed."}

from typing import Dict, Any, List
from db import update_user_concepts, get_concept_dashboard, add_history

def update_memory(user_id: str, misconceptions: List[Dict[str, Any]], is_correct: bool):
    update_user_concepts(user_id, misconceptions, is_correct)

    # Optional: also write to history table for continuity with your older UI logic
    # We keep it lightweight.
    if misconceptions:
        top = misconceptions[0]
        concept = (top.get("concept") or "General Understanding")
        mastery = 70 if is_correct else 40
        note = "Correct response" if is_correct else "Needs improvement"
        add_history(user_id, concept, mastery, note)

def dashboard(user_id: str) -> Dict[str, Any]:
    return get_concept_dashboard(user_id)

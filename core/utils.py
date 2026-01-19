import json
from typing import Optional, Any, Dict

def extract_json(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if len(lines) > 2:
            t = "\n".join(lines[1:-1])
    t = t.replace("```json", "").replace("```", "").strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        return None
    return t[start:end + 1]

def safe_json_load(text: str) -> Optional[Dict[str, Any]]:
    try:
        j = extract_json(text)
        if not j:
            return None
        return json.loads(j)
    except Exception:
        return None

def is_academic_only(text: str) -> bool:
    t = (text or "").lower()
    banned = [
        "game", "minecraft", "roblox", "valorant", "fortnite",
        "roleplay", "story", "fanfic", "meme", "joke",
        "dating", "pickup", "flirt",
        "hack", "cheat code", "aimbot",
    ]
    return not any(b in t for b in banned)

def clamp(x: float, lo: float, hi: float) -> float:
    try:
        v = float(x)
    except Exception:
        v = lo
    return max(lo, min(hi, v))

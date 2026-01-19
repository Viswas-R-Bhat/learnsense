import streamlit as st
import uuid
from backend import tutor_turn, generate_questions_from_notes

st.set_page_config(page_title="LearnSense", page_icon="🧠", layout="wide")

# ---------- CSS (ChatGPT-ish) ----------
st.markdown(
    """
    <style>
      /* Constrain Streamlit main content width safely */
      section.main > div { max-width: 900px; margin: 0 auto; }

      /* Sidebar like ChatGPT left rail */
      [data-testid="stSidebar"] { min-width: 320px; max-width: 320px; }
      [data-testid="stSidebar"] .stMarkdown { font-size: 0.95rem; }

      /* Tighten chat spacing */
      [data-testid="stChatMessage"] { padding-top: 6px; padding-bottom: 6px; }

      /* Input rounded */
      [data-testid="stChatInput"] textarea { border-radius: 14px !important; }

      /* Steps list */
      .ls-step { padding: 8px 10px; border-radius: 10px; border: 1px solid rgba(128,128,128,0.18); margin: 6px 0; }
      .ls-step-wrong { border: 1px solid rgba(255,0,0,0.35); background: rgba(255,0,0,0.04); }

      /* Dataframe tweak */
      [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Session State ----------
if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending" not in st.session_state:
    st.session_state.pending = False
if "pending_input" not in st.session_state:
    st.session_state.pending_input = ""
if "pending_placeholder_index" not in st.session_state:
    st.session_state.pending_placeholder_index = None
if "pending_request_id" not in st.session_state:
    st.session_state.pending_request_id = None

if "cancel_requested" not in st.session_state:
    st.session_state.cancel_requested = False
if "cancel_request_id" not in st.session_state:
    st.session_state.cancel_request_id = None

# Tutor settings (left rail)
if "learning_mode" not in st.session_state:
    st.session_state.learning_mode = "Exam"  # ELI5 | Exam | Interview
if "current_topic" not in st.session_state:
    st.session_state.current_topic = "General"
if "current_question" not in st.session_state:
    st.session_state.current_question = ""
if "hint_level" not in st.session_state:
    st.session_state.hint_level = 1  # 1-4

# Attachment state (ChatGPT-like "+")
if "uploaded_image_bytes" not in st.session_state:
    st.session_state.uploaded_image_bytes = None
if "uploaded_image_mime" not in st.session_state:
    st.session_state.uploaded_image_mime = None

# Notes -> question bank
if "question_bank" not in st.session_state:
    st.session_state.question_bank = []

# Last response + last student answer (for Give up)
if "last_tutor_response" not in st.session_state:
    st.session_state.last_tutor_response = None
if "last_student_answer" not in st.session_state:
    st.session_state.last_student_answer = ""

# Internal: force give up on next model call
if "_force_give_up" not in st.session_state:
    st.session_state._force_give_up = False

# Debounce
if "last_user_text" not in st.session_state:
    st.session_state.last_user_text = None


# ---------- Helpers ----------
def add_msg(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def render_msg(role: str, content: str):
    with st.chat_message(role):
        st.markdown(content)


def is_academic_query(text: str) -> bool:
    t = (text or "").lower()
    banned = [
        "game", "minecraft", "roblox", "valorant", "fortnite",
        "roleplay", "story", "fanfic", "meme", "joke",
        "dating", "pickup", "flirt", "bgmi", "efootball", "gta",
        "hack", "cheat code", "aimbot",
    ]
    return not any(b in t for b in banned)


def reset_all():
    st.session_state.messages = []
    st.session_state.pending = False
    st.session_state.pending_input = ""
    st.session_state.pending_placeholder_index = None
    st.session_state.pending_request_id = None
    st.session_state.cancel_requested = False
    st.session_state.cancel_request_id = None
    st.session_state.last_user_text = None
    st.session_state.uploaded_image_bytes = None
    st.session_state.uploaded_image_mime = None
    st.session_state.last_tutor_response = None
    st.session_state.last_student_answer = ""
    st.session_state.hint_level = 1
    st.session_state._force_give_up = False
    st.rerun()


def _first_text_message(tr: dict) -> str:
    msgs = (tr or {}).get("messages") or []
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return (msgs[0].get("text") or "").strip()
    return ""


def _render_artifacts(tr: dict):
    if not isinstance(tr, dict):
        return

    mode = tr.get("mode")
    artifacts = tr.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    # ----- DIAGNOSE: steps + wrong-step highlight -----
    steps = artifacts.get("steps") or []
    wrong_idx = artifacts.get("wrong_step_index", None)

    if mode == "DIAGNOSE" and isinstance(steps, list) and steps:
        st.markdown("##### 🧪 Mistake Microscope")
        for i, s in enumerate(steps):
            cls = "ls-step ls-step-wrong" if (isinstance(wrong_idx, int) and wrong_idx == i) else "ls-step"
            st.markdown(f'<div class="{cls}"><b>Step {i+1}.</b> {s}</div>', unsafe_allow_html=True)

    # ----- RUBRIC: solution + minimal fix + rubric table -----
    if mode == "RUBRIC":
        sol = artifacts.get("solution_steps") or []
        minimal_fix = (artifacts.get("minimal_fix") or "").strip()
        rubric = artifacts.get("rubric") or []

        st.markdown("##### ✅ Full Solution")
        if isinstance(sol, list) and sol:
            for i, s in enumerate(sol):
                st.markdown(f"- **Step {i+1}:** {s}")
        else:
            st.markdown("- (No steps returned)")

        if minimal_fix:
            st.markdown("##### 🔧 Minimal Fix to Your Attempt")
            st.info(minimal_fix)

        if isinstance(rubric, list) and rubric:
            st.markdown("##### 🧾 Grading Rubric")
            st.dataframe(rubric, use_container_width=True)

    # ----- Concept dashboard -----
    dash = artifacts.get("concept_dashboard")
    if isinstance(dash, dict):
        weakest = dash.get("weakest") or []
        frequent = dash.get("frequent") or []
        with st.expander("📌 Your learning dashboard", expanded=False):
            if weakest:
                st.markdown("**Weakest concepts (improve next):**")
                for w in weakest[:3]:
                    concept = w.get("concept", "")
                    mastery = int(float(w.get("mastery_est", 0) or 0))
                    st.markdown(f"- {concept} — mastery ~{mastery}%")
            if frequent:
                st.markdown("**Most frequent misconceptions:**")
                for f in frequent[:3]:
                    concept = f.get("concept", "")
                    cnt = int(f.get("misconception_count", 0) or 0)
                    st.markdown(f"- {concept} — {cnt} times")


def _start_pending(user_visible_user_msg: str, pending_student_input: str, force_give_up: bool):
    add_msg("user", user_visible_user_msg)
    add_msg("assistant", "⏳ Analyzing…")
    st.session_state.pending_placeholder_index = len(st.session_state.messages) - 1
    st.session_state.pending_input = pending_student_input
    st.session_state.pending = True
    st.session_state.pending_request_id = str(uuid.uuid4())
    st.session_state.cancel_requested = False
    st.session_state.cancel_request_id = None
    st.session_state._force_give_up = force_give_up
    st.rerun()


# ==========================
# LEFT RAIL (ChatGPT-like)
# ==========================
with st.sidebar:
    st.markdown("## LearnSense")
    st.caption("Understand your mistakes, not just your marks")

    st.session_state.learning_mode = st.selectbox(
        "Mode",
        ["ELI5", "Exam", "Interview"],
        index=["ELI5", "Exam", "Interview"].index(st.session_state.learning_mode),
        help="Like ChatGPT model picker — changes tutoring style.",
    )

    st.session_state.current_topic = st.selectbox(
        "Topic",
        ["General", "DSA", "Math", "OS", "DBMS", "CN", "AI/ML", "Physics", "Chemistry", "Biology", "Economics", "Other"],
        index=["General", "DSA", "Math", "OS", "DBMS", "CN", "AI/ML", "Physics", "Chemistry", "Biology", "Economics", "Other"].index(st.session_state.current_topic),
    )

    st.session_state.current_question = st.text_area(
        "Question (required)",
        value=st.session_state.current_question,
        height=80,
        placeholder="E.g., Differentiate AVL and BST.",
    )

    st.session_state.hint_level = st.select_slider(
        "Hint level",
        options=[1, 2, 3, 4],
        value=st.session_state.hint_level,
        help="1 = subtle hint, 3 = explicit hint, 4 = full answer (or click Give up).",
    )

    st.markdown("---")

    with st.expander("📄 Generate practice questions from notes"):
        notes_text = st.text_area(
            "Paste notes",
            height=160,
            placeholder="Paste your class notes/key points here..."
        )

        gen = st.button("Generate", use_container_width=True)

        if gen and notes_text.strip():
            qb = generate_questions_from_notes(
                notes_text=notes_text,
                topic=st.session_state.current_topic,
                mode=st.session_state.learning_mode
            )

            if isinstance(qb, dict) and qb.get("questions"):
                st.session_state.question_bank = qb["questions"]
            elif isinstance(qb, list):
                st.session_state.question_bank = qb
            else:
                st.session_state.question_bank = []

            if st.session_state.question_bank:
                st.success(f"Generated {len(st.session_state.question_bank)} questions.")
            else:
                st.warning("Couldn’t generate questions. Try shorter notes or clearer points.")

        if st.session_state.question_bank:
            choices = [
                f"{i+1}. ({q.get('difficulty','?')}, {q.get('type','?')}) {q.get('q','')[:90]}"
                for i, q in enumerate(st.session_state.question_bank)
            ]
            idx = st.selectbox(
                "Pick a question",
                range(len(choices)),
                format_func=lambda i: choices[i]
            )

            if st.button("Use selected question", use_container_width=True):
                selected = st.session_state.question_bank[idx]
                st.session_state.current_question = selected.get("q", "")
                st.session_state.current_topic = selected.get("topic", st.session_state.current_topic)
                st.session_state.uploaded_image_bytes = None
                st.session_state.uploaded_image_mime = None
                st.session_state.last_tutor_response = None
                st.session_state.last_student_answer = ""
                st.rerun()

    st.markdown("---")
    if st.button("🔄 Reset chat", use_container_width=True):
        reset_all()

    # Give up control (only when you have a last response, and it's not correct, and not generating)
    if st.session_state.last_tutor_response and not st.session_state.pending:
        tr = st.session_state.last_tutor_response
        is_correct = bool(tr.get("is_correct", False))
        attempts_used = int(tr.get("attempts_used", 0) or 0)

        st.markdown("---")
        st.caption(f"Attempts so far: {attempts_used}")

        if not is_correct:
            if st.button("🏳️ Give up (show answer + rubric)", use_container_width=True):
                # Use the last student answer as the attempt context for rubric generation
                attempt_text = (st.session_state.last_student_answer or "").strip()
                if not attempt_text:
                    attempt_text = "I don't know."

                _start_pending(
                    user_visible_user_msg="I give up.",
                    pending_student_input=attempt_text,
                    force_give_up=True
                )

# ==========================
# MAIN CHAT
# ==========================
if len(st.session_state.messages) == 0:
    add_msg("assistant", "Hi! Type an answer below and I’ll analyze it for misconceptions.")

for msg in st.session_state.messages:
    render_msg(msg["role"], msg["content"])

# Stop generating
if st.session_state.pending:
    if st.button("⏹ Stop generating"):
        st.session_state.cancel_requested = True
        st.session_state.cancel_request_id = st.session_state.pending_request_id
        idx = st.session_state.pending_placeholder_index
        if idx is not None and 0 <= idx < len(st.session_state.messages):
            st.session_state.messages[idx]["content"] = "⏹ Stopped."
        st.session_state.pending = False
        st.session_state.pending_input = ""
        st.session_state.pending_placeholder_index = None
        st.session_state.pending_request_id = None
        st.session_state._force_give_up = False
        st.rerun()

# Resolve pending (single call to tutor_turn)
if st.session_state.pending:
    if st.session_state.cancel_requested and st.session_state.cancel_request_id == st.session_state.pending_request_id:
        st.session_state.pending = False
        st.session_state.pending_input = ""
        st.session_state.pending_placeholder_index = None
        st.session_state.pending_request_id = None
        st.session_state.cancel_requested = False
        st.session_state.cancel_request_id = None
        st.session_state._force_give_up = False
        st.rerun()

    request_id = st.session_state.pending_request_id

    with st.spinner("Analyzing with Gemini…"):
        assistant_text = "I couldn’t analyze that yet. Try again."
        tr = None
        try:
            tr = tutor_turn(
                user_id=st.session_state.user_id,
                question=st.session_state.current_question,
                student_input=st.session_state.pending_input,
                mode=st.session_state.learning_mode,
                topic=st.session_state.current_topic,
                hint_level=int(st.session_state.hint_level),
                give_up=bool(st.session_state._force_give_up),
                image_bytes=st.session_state.uploaded_image_bytes,
                image_mime=st.session_state.uploaded_image_mime,
            )

            if isinstance(tr, dict):
                st.session_state.last_tutor_response = tr

            assistant_text = _first_text_message(tr) or "Done."

        except Exception:
            assistant_text = "I couldn’t reach the model right now (it may be overloaded). Please try again in a moment."
            st.session_state.last_tutor_response = None

        idx = st.session_state.pending_placeholder_index
        canceled = (st.session_state.cancel_requested and st.session_state.cancel_request_id == request_id)
        if not canceled and idx is not None and 0 <= idx < len(st.session_state.messages):
            st.session_state.messages[idx]["content"] = assistant_text

        # Clear attachment after send (ChatGPT-like)
        st.session_state.uploaded_image_bytes = None
        st.session_state.uploaded_image_mime = None

        # cleanup
        st.session_state.pending = False
        st.session_state.pending_input = ""
        st.session_state.pending_placeholder_index = None
        st.session_state.pending_request_id = None
        st.session_state._force_give_up = False
        if st.session_state.cancel_request_id == request_id:
            st.session_state.cancel_requested = False
            st.session_state.cancel_request_id = None

    st.rerun()

# Render artifacts for the most recent model turn (at bottom)
if st.session_state.last_tutor_response and not st.session_state.pending:
    with st.container():
        _render_artifacts(st.session_state.last_tutor_response)


# ==========================
# INPUT BAR + ATTACHMENT ("+")
# ==========================
attach_col, rest_col = st.columns([1, 12])

with attach_col:
    # Streamlit popover behaves like a ChatGPT "+" menu
    try:
        with st.popover("➕", help="Attach an image (handwritten answer, diagram, notes)"):
            up = st.file_uploader(
                "Attach image",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=False,
                label_visibility="collapsed",
            )
            if up is not None:
                st.session_state.uploaded_image_bytes = up.read()
                st.session_state.uploaded_image_mime = up.type
                st.success("Attached. Now send your answer.")
    except Exception:
        with st.expander("➕ Attach image"):
            up = st.file_uploader(
                "Attach image",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=False,
            )
            if up is not None:
                st.session_state.uploaded_image_bytes = up.read()
                st.session_state.uploaded_image_mime = up.type
                st.success("Attached. Now send your answer.")

with rest_col:
    if st.session_state.uploaded_image_bytes:
        st.caption("📎 Image attached")

placeholder = "Type your answer…"
user_text = st.chat_input(placeholder, disabled=st.session_state.pending)

# Debounce identical immediate resubmits
if user_text:
    if user_text == st.session_state.last_user_text:
        st.stop()
    st.session_state.last_user_text = user_text

if user_text and not st.session_state.pending:
    add_msg("user", user_text)

    # Save last student answer for rubric context
    st.session_state.last_student_answer = user_text

    # Academic-only guardrail
    if not is_academic_query(user_text) or not is_academic_query(st.session_state.current_question):
        add_msg("assistant", "I can help only with academic/learning questions. Please ask something educational (concepts, problems, explanations).")
        st.rerun()

    # Require question
    if not st.session_state.current_question.strip():
        add_msg("assistant", "Please enter the **Question** in the left panel first, then type your answer.")
        st.rerun()

    # Start analysis via router
    add_msg("assistant", "⏳ Analyzing…")
    st.session_state.pending_placeholder_index = len(st.session_state.messages) - 1
    st.session_state.pending_input = user_text
    st.session_state.pending = True
    st.session_state.pending_request_id = str(uuid.uuid4())
    st.session_state.cancel_requested = False
    st.session_state.cancel_request_id = None
    st.session_state._force_give_up = False
    st.rerun()

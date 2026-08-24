"""Recruiter-facing UI on top of the `recruiting` package.

Same functions the notebooks call directly (`extract_candidate`,
`evaluate_candidate`, `generate_questions`, ...) - this is the click-through
version. The floating "Chat with the agent" widget (bottom-left) wires up
the same conversational agent as notebook 04 (`create_agent` + tools),
sharing this session's candidate/JD data instead of duplicating it. Run with:

    uv run streamlit run recruiter_app.py

Every action that *writes* somewhere (booking a calendar event) requires an
explicit click, or an explicit confirmation in the chat, after seeing the
proposed options first - never a side effect of loading the page.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # must run before importing `recruiting` - its modules build an LLM client at import time

from recruiting import (
    CandidateEvaluation,
    apply_bias_check,
    evaluate_candidate,
    extract_candidate,
    extract_job_description,
    generate_questions,
    rank_candidates,
    score_for_categories,
)

CRITERIA = {"Experience": "experience", "Skills": "skills", "Education": "education", "Certs": "certifications"}

st.set_page_config(page_title="HireSense", layout="wide")

FB_PRIMARY = "#1D4ED8"
FB_PRIMARY_HOVER = "#1E3A8A"
FB_MUTED = "#5C7A99"
FB_BORDER = "#D6E4F7"

if "home_stage" not in st.session_state:
    st.session_state.home_stage = "landing"  # landing -> loading -> app

st.markdown(
    f"""
    <style>
    .stApp {{ background: #EFF5FC; }}

    /* cards: candidate panels, metrics, expanders - all one white-card language */
    div[data-testid="stContainer"][style*="border"],
    div[data-testid="stExpander"],
    div[data-testid="stMetric"] {{
        background: #FFFFFF !important;
        border: 1px solid {FB_BORDER} !important;
        border-radius: 1.1rem !important;
        box-shadow: 0 1px 3px rgba(16, 24, 40, 0.05);
        transition: box-shadow 0.15s ease, border-color 0.15s ease;
    }}
    div[data-testid="stContainer"][style*="border"] {{ padding: 1rem 1.15rem; }}
    div[data-testid="stContainer"][style*="border"]:hover {{
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.12);
        border-color: rgba(37, 99, 235, 0.35) !important;
    }}
    div[data-testid="stExpander"] summary {{ border-radius: 1.1rem; font-weight: 600; }}

    /* metric text: bold dark value, small caps muted label - FinBank's stat-card look */
    div[data-testid="stMetric"] {{
        text-align: center;
        display: flex;
        flex-direction: column;
        align-items: center;
    }}
    div[data-testid="stMetricValue"] {{ color: #1F2937; font-weight: 700; }}
    div[data-testid="stMetricLabel"] {{
        color: {FB_MUTED}; text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.72rem;
    }}

    /* tabs: underline style instead of boxed */
    div[data-testid="stTabs"] button[role="tab"] {{
        font-size: 0.95rem; font-weight: 600; color: {FB_MUTED}; padding: 0.5rem 1rem;
    }}
    div[data-testid="stTabs"] button[aria-selected="true"] {{ color: {FB_PRIMARY}; }}

    /* chat bubbles: white cards, not gray tint */
    div[data-testid="stChatMessage"] {{
        border-radius: 1.1rem;
        padding: 0.6rem 1rem;
        background: #FFFFFF;
        border: 1px solid {FB_BORDER};
        box-shadow: 0 1px 3px rgba(16, 24, 40, 0.04);
        margin-bottom: 0.6rem;
    }}

    /* buttons: pill-shaped, blue primary */
    div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button {{
        border-radius: 999px;
        font-weight: 600;
        transition: transform 0.1s ease, box-shadow 0.15s ease;
    }}
    div[data-testid="stButton"] button:hover {{ transform: translateY(-1px); }}
    div[data-testid="stButton"] button[kind="primary"] {{
        background: {FB_PRIMARY};
        border-color: {FB_PRIMARY};
        box-shadow: 0 4px 10px rgba(37, 99, 235, 0.25);
    }}
    div[data-testid="stButton"] button[kind="primary"]:hover {{ background: {FB_PRIMARY_HOVER}; }}

    /* sidebar: white panel, blue uppercase section labels like a nav rail */
    section[data-testid="stSidebar"] {{ background: #FFFFFF; border-right: 1px solid {FB_BORDER}; }}
    section[data-testid="stSidebar"] h2 {{
        color: {FB_PRIMARY}; text-transform: uppercase; font-size: 0.78rem; letter-spacing: 0.07em;
    }}

    h1 {{ color: #1F2937 !important; font-weight: 700 !important; }}

    /* floating chat: launcher and panel share the same bottom-right slot -
       only one is ever visible, matching a normal chat-widget pattern. */
    div.st-key-chat_launcher {{
        position: fixed;
        bottom: 1.5rem;
        right: 1.5rem;
        z-index: 1000;
        width: auto !important;
    }}
    div.st-key-chat_launcher button {{
        border-radius: 999px;
        padding: 0.7rem 1.4rem;
        background: {FB_PRIMARY};
        color: #fff;
        border: none;
        box-shadow: 0 8px 20px rgba(37, 99, 235, 0.35);
    }}
    div.st-key-chat_launcher button:hover {{ background: {FB_PRIMARY_HOVER}; }}

    div.st-key-chat_panel {{
        position: fixed;
        bottom: 1.5rem;
        right: 1.5rem;
        width: 360px;
        height: 70vh;
        min-width: 300px;
        min-height: 320px;
        max-width: 90vw;
        max-height: 90vh;
        resize: both;
        overflow: auto;
        z-index: 999;
        background: #FFFFFF !important;
        border: 1px solid {FB_BORDER} !important;
        border-radius: 1.1rem !important;
        box-shadow: 0 16px 40px rgba(16, 24, 40, 0.22);
        padding: 1rem 1.15rem !important;
    }}
    div.st-key-chat_panel, div.st-key-chat_panel p {{ font-size: 0.82rem; }}
    div.st-key-chat_panel div[data-testid="stCaptionContainer"] {{ font-size: 0.7rem; }}

    /* header: avatar circle + title/subtitle + a bare close (x) button */
    div.st-key-chat_close button {{
        background: transparent !important;
        color: {FB_MUTED} !important;
        border: none !important;
        box-shadow: none !important;
        font-size: 1.2rem !important;
        line-height: 1 !important;
        padding: 0 !important;
        width: 1.8rem;
        height: 1.8rem;
    }}
    div.st-key-chat_close button:hover {{ color: #1F2937 !important; transform: none; }}

    /* message cards: full-width labeled cards instead of left/right bubbles -
       one shared rule (matched by the "msg_"/"chat_streaming" key substring)
       so markdown inside each still renders through plain st.markdown calls. */
    div[class*="st-key-msg_"], div.st-key-chat_streaming {{
        border-radius: 0.9rem;
        padding: 0.65rem 0.9rem;
        margin-bottom: 0.6rem;
        border: none !important;
        box-shadow: none !important;
    }}
    div[class*="st-key-msg_"] p, div.st-key-chat_streaming p {{
        font-size: 0.82rem; margin: 0.15rem 0 0; color: #1F2937;
        word-wrap: break-word; overflow-wrap: anywhere;
    }}
    div[class*="st-key-msg_"][class*="_assistant"], div.st-key-chat_streaming {{ background: #DBEAFE; }}
    div[class*="st-key-msg_"][class*="_user"] {{ background: #EEF2F8; }}

    /* input: multi-line textarea + hint caption + a pill send button.
       field-sizing:content (Chromium/Edge) grows the box to fit what's typed
       instead of leaving a short message stranded in a tall empty box; older
       browsers just keep the min-height below, no breakage either way. */
    div.st-key-chat_panel div[data-testid="stTextArea"] textarea {{
        border-radius: 0.9rem;
        border: 1px solid {FB_BORDER};
        font-size: 0.82rem;
        line-height: 1.5;
        padding: 0.7rem 0.85rem;
        resize: none;
        field-sizing: content;
        min-height: 2.6rem;
        max-height: 40vh;
    }}
    div.st-key-chat_panel div[data-testid="stFormSubmitButton"] button {{
        border-radius: 999px;
        background: {FB_PRIMARY};
        color: #fff;
        border: none;
        font-weight: 600;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


def _section_label(title: str, color: str, count: int | None = None) -> str:
    suffix = f" &middot; {count}" if count is not None else ""
    return (
        f'<div style="font-weight:700;color:{color};font-size:0.78rem;'
        f'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.5rem;">'
        f"{title}{suffix}</div>"
    )


def _chips(items: list[str], tone: str) -> str:
    palette = {
        "essential": ("#DBEAFE", FB_PRIMARY, "rgba(37, 99, 235, 0.25)"),
        "preferred": ("#EEF2F8", "#4B5563", FB_BORDER),
    }
    bg, fg, border = palette[tone]
    if not items:
        return f'<span style="color:{FB_MUTED};font-size:0.85rem;">None listed</span>'
    spans = "".join(
        f'<span style="display:inline-block;background:{bg};color:{fg};border:1px solid {border};'
        f'border-radius:999px;padding:0.35rem 0.85rem;margin:0.2rem 0.3rem 0.2rem 0;'
        f'font-size:0.85rem;font-weight:500;">{item}</span>'
        for item in items
    )
    return f'<div style="display:flex;flex-wrap:wrap;">{spans}</div>'


def _donut(percent: float, label: str, sublabel: str) -> str:
    percent = max(0.0, min(100.0, percent))
    return f"""
    <div style="text-align:center;">
      <div style="width:108px;height:108px;border-radius:50%;margin:0 auto 0.5rem;
                  background:conic-gradient({FB_PRIMARY} {percent}%, {FB_BORDER} {percent}% 100%);
                  display:flex;align-items:center;justify-content:center;">
        <div style="width:80px;height:80px;border-radius:50%;background:#fff;
                    display:flex;flex-direction:column;align-items:center;justify-content:center;">
          <span style="font-size:1.25rem;font-weight:700;color:#1F2937;">{percent:.0f}</span>
          <span style="font-size:0.6rem;color:{FB_MUTED};">/ 100</span>
        </div>
      </div>
      <div style="font-weight:600;color:#1F2937;font-size:0.85rem;">{label}</div>
      <div style="font-size:0.75rem;color:{FB_MUTED};">{sublabel}</div>
    </div>
    """

SAMPLE_DIR = Path(__file__).parent / "sample_data"


# -- cached clients -----------------------------------------------------


@st.cache_resource
def _drive_client():
    from recruiting import DriveClient

    return DriveClient()


@st.cache_resource
def _calendar_client(calendar_id: str):
    from recruiting import CalendarClient

    return CalendarClient(calendar_id=calendar_id)


# -- data loading ---------------------------------------------------------


def _load_jd_text(source: str, jd_folder_id: str) -> tuple[str, str]:
    if source == "Google Drive":
        drive = _drive_client()
        f = drive.latest(jd_folder_id)
        if not f:
            raise ValueError("No files in the JD folder.")
        return drive.fetch_text(f), f.name
    path = SAMPLE_DIR / "job_description.txt"
    return path.read_text(encoding="utf-8"), path.name


def _load_resume_texts(source: str, resumes_folder_id: str) -> list[tuple[str, str]]:
    if source == "Google Drive":
        drive = _drive_client()
        return [(drive.fetch_text(f), f.name) for f in drive.list_files(resumes_folder_id)]
    return [(p.read_text(encoding="utf-8"), p.name) for p in sorted(SAMPLE_DIR.glob("resume_*.txt"))]


def _refresh(source: str, jd_folder_id: str, resumes_folder_id: str) -> None:
    """(Re)build every evaluation. Only re-extracts resumes whose text changed,
    so editing the JD or dropping in one new resume does not re-score everyone."""
    jd_text, jd_name = _load_jd_text(source, jd_folder_id)
    jd = extract_job_description(jd_text, source_file=jd_name)
    st.session_state.jd = jd

    cache: dict[str, CandidateEvaluation] = st.session_state.setdefault("evaluations", {})
    seen = set()
    for text, name in _load_resume_texts(source, resumes_folder_id):
        seen.add(name)
        if name in cache and cache[name].candidate.raw_text == text:
            continue  # unchanged, keep the cached evaluation (and its questions/bias flags)
        candidate = extract_candidate(text, source_file=name)
        cache[name] = evaluate_candidate(candidate, jd)
    for stale in set(cache) - seen:
        del cache[stale]


def _safe_refresh(source: str, jd_folder_id: str, resumes_folder_id: str) -> str | None:
    """Returns None on success, or a user-facing error message on failure -
    the caller decides where to display it (a plain st.error isn't visible
    when called from behind the full-screen homepage overlay)."""
    try:
        _refresh(source, jd_folder_id, resumes_folder_id)
        return None
    except FileNotFoundError as exc:
        return f"Google sign-in isn't set up yet: {exc}"
    except Exception as exc:  # Drive/API errors, bad folder ids, etc.
        return f"Couldn't load candidates from {source}: {exc}"


# -- conversational agent (shared with notebook 04's design) ---------------
#
# LangChain's agent executor runs tool calls on worker threads that don't
# carry Streamlit's ScriptRunContext, so `st.session_state` reads inside a
# @tool function silently see empty state (confirmed via AppTest - the agent
# reported "no candidates loaded" despite the Candidates tab showing them).
# `_agent_state` is a plain, non-Streamlit object the main thread syncs
# right before invoking the agent; tools read/write it instead.


class _AgentState:
    evaluations: dict[str, CandidateEvaluation] = {}
    calendar_id: str = "primary"
    interviewer_emails: str = ""
    last_slots: list = []
    last_emails: list[str] = []
    pending_questions: dict[str, list] = {}


_agent_state = _AgentState()
_agent_state.pending_questions = {}


@lru_cache(maxsize=8)
def _agent_calendar_client(calendar_id: str):
    from recruiting import CalendarClient

    return CalendarClient(calendar_id=calendar_id)


def _find_evaluation(name: str) -> CandidateEvaluation | None:
    return next(
        (v for v in _agent_state.evaluations.values() if name.lower() in v.candidate.name.lower()), None
    )


def _agent_tools() -> list:
    from langchain.tools import tool

    @tool
    def list_candidates() -> list[dict]:
        """List every candidate for the current JD, ranked best first, with
        score and whether they're tied with the next candidate."""
        ranked = rank_candidates(list(_agent_state.evaluations.values()))
        return [
            {"name": e.candidate.name, "score": e.score, "tied_with_next": e.tied_with_next}
            for e in ranked
        ]

    @tool
    def get_candidate_evidence(name: str) -> dict:
        """Full per-requirement evidence for one candidate: matched/not, quotes,
        transferable-skill notes, missing info, inconsistencies. Call this
        before explaining why someone is or isn't a fit."""
        e = _find_evaluation(name)
        if not e:
            return {"error": f"no candidate matches {name!r}"}
        return {
            "candidate": e.candidate.name,
            "score": e.score,
            "matches": [m.__dict__ for m in e.matches],
            "missing_info": e.missing_info,
            "inconsistencies": e.inconsistencies,
        }

    @tool
    def generate_interview_questions_for(name: str) -> list[dict]:
        """Personalized interview questions for one candidate, grounded in
        their specific gaps and transferable-skill matches."""
        e = _find_evaluation(name)
        if not e:
            return [{"error": f"no candidate matches {name!r}"}]
        questions = generate_questions(e)
        _agent_state.pending_questions[e.candidate.source_file] = questions
        return [q.__dict__ for q in questions]

    @tool
    def check_bias_for(name: str) -> list[str]:
        """Re-check one candidate's evaluation reasoning for bias. Run this
        before finalizing a recommendation."""
        e = _find_evaluation(name)
        if not e:
            return [f"no candidate matches {name!r}"]
        apply_bias_check(e)  # mutates e.bias_flags in place - e is the same
        return e.bias_flags  # object the Candidates tab reads, so this is already visible there

    @tool
    def propose_interview_slots(interviewer_emails: list[str] | None = None, duration_min: int = 45) -> list[str]:
        """Propose open interview slots across every interviewer's calendar.
        This only reads calendars - it never books anything. If
        interviewer_emails is omitted, uses the emails configured in the
        sidebar. Always call this and show the options to the recruiter
        before ever calling book_interview."""
        emails = interviewer_emails or [
            e.strip() for e in _agent_state.interviewer_emails.split(",") if e.strip()
        ]
        if not emails:
            return ["No interviewer emails available - add some in the sidebar first."]
        cal = _agent_calendar_client(_agent_state.calendar_id)
        slots = cal.find_free_slots(emails, duration_min=duration_min)
        _agent_state.last_slots = slots
        _agent_state.last_emails = emails
        if not slots:
            return ["No open slots in the next few days - try widening the search."]
        return [f"{i}: {s}" for i, s in enumerate(slots)]

    @tool
    def book_interview(candidate_name: str, slot_index: int) -> str:
        """Book the interview at the given slot index from the most recent
        propose_interview_slots call. ONLY call this after the recruiter has
        explicitly confirmed a slot in the conversation - never on your own
        initiative."""
        slots = _agent_state.last_slots
        emails = _agent_state.last_emails
        if not (0 <= slot_index < len(slots)):
            return "That slot index isn't from the most recent proposal - call propose_interview_slots again."
        cal = _agent_calendar_client(_agent_state.calendar_id)
        link = cal.create_event(
            summary=f"Interview: {candidate_name}", slot=slots[slot_index], attendee_emails=emails
        )
        return f"Booked. {link}"

    return [
        list_candidates,
        get_candidate_evidence,
        generate_interview_questions_for,
        check_bias_for,
        propose_interview_slots,
        book_interview,
    ]


@st.cache_resource
def _agent():
    from langchain.agents import create_agent

    from recruiting import get_model

    return create_agent(
        model=get_model(),
        tools=_agent_tools(),
        system_prompt=(
            "You help a recruiter screen candidates for one open role. Always call "
            "list_candidates first to see who's in play. Before explaining why "
            "someone is or isn't a fit, call get_candidate_evidence - never assert "
            "a match without it. If two candidates are close in score, say so "
            "explicitly instead of picking a favorite. Before finalizing a "
            "recommendation, call check_bias_for on it. "
            "For scheduling: always call propose_interview_slots and show the "
            "options to the recruiter first. Only call book_interview after the "
            "recruiter has explicitly picked a slot in this conversation - never "
            "book on your own initiative. "
            "This chat renders in a small widget: reply in plain prose or short "
            "bullet points, and never use markdown headings (#, ##, ###)."
        ),
    )


def _stream_agent_reply(user_msg: str):
    """Yields text deltas as the model generates them - tool-call steps also
    pass through `stream_mode="messages"` but with empty content, so only the
    final human-readable answer actually produces chunks here."""
    from langchain_core.messages import AIMessageChunk, HumanMessage

    for chunk, _meta in _agent().stream({"messages": [HumanMessage(user_msg)]}, stream_mode="messages"):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            yield chunk.content


# -- one candidate's panel -------------------------------------------------


def _match_rows(matches: list) -> str:
    if not matches:
        return f'<div style="color:{FB_MUTED};font-size:0.85rem;padding:0.5rem 0;">None</div>'
    rows = []
    for m in matches:
        dot = FB_PRIMARY if m.matched else "#D1D5DB"
        title_color = "#1F2937" if m.matched else FB_MUTED
        transfer = (
            f'<span style="color:{FB_MUTED};font-weight:400;font-size:0.78rem;"> &middot; transferable</span>'
            if m.transferable
            else ""
        )
        details = ""
        if m.evidence:
            details += (
                f'<div style="font-size:0.8rem;color:{FB_MUTED};margin-top:0.3rem;line-height:1.45;">'
                f"{m.evidence}</div>"
            )
        if m.note:
            details += (
                f'<div style="font-size:0.78rem;color:{FB_MUTED};margin-top:0.2rem;line-height:1.4;">{m.note}</div>'
            )
        rows.append(
            f'<div style="display:flex;gap:0.75rem;padding:0.85rem 0.2rem;border-bottom:1px solid {FB_BORDER};">'
            f'<div style="width:8px;height:8px;border-radius:50%;background:{dot};margin-top:0.4rem;flex-shrink:0;"></div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-weight:600;color:{title_color};font-size:0.92rem;line-height:1.4;">'
            f"{m.requirement}{transfer}</div>"
            f"{details}"
            f"</div></div>"
        )
    rows[-1] = rows[-1].replace(f"border-bottom:1px solid {FB_BORDER};", "border-bottom:none;")
    return "".join(rows)


def _callout(title: str, items: list[str], bg: str, fg: str, border: str) -> str:
    lines = "".join(f'<div style="margin-top:0.3rem;line-height:1.45;">{item}</div>' for item in items)
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:0.85rem;'
        f'padding:0.75rem 0.95rem;margin-top:0.7rem;font-size:0.82rem;color:{fg};">'
        f'<div style="font-weight:700;font-size:0.74rem;text-transform:uppercase;'
        f'letter-spacing:0.05em;">{title}</div>'
        f"{lines}</div>"
    )


_PDF_CHAR_MAP = str.maketrans(
    {
        "—": "-",  # em dash
        "–": "-",  # en dash
        "‘": "'",
        "’": "'",  # curly single quotes
        "“": '"',
        "”": '"',  # curly double quotes
        "…": "...",  # ellipsis
        " ": " ",  # non-breaking space
        "•": "-",  # bullet
    }
)


def _pdf_safe(text: str) -> str:
    """fpdf2's core Helvetica font only supports Latin-1 - LLM output
    routinely has smart punctuation (em-dashes, curly quotes) that would
    otherwise crash generation with FPDFUnicodeEncodingException. Anything
    left over after the common-case swaps (e.g. non-Latin script) is
    replaced rather than allowed to crash the download."""
    text = text.translate(_PDF_CHAR_MAP)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _questions_pdf_bytes(candidate_name: str, questions: list) -> bytes:
    from fpdf import FPDF

    candidate_name = _pdf_safe(candidate_name)
    primary_rgb = tuple(int(FB_PRIMARY[i : i + 2], 16) for i in (1, 3, 5))

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()

    pdf.set_fill_color(*primary_rgb)
    pdf.rect(0, 0, pdf.w, 26, style="F")
    pdf.set_xy(18, 8)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 8, f"Interview Questions - {candidate_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(18, 34)

    for i, q in enumerate(questions, start=1):
        if pdf.will_page_break(20):
            pdf.add_page()
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(31, 41, 55)
        pdf.multi_cell(0, 6, _pdf_safe(f"{i}. {q.question}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(107, 114, 128)
        pdf.multi_cell(
            0, 5.5, _pdf_safe(f"Why: {q.rationale}  |  Targets: {q.targets}"), new_x="LMARGIN", new_y="NEXT"
        )
        pdf.ln(3)

    return bytes(pdf.output())


@st.dialog("Interview Questions", width="large")
def _questions_dialog(candidate_name: str, questions: list) -> None:
    st.caption(candidate_name)
    for i, q in enumerate(questions, start=1):
        st.markdown(f"**{i}. {q.question}**")
        st.caption(f"{q.rationale}  ·  targets: {q.targets}")
        st.divider()
    st.download_button(
        "Download as PDF",
        data=_questions_pdf_bytes(candidate_name, questions),
        file_name=f"{candidate_name.replace(' ', '_').lower()}_interview_questions.pdf",
        mime="application/pdf",
        use_container_width=True,
    )


def _candidate_panel(evaluation: CandidateEvaluation, calendar_id: str, interviewer_emails_raw: str) -> None:
    key = evaluation.candidate.source_file
    met, total = evaluation.essential_coverage()

    st.progress(met / total if total else 0.0, text=f"Essential requirements met: {met}/{total}")

    essentials = [m for m in evaluation.matches if m.essential]
    preferred = [m for m in evaluation.matches if not m.essential]

    col_e, col_p = st.columns(2)
    with col_e:
        with st.expander(f"Essential ({len(essentials)})"):
            st.markdown(_match_rows(essentials), unsafe_allow_html=True)
    with col_p:
        with st.expander(f"Preferred ({len(preferred)})"):
            st.markdown(_match_rows(preferred), unsafe_allow_html=True)

    if evaluation.missing_info:
        st.markdown(
            _callout("Missing information", evaluation.missing_info, "#FFF8EC", "#92400E", "#FBE3B8"),
            unsafe_allow_html=True,
        )
    if evaluation.inconsistencies:
        st.markdown(
            _callout("Inconsistencies", evaluation.inconsistencies, "#FDF2F2", "#9B1C1C", "#F5CFCF"),
            unsafe_allow_html=True,
        )

    st.markdown('<div style="margin-top:1.1rem;"></div>', unsafe_allow_html=True)
    btn_cols = st.columns(3, vertical_alignment="bottom", gap="medium")

    with btn_cols[0]:
        if st.button("Generate interview questions", key=f"q-{key}", use_container_width=True):
            with st.spinner("Generating..."):
                questions = generate_questions(evaluation)
                st.session_state.setdefault("questions", {})[key] = questions
            _questions_dialog(evaluation.candidate.name, questions)
        cached_questions = st.session_state.get("questions", {}).get(key)
        if cached_questions and st.button("View questions", key=f"q-view-{key}", use_container_width=True):
            _questions_dialog(evaluation.candidate.name, cached_questions)

    with btn_cols[1]:
        if st.button("Check for bias", key=f"bias-{key}", use_container_width=True):
            with st.spinner("Checking..."):
                apply_bias_check(evaluation)
        for flag in evaluation.bias_flags:
            st.warning(flag)

    with btn_cols[2]:
        if st.button("Flag as disputed", key=f"dispute-btn-{key}", use_container_width=True):
            note = st.session_state.get(f"dispute-note-{key}", "")
            st.session_state.setdefault("disputes", {})[key] = note or "disputed, no note"
            st.rerun()
        st.text_input("Flag this evaluation", key=f"dispute-note-{key}", placeholder="Optional note")

    st.markdown('<div style="margin-top:0.4rem;"></div>', unsafe_allow_html=True)
    st.markdown(_section_label("Schedule an interview", FB_MUTED), unsafe_allow_html=True)
    emails = [e.strip() for e in interviewer_emails_raw.split(",") if e.strip()]
    if not emails:
        st.caption("Add interviewer emails in the sidebar to schedule.")
        return

    if st.button("Propose interview times", key=f"propose-{key}"):
        with st.spinner("Checking calendars..."):
            cal = _calendar_client(calendar_id)
            st.session_state.setdefault("slots", {})[key] = cal.find_free_slots(emails)

    slots = st.session_state.get("slots", {}).get(key)
    if slots:
        choice = st.radio(
            "Open slots",
            options=range(len(slots)),
            format_func=lambda i: str(slots[i]),
            key=f"slotpick-{key}",
        )
        if st.button("Confirm & book this slot", key=f"book-{key}"):
            with st.spinner("Booking..."):
                cal = _calendar_client(calendar_id)
                link = cal.create_event(
                    summary=f"Interview: {evaluation.candidate.name}",
                    slot=slots[choice],
                    attendee_emails=emails,
                )
            st.success(f"Booked. [Open event]({link})")


# -- homepage: landing (Get Started) -> loading (does the real work) -> app -
# Placed after _safe_refresh so the loading stage can call it directly, and
# before the sidebar so landing/loading are clean full-screen takeovers.

# both stages render inside a `key`-ed container so this CSS can turn that
# *real* container into the full-screen overlay - unlike raw HTML tags split
# across separate st.markdown calls, a `with st.container(key=...):` block
# genuinely nests its children (including real widgets like st.button) in
# the actual DOM, so they render correctly on top of the gradient instead of
# being an invisible sibling behind it.
st.markdown(
    """
    <style>
    div.st-key-landing_stage, div.st-key-loading_stage, div.st-key-loading_stage_retry {
        position: fixed; inset: 0; z-index: 999999;
        background: linear-gradient(135deg, #0B1E4D 0%, #1E3A8A 45%, #1D4ED8 100%);
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        text-align: center; padding: 2rem;
        border: none !important; box-shadow: none !important;
    }
    .hiresense-logo {
        width: 64px; height: 64px; border-radius: 1.1rem; background: rgba(255,255,255,0.12);
        border: 1px solid rgba(255,255,255,0.25);
        display: flex; align-items: center; justify-content: center;
        color: #fff; font-weight: 800; font-size: 1.6rem; margin-bottom: 1.1rem;
    }
    .hiresense-title {
        color: #fff; font-size: 3.2rem; font-weight: 800; letter-spacing: -0.02em;
        margin-bottom: 0.5rem;
    }
    .hiresense-tagline { color: rgba(255,255,255,0.82); font-size: 1.05rem; margin-bottom: 1.8rem; max-width: 32rem; }
    .hiresense-features {
        display: flex; gap: 0.75rem; flex-wrap: wrap; justify-content: center; margin-bottom: 2rem;
    }
    .hiresense-feature {
        background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2);
        color: #fff; border-radius: 999px; padding: 0.45rem 1rem; font-size: 0.82rem; font-weight: 500;
    }
    .hiresense-spinner {
        width: 38px; height: 38px; border-radius: 50%;
        border: 4px solid rgba(255,255,255,0.25); border-top-color: #fff;
        animation: hiresense-spin 0.8s linear infinite; margin-bottom: 1rem;
    }
    @keyframes hiresense-spin { to { transform: rotate(360deg); } }
    .hiresense-status { color: rgba(255,255,255,0.85); font-size: 0.95rem; }

    /* the Get Started button: white pill, dark blue text, clear CTA on the gradient */
    div.st-key-landing_stage div[data-testid="stButton"] { max-width: 260px; }
    div.st-key-landing_stage div[data-testid="stButton"] button {
        background: #fff; color: #1E3A8A; border: none; font-weight: 700;
        padding: 0.7rem 1rem; box-shadow: 0 8px 20px rgba(0,0,0,0.25);
    }
    div.st-key-landing_stage div[data-testid="stButton"] button:hover { background: #EFF5FC; }
    </style>
    """,
    unsafe_allow_html=True,
)

if st.session_state.home_stage == "landing":
    with st.container(key="landing_stage"):
        st.markdown('<div class="hiresense-logo">H</div>', unsafe_allow_html=True)
        st.markdown('<div class="hiresense-title">HireSense</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="hiresense-tagline">AI-powered candidate screening, ranking, and '
            "scheduling - with evidence for every decision.</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="hiresense-features">'
            '<span class="hiresense-feature">Evidence-based ranking</span>'
            '<span class="hiresense-feature">Bias-aware evaluations</span>'
            '<span class="hiresense-feature">One-click scheduling</span>'
            "</div>",
            unsafe_allow_html=True,
        )
        if st.button("Get Started", key="get_started_btn", use_container_width=True):
            st.session_state.home_stage = "loading"
            st.rerun()
    st.stop()

if st.session_state.home_stage == "loading":
    placeholder = st.empty()
    with placeholder.container(key="loading_stage"):
        st.markdown('<div class="hiresense-logo">H</div>', unsafe_allow_html=True)
        st.markdown('<div class="hiresense-spinner"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="hiresense-status">Reading resumes and job description...</div>',
            unsafe_allow_html=True,
        )

    default_source = "Google Drive" if os.environ.get("GOOGLE_DRIVE_JD_FOLDER_ID") else "Sample data"
    error = _safe_refresh(
        default_source,
        os.environ.get("GOOGLE_DRIVE_JD_FOLDER_ID", ""),
        os.environ.get("GOOGLE_DRIVE_RESUMES_FOLDER_ID", ""),
    )
    if error is None:
        st.session_state.home_stage = "app"
        st.rerun()
    else:
        # a distinct key from the spinner container above - Streamlit
        # disallows two elements sharing one explicit key within the same
        # script run, even via the same st.empty() placeholder.
        with placeholder.container(key="loading_stage_retry"):
            st.markdown('<div class="hiresense-logo">H</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="hiresense-status">{error}</div>', unsafe_allow_html=True)
            if st.button("Try again", key="loading_retry_btn", use_container_width=True):
                st.rerun()  # already "loading" - reruns straight back into this same block
        st.stop()


# -- sidebar ----------------------------------------------------------------

with st.sidebar:
    st.markdown(
        f'<div style="font-weight:800;font-size:1.15rem;color:{FB_PRIMARY};margin-bottom:1rem;">'
        f"HireSense</div>",
        unsafe_allow_html=True,
    )
    st.header("Source")
    default_source = "Google Drive" if os.environ.get("GOOGLE_DRIVE_JD_FOLDER_ID") else "Sample data"
    source = st.radio(
        "Data source",
        ["Sample data", "Google Drive"],
        index=["Sample data", "Google Drive"].index(default_source),
        label_visibility="collapsed",
    )
    jd_folder_id = st.text_input("JD folder ID", value=os.environ.get("GOOGLE_DRIVE_JD_FOLDER_ID", ""))
    resumes_folder_id = st.text_input(
        "Resumes folder ID", value=os.environ.get("GOOGLE_DRIVE_RESUMES_FOLDER_ID", "")
    )

    if st.button("Refresh candidates", type="primary", use_container_width=True):
        with st.spinner("Reading resumes and job description..."):
            error = _safe_refresh(source, jd_folder_id, resumes_folder_id)
        if error is None:
            st.rerun()
        else:
            st.error(error)

    st.divider()
    st.header("Scheduling")
    calendar_id = st.text_input(
        "Calendar ID", value=os.environ.get("GOOGLE_CALENDAR_ID", "primary"), key="calendar_id"
    )
    interviewer_emails = st.text_input(
        "Interviewer emails (comma-separated)",
        value=os.environ.get("INTERVIEWER_EMAILS", ""),
        key="interviewer_emails",
    )

    st.divider()
    agent_ready = bool(os.environ.get("LITELLM_API_KEY"))
    st.caption("Agent: " + ("ready" if agent_ready else "needs LITELLM_API_KEY in .env"))


# -- first load ---------------------------------------------------------

if "evaluations" not in st.session_state:
    with st.spinner("Reading resumes and job description..."):
        error = _safe_refresh(source, jd_folder_id, resumes_folder_id)
    if error is not None:
        st.error(error)
        st.stop()

jd = st.session_state.jd
evaluations: dict[str, CandidateEvaluation] = st.session_state.evaluations

# -- header -----------------------------------------------------------------

st.title(f"Welcome to the {jd.title or 'Candidates'} search")
st.caption("Here's where things stand on your open role.")

n_essential, n_preferred = len(jd.essential_requirements), len(jd.preferred_requirements)
with st.expander(f"Job description  ·  {n_essential} essential  ·  {n_preferred} preferred"):
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown(_section_label("Essential", FB_PRIMARY, n_essential), unsafe_allow_html=True)
        st.markdown(_chips(jd.essential_requirements, "essential"), unsafe_allow_html=True)
    with col2:
        st.markdown(_section_label("Preferred", FB_MUTED, n_preferred), unsafe_allow_html=True)
        st.markdown(_chips(jd.preferred_requirements, "preferred"), unsafe_allow_html=True)

selected = st.pills("Rank by", list(CRITERIA.keys()), selection_mode="multi", default=[])
categories = {CRITERIA[label] for label in selected} or None

ranked = rank_candidates(list(evaluations.values()), categories=categories)

if ranked:
    top_score = score_for_categories(ranked[0], categories)
    top_tier = "Strong match" if top_score >= 80 else "Possible match" if top_score >= 50 else "Weak match"

    m1, m2, m3, m4 = st.columns([1.3, 1, 1, 1])
    with m1:
        with st.container(border=True):
            st.markdown(_donut(top_score, "Top score", top_tier), unsafe_allow_html=True)
    m2.metric("Candidates", len(ranked), border=True)
    m3.metric("Tied for 1st", sum(1 for e in ranked if e.tied_with_next), border=True)
    m4.metric("Flagged", sum(1 for e in ranked if e.bias_flags or e.inconsistencies), border=True)

st.divider()

# -- ranked candidates -------------------------------------------------------

if not ranked:
    st.info("No candidates yet - hit **Refresh** in the sidebar.")
else:
    st.subheader(f"{len(ranked)} candidates")
    disputes: dict[str, str] = st.session_state.get("disputes", {})

    for evaluation in ranked:
        met, total = evaluation.essential_coverage()
        score = score_for_categories(evaluation, categories)
        tier_color = "primary" if score >= 80 else "orange" if score >= 50 else "red"
        tier_label = "Strong" if score >= 80 else "Possible" if score >= 50 else "Weak"

        with st.container(border=True):
            head = st.columns([3, 1, 1.3])
            with head[0]:
                st.markdown(f"### {evaluation.candidate.name}")
                st.badge(tier_label, color=tier_color)
            with head[1]:
                st.metric("Score", f"{score:.0f}")
            with head[2]:
                st.metric("Essential met", f"{met}/{total}")

            with st.container(horizontal=True):
                if evaluation.tied_with_next:
                    st.badge("Tied", color="orange")
                if evaluation.missing_info:
                    st.badge("Gaps", color="gray")
                if evaluation.inconsistencies:
                    st.badge("Inconsistent", color="red")
                if evaluation.bias_flags:
                    st.badge("Bias flag", color="violet")
                if evaluation.candidate.source_file in disputes:
                    st.badge("Disputed", color="blue")

            _candidate_panel(evaluation, calendar_id, interviewer_emails)


# -- floating chat widget -----------------------------------------------------
# st.chat_input always docks to a full-width bar at the bottom of the whole
# page (Streamlit's "stBottom" container), so it can't live inside a small
# floating card - a plain form + text_area does, and gives the same
# Shift+Enter-for-newline layout without escaping the panel.


def _render_message(idx: int, role: str, text: str) -> None:
    label = "You" if role == "user" else "Recruiting Assistant"
    label_color = "#4B5563" if role == "user" else FB_PRIMARY
    with st.container(key=f"msg_{idx}_{role}"):
        st.markdown(
            f'<div style="font-weight:700;font-size:0.68rem;text-transform:uppercase;'
            f'letter-spacing:0.05em;color:{label_color};">{label}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(text)


if "chat_open" not in st.session_state:
    st.session_state.chat_open = False

if not st.session_state.chat_open:
    with st.container(key="chat_launcher"):
        if st.button("Chat with the agent", key="chat_toggle_btn", use_container_width=True):
            st.session_state.chat_open = True
            st.rerun()

if st.session_state.chat_open:
    with st.container(key="chat_panel"):
        head = st.columns([0.16, 0.68, 0.16], vertical_alignment="center")
        with head[0]:
            st.markdown(
                f'<div style="width:34px;height:34px;border-radius:50%;background:{FB_PRIMARY};'
                f'display:flex;align-items:center;justify-content:center;color:#fff;'
                f'font-weight:700;font-size:0.9rem;">R</div>',
                unsafe_allow_html=True,
            )
        with head[1]:
            st.markdown(
                '<div style="font-weight:700;font-size:0.92rem;color:#1F2937;line-height:1.25;">'
                "Recruiting Assistant</div>"
                f'<div style="font-size:0.7rem;color:{FB_MUTED};">Screening &amp; scheduling</div>',
                unsafe_allow_html=True,
            )
        with head[2]:
            with st.container(key="chat_close"):
                if st.button("×", key="chat_close_btn"):
                    st.session_state.chat_open = False
                    st.rerun()
        st.divider()

        if not agent_ready:
            st.error("Set LITELLM_API_KEY in `.env` to talk to the agent.")
        elif not ranked:
            st.info("No candidates yet - refresh from the sidebar.")
        else:
            # messages render here, always above the input below - the exchange
            # just sent is appended then the page reruns, instead of echoing it
            # inline, so ordering never flips relative to older history.
            for i, (role, content) in enumerate(st.session_state.get("chat_history", [])):
                _render_message(i, role, content)

            # keeps the panel scrolled to the newest message, including while
            # a reply is still streaming in token by token. A MutationObserver
            # (not a one-shot scroll) is needed because st.write_stream updates
            # the DOM incrementally within a single script run, with no rerun
            # in between to re-trigger a plain "scroll once" call.
            st.iframe(
                """
                <script>
                (function() {
                    const panel = window.parent.document.querySelector('.st-key-chat_panel');
                    if (!panel) return;
                    panel.scrollTop = panel.scrollHeight;
                    const observer = new MutationObserver(() => { panel.scrollTop = panel.scrollHeight; });
                    observer.observe(panel, {childList: true, subtree: true, characterData: true});
                })();
                </script>
                """,
                height=1,
            )

            with st.form(
                "floating_chat_form", clear_on_submit=True, border=False, enter_to_submit=False
            ):
                user_msg = st.text_area(
                    "Message",
                    label_visibility="collapsed",
                    placeholder='Ask things like "Explain more" or "Why is this wrong?"',
                    height=80,
                )
                hint_col, btn_col = st.columns([2.2, 1], vertical_alignment="center")
                hint_col.caption("Shift+Enter for a new line")
                sent = btn_col.form_submit_button("Send", use_container_width=True)

            if sent and user_msg:
                st.session_state.setdefault("chat_history", []).append(("user", user_msg))
                _render_message(len(st.session_state.chat_history) - 1, "user", user_msg)

                # main thread has ScriptRunContext - safe to touch session_state here
                _agent_state.evaluations = evaluations
                _agent_state.calendar_id = calendar_id
                _agent_state.interviewer_emails = interviewer_emails
                with st.container(key="chat_streaming"):
                    st.markdown(
                        f'<div style="font-weight:700;font-size:0.68rem;text-transform:uppercase;'
                        f'letter-spacing:0.05em;color:{FB_PRIMARY};">Recruiting Assistant</div>',
                        unsafe_allow_html=True,
                    )
                    try:
                        reply = st.write_stream(_stream_agent_reply(user_msg))
                    except Exception as exc:
                        reply = f"Something went wrong talking to the agent: {exc}"
                        st.markdown(reply)
                if _agent_state.pending_questions:
                    st.session_state.setdefault("questions", {}).update(_agent_state.pending_questions)
                    _agent_state.pending_questions.clear()

                st.session_state.chat_history.append(("assistant", reply))
                st.rerun()

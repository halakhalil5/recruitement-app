"""Personalized interview questions, grounded in one candidate's evaluation.

Not generic questions - each one targets a specific gap, an unverified
claim, or a transferable-skill match that is worth probing in person.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .llm import get_model
from .models import CandidateEvaluation, InterviewQuestion

_model = get_model()


class _Question(BaseModel):
    question: str
    rationale: str
    targets: str = Field(description="the requirement or gap this question probes")


class _Questions(BaseModel):
    questions: list[_Question]


def generate_questions(evaluation: CandidateEvaluation, count: int = 6) -> list[InterviewQuestion]:
    """Interview questions for one candidate, tied to their specific evaluation."""
    matches_summary = "\n".join(
        f"- [{'MET' if m.matched else 'GAP'}"
        f"{', transferable' if m.transferable else ''}] {m.requirement}: {m.evidence or m.note}"
        for m in evaluation.matches
    )
    result = _model.with_structured_output(_Questions).invoke(
        f"Candidate for: {evaluation.job_title}\n\n"
        f"Requirement-by-requirement evaluation:\n{matches_summary}\n\n"
        f"Missing information: {evaluation.missing_info}\n"
        f"Inconsistencies to probe: {evaluation.inconsistencies}\n\n"
        f"Write {count} interview questions for this specific candidate. "
        "Prioritize: verifying transferable-skill matches, probing gaps against "
        "essential requirements, and resolving any missing information or "
        "inconsistencies. Avoid generic questions that would apply to any candidate."
    )
    return [
        InterviewQuestion(question=q.question, rationale=q.rationale, targets=q.targets)
        for q in result.questions
    ]

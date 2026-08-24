"""Compare a candidate to a job description, with evidence for every call.

One structured LLM call per candidate: for every requirement (essential and
preferred) it decides whether the candidate meets it, quotes the resume text
that shows it, and says explicitly when a match is via a *transferable*
skill or different terminology rather than a literal one. It also surfaces
missing information and internal inconsistencies - it shows its work rather
than just handing back a score.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .llm import get_model
from .models import Candidate, CandidateEvaluation, EvidenceMatch, JobDescription

_model = get_model()

Category = Literal["experience", "skills", "education", "certifications"]
CATEGORIES: tuple[Category, ...] = ("experience", "skills", "education", "certifications")


class _MatchOutput(BaseModel):
    requirement: str
    essential: bool
    matched: bool
    category: Category = Field(
        default="skills",
        description=(
            "which aspect of the candidate this requirement is about: experience "
            "(years/roles/domains worked), skills (tools/frameworks/technical "
            "knowledge), education (degrees/coursework), or certifications "
            "(certifications, publications, research work)"
        ),
    )
    evidence: str = Field(
        default="", description="short quote or paraphrase from the resume; empty if not matched"
    )
    transferable: bool = Field(
        default=False, description="true if matched via a related/transferable skill, not a literal one"
    )
    note: str = Field(default="", description="one line of reasoning")


class _EvaluationOutput(BaseModel):
    matches: list[_MatchOutput]
    missing_info: list[str] = Field(
        default_factory=list, description="resume gaps that make evaluation harder, e.g. no dates on a role"
    )
    inconsistencies: list[str] = Field(
        default_factory=list,
        description="internal contradictions, e.g. overlapping employment dates, a claimed skill with no supporting evidence",
    )


def _coverage_score(matches: list) -> float:
    """0-100, weighted 75% essential coverage / 25% preferred coverage.
    Computed from the matches the LLM already produced rather than asking it
    to also self-report a number - one fewer field that a long response can
    get cut off before reaching, and it's what every category-filtered score
    already does (see `score_for_categories`), so "overall" is now just that
    same math over every match instead of a separate, LLM-judged figure."""
    essentials = [m for m in matches if m.essential]
    preferred = [m for m in matches if not m.essential]
    essential_ratio = (sum(1 for m in essentials if m.matched) / len(essentials)) if essentials else 1.0
    preferred_ratio = (sum(1 for m in preferred if m.matched) / len(preferred)) if preferred else 1.0
    return round((0.75 * essential_ratio + 0.25 * preferred_ratio) * 100, 1)


def evaluate_candidate(candidate: Candidate, jd: JobDescription) -> CandidateEvaluation:
    """Score one candidate against one job description, with evidence."""
    requirements = "\n".join(
        [f"- (essential) {r}" for r in jd.essential_requirements]
        + [f"- (preferred) {r}" for r in jd.preferred_requirements]
    )
    result = _model.with_structured_output(_EvaluationOutput).invoke(
        f"Job: {jd.title}\n\nRequirements:\n{requirements}\n\n"
        f"Candidate resume (raw text):\n{candidate.raw_text}\n\n"
        "For every requirement above, decide if this candidate meets it. Quote "
        "or closely paraphrase the resume text that supports your decision. "
        "Recognize transferable skills and different terminology for the same "
        "thing (e.g. 'Django' counts toward 'backend web framework experience'), "
        "and mark those matches transferable=true with a note explaining why. "
        "Classify each requirement's category as experience, skills, education, "
        "or certifications. Separately, list any missing information that makes "
        "this harder to judge, and any internal inconsistencies in the resume itself."
    )
    matches = [
        EvidenceMatch(
            requirement=m.requirement,
            essential=m.essential,
            matched=m.matched,
            evidence=m.evidence,
            transferable=m.transferable,
            note=m.note,
            category=m.category,
        )
        for m in result.matches
    ]
    return CandidateEvaluation(
        candidate=candidate,
        job_title=jd.title,
        score=_coverage_score(matches),
        matches=matches,
        missing_info=result.missing_info,
        inconsistencies=result.inconsistencies,
    )


def score_for_categories(evaluation: CandidateEvaluation, categories: set[str] | None) -> float:
    """0-100 fit score using only the requirements tagged with one of
    `categories` (e.g. {"experience"}). None/empty means every category -
    the same math `evaluation.score` already used, no re-evaluation needed
    since this just re-weights the evidence the LLM already produced."""
    matches = evaluation.matches
    if categories:
        matches = [m for m in matches if m.category in categories]
        if not matches:
            return 0.0
    return _coverage_score(matches)


def rank_candidates(
    evaluations: list[CandidateEvaluation],
    tie_margin: float = 3.0,
    categories: set[str] | None = None,
) -> list[CandidateEvaluation]:
    """Sort best-first, optionally re-weighted toward just `categories` (e.g.
    {"experience", "education"}) instead of every requirement. Candidates
    within `tie_margin` points of the next one are flagged as tied, for a
    recruiter to differentiate - not silently broken by us."""
    ranked = sorted(evaluations, key=lambda e: score_for_categories(e, categories), reverse=True)
    for i, evaluation in enumerate(ranked):
        this_score = score_for_categories(evaluation, categories)
        evaluation.tied_with_next = i + 1 < len(ranked) and abs(
            this_score - score_for_categories(ranked[i + 1], categories)
        ) <= tie_margin
    return ranked

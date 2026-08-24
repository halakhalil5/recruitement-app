"""A second look at our own evaluation, checking for bias.

`extract.py` already keeps irrelevant personal information (age, gender,
marital status, nationality, photos) out of the `Candidate` model in the
first place. This module is the second layer: it re-reads the evaluation's
own reasoning for proxies that can smuggle bias back in - graduation year as
an age proxy, a name or pronoun slipping into a note, alma mater prestige
substituting for an actual skill check, and so on. It flags; it does not
silently correct - a human decides what to do with a flag.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .llm import get_model
from .models import CandidateEvaluation

_model = get_model()


class _BiasCheck(BaseModel):
    flags: list[str] = Field(
        default_factory=list,
        description=(
            "each a short, specific description of a potentially biased criterion "
            "or proxy found in the evaluation reasoning; empty if none found"
        ),
    )


def check_bias(evaluation: CandidateEvaluation) -> list[str]:
    """Re-read one evaluation's reasoning for protected-attribute proxies."""
    reasoning = "\n".join(f"- {m.requirement}: {m.note or m.evidence}" for m in evaluation.matches)
    result = _model.with_structured_output(_BiasCheck).invoke(
        "Review this candidate evaluation's reasoning for bias: language that "
        "leans on age (e.g. graduation year, 'digital native'), gender, name "
        "origin, nationality, marital/family status, school prestige used as a "
        "proxy instead of an actual skill check, or any other factor irrelevant "
        "to job performance. Flag anything that qualifies, however subtle. If "
        "nothing qualifies, return an empty list - do not invent flags.\n\n"
        f"Job: {evaluation.job_title}\n\nEvaluation reasoning:\n{reasoning}"
    )
    return result.flags


def apply_bias_check(evaluation: CandidateEvaluation) -> CandidateEvaluation:
    """Run `check_bias` and attach the flags to the evaluation in place."""
    evaluation.bias_flags = check_bias(evaluation)
    return evaluation

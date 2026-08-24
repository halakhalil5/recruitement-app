"""Text -> structured data, one LLM call each.

Two things worth noticing:

- The extraction schemas below have no field for age, gender, marital
  status, nationality, or a photo. That is deliberate: irrelevant personal
  information is left out at the source, not filtered out afterwards.
- The result is a plain `Candidate`/`JobDescription` dataclass. Everything
  downstream (matching, questions, bias checks) works on those, not on Drive
  or the LLM directly, which is what makes it easy to test against a local
  text file instead of a live Drive folder.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .llm import get_model
from .models import Candidate, JobDescription

_model = get_model()


class _ExtractedCandidate(BaseModel):
    """Job-relevant facts pulled from a resume."""

    name: str
    email: str | None = None
    phone: str | None = None
    education: list[str] = Field(
        default_factory=list, description="one entry per degree: field, institution, year"
    )
    experience: list[str] = Field(
        default_factory=list,
        description="one entry per role: title, employer, dates, key responsibilities/achievements",
    )
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class _ExtractedJobDescription(BaseModel):
    title: str
    essential_requirements: list[str] = Field(description="must-have requirements, one per item")
    preferred_requirements: list[str] = Field(
        default_factory=list, description="nice-to-have requirements, one per item"
    )


def extract_candidate(text: str, source_file: str, modified_time: str | None = None) -> Candidate:
    """One resume's text -> a structured `Candidate`."""
    extracted = _model.with_structured_output(_ExtractedCandidate).invoke(
        "Extract this candidate's job-relevant facts from their resume. Do not "
        "infer or record age, gender, marital status, nationality, religion, or "
        "anything from a photo - it is irrelevant to job performance and must "
        f"not appear in your output.\n\nRESUME:\n{text}"
    )
    return Candidate(
        source_file=source_file,
        raw_text=text,
        modified_time=modified_time,
        **extracted.model_dump(),
    )


def extract_job_description(
    text: str, source_file: str | None = None, modified_time: str | None = None
) -> JobDescription:
    """A job posting's text -> a structured `JobDescription`."""
    extracted = _model.with_structured_output(_ExtractedJobDescription).invoke(
        "Extract this job description's requirements, split into essential "
        "(must-have) and preferred (nice-to-have). Keep each requirement short "
        f"and concrete, one skill/qualification per item.\n\nJOB DESCRIPTION:\n{text}"
    )
    return JobDescription(
        source_file=source_file,
        raw_text=text,
        modified_time=modified_time,
        **extracted.model_dump(),
    )

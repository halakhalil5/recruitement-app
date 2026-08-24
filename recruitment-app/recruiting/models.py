"""Plain data holders for what the recruiting package works with.

These are dataclasses on purpose, same reasoning as `guc_cms/models.py`: no
logic, easy to print, one `dataclasses.asdict` away from JSON for a UI or a
tool result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Candidate:
    """Structured, job-relevant facts pulled from one resume.

    Deliberately has no field for age, gender, marital status, nationality,
    or a photo - see `extract.py` for why that is left out at the source.
    """

    name: str
    source_file: str
    raw_text: str
    email: str | None = None
    phone: str | None = None
    education: list[str] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    modified_time: str | None = None  # Drive modifiedTime, for incremental re-extraction


@dataclass
class JobDescription:
    """Essential vs. preferred requirements pulled from one job posting."""

    title: str
    raw_text: str
    essential_requirements: list[str] = field(default_factory=list)
    preferred_requirements: list[str] = field(default_factory=list)
    source_file: str | None = None
    modified_time: str | None = None


@dataclass
class EvidenceMatch:
    """One requirement, and whether/why this candidate meets it."""

    requirement: str
    essential: bool
    matched: bool
    evidence: str  # quote/paraphrase from the resume; "" if not matched
    transferable: bool  # matched via a related skill/different terminology, not literally
    note: str  # one line of reasoning
    category: str = "skills"  # "experience" | "skills" | "education" | "certifications"


@dataclass
class CandidateEvaluation:
    """One candidate scored against one job description, with evidence."""

    candidate: Candidate
    job_title: str
    score: float  # 0-100
    matches: list[EvidenceMatch]
    missing_info: list[str] = field(default_factory=list)
    inconsistencies: list[str] = field(default_factory=list)
    bias_flags: list[str] = field(default_factory=list)
    tied_with_next: bool = False  # set by rank_candidates

    def essential_coverage(self) -> tuple[int, int]:
        """(essential requirements met, essential requirements total)."""
        essentials = [m for m in self.matches if m.essential]
        return sum(1 for m in essentials if m.matched), len(essentials)


@dataclass
class InterviewQuestion:
    """One question, and why it is worth asking this specific candidate."""

    question: str
    rationale: str
    targets: str  # the requirement or gap this question probes


@dataclass
class TimeSlot:
    """One open interview slot."""

    start: datetime
    end: datetime

    def __str__(self) -> str:
        return f"{self.start:%a %b %d, %H:%M} - {self.end:%H:%M} UTC"

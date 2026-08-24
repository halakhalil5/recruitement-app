"""Portal grades and transcript, wrapped as LangChain tools.

Import what you need:

    from portal_tools import (list_my_terms, list_courses_in_term, get_my_grades,
                               list_transcript_years, get_my_transcript)

Logging in to the portal happens once, the first time this module is imported.
"""

import getpass
import os

from dotenv import load_dotenv
from langchain.tools import tool

from guc_portal import GucPortal

load_dotenv()  # GUC_USERNAME / GUC_PASSWORD from .env, if present
if not os.environ.get("GUC_USERNAME"):
    os.environ["GUC_USERNAME"] = input("GUC username: ")
if not os.environ.get("GUC_PASSWORD"):
    os.environ["GUC_PASSWORD"] = getpass.getpass("GUC password: ")

portal = GucPortal()  # site defaults to "guc" (set GUC_SITE=giu to switch)
print("logged in to the portal")

_cache = {}


def _seasons():
    if "seasons" not in _cache:
        _cache["seasons"] = portal.available_seasons()  # [(value, label), ...]
    return _cache["seasons"]


def _years():
    if "years" not in _cache:
        _cache["years"] = portal.available_years()      # [(value, label), ...]
    return _cache["years"]


@tool
def list_my_terms() -> list[str]:
    """List the terms the student has grades for, e.g. 'Winter 2024'."""
    return [label for _v, label in _seasons()]


@tool
def list_courses_in_term(term: str) -> list[str]:
    """List the courses taught in a past term, e.g. 'Winter 2024'.
    Use this to find a course's exact name before asking for its grades."""
    value = next((v for v, label in _seasons() if term.lower() in label.lower()), None)
    if not value:
        return [f"no term matches {term!r}"]
    return [label for _v, label in portal.list_previous_courses(value)]


@tool
def get_my_grades(term: str, course: str) -> dict:
    """Detailed marks for one course in one term: each quiz/assignment (earned / max)
    plus the percentage of every course that term.
    `term` like 'Winter 2024', `course` like 'Discrete Math' or 'MATH501'."""
    key = ("grades", term.lower(), course.lower())
    if key not in _cache:
        g = portal.get_grades_by_name(term, course)
        _cache[key] = {
            "course": g.course,
            "term": g.season,
            "items": [{"what": i.assessment, "grade": i.grade} for i in g.items],
            "course_percentages": g.percentages,
        }
    return _cache[key]


@tool
def list_transcript_years() -> list[str]:
    """List the academic years on the transcript, e.g. '2024-2025'."""
    return [label for _v, label in _years()]


@tool
def get_my_transcript(year: str) -> dict:
    """The transcript for one academic year: each course with its letter grade,
    and the cumulative GPA. `year` is a label like '2024-2025'."""
    value = next((v for v, label in _years() if year in label), None)
    if not value:
        return {"error": f"no year matches {year!r}; options: {[l for _v, l in _years()]}"}
    key = ("tx", value)
    if key not in _cache:
        t = portal.get_transcript_year(value)
        _cache[key] = {
            "year": year,
            "cumulative_gpa": t.cumulative_gpa,
            "courses": [
                {"course": r.course, "grade": r.grade, "semester": r.semester} for r in t.rows
            ],
        }
    return _cache[key]

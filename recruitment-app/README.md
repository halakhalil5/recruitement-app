# Recruitment app: resumes and a JD into a ranked, explained shortlist

An intelligent recruitment support system: it screens resumes against a job
description, ranks candidates with evidence for every score, recognizes
transferable skills and different terminology, flags missing information
and inconsistencies, generates personalized interview questions, proposes
(and, only on confirmation, books) interview times, and checks its own
reasoning for bias.

The work is in four small notebooks that teach one idea each, plus a
combined agent, plus a click-through UI:

| Notebook | The move | The agent/app can... |
|---|---|---|
| `00-recruitment-basics.ipynb` | connect to **Drive**, list files | find the current JD and resumes |
| `01-structured-extraction.ipynb` | text -> **structured** `Candidate`/`JobDescription` | compare on fields, not paragraphs |
| `02-candidate-comparison.ipynb` | score against requirements **with evidence** | rank candidates and show why |
| `03-questions-and-bias.ipynb` | generate **interview questions**, check for **bias** | prep for interviews, catch bad reasoning |
| `04-recruiter-agent-and-scheduling.ipynb` | **combine** everything, propose/book interviews | one agent, human-in-the-loop scheduling |

They sit on one small package that knows nothing about agents:

- `recruiting/` : Drive + Calendar clients, extraction, matching, interview
  questions, bias checks - all plain functions and dataclasses.

`recruiter_app.py` is the same package again, as a Streamlit UI instead of a
notebook or a chat.

## Why the schema leaves things out

`recruiting/extract.py`'s resume schema has no field for age, gender,
marital status, nationality, or a photo. That is deliberate: irrelevant
personal information is designed out at extraction time, not filtered out
after the fact. `recruiting/bias.py` is a second layer on top of that: it
re-reads the evaluation's own *reasoning* for proxies that can smuggle bias
back in (graduation year as an age proxy, school prestige standing in for a
skill check, and so on) and flags them for a human to look at.

## Why booking is two tools, not one

`CalendarClient.find_free_slots` only reads calendars. `CalendarClient.create_event`
writes to one, and nothing in this app calls it except in direct response to
a human confirming a specific slot - a button click in the UI, or an
explicit follow-up message to the agent in notebook 04. Proposing and
booking are separate on purpose, so "review important actions before they
are executed" is structural, not just a prompt asking nicely.

## Setup

```bash
uv sync                                # make the venv, install everything (uses Python 3.12)
cp .env.example .env                   # then paste your LITELLM_API_KEY into .env (iHQ LiteLLM proxy, see recruiting/llm.py)
uv run jupyter lab                     # open the notebooks
uv run streamlit run recruiter_app.py  # or open the UI
```

Notebooks 01-04 and the UI work out of the box against the synthetic resumes
and JD in `sample_data/` - no Google setup needed to try the matching,
questions, or bias check. Notebook 00 and live Drive/Calendar use need the
Google OAuth setup below.

### Google OAuth (Drive + Calendar), if you want the live version

1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project (or reuse one), then enable the **Google Drive API** and the
   **Google Calendar API**.
2. Under *APIs & Services > Credentials*, create an **OAuth client ID** of
   type **Desktop app**. Download it and save it as `credentials.json` in
   this folder.
3. Put your resumes in one Drive folder and your JD in another (or the same
   one - just point both env vars at it). Copy each folder's id from its
   URL (`.../folders/<this-part>`) into `.env`:
   `GOOGLE_DRIVE_RESUMES_FOLDER_ID`, `GOOGLE_DRIVE_JD_FOLDER_ID`.
4. The first time `DriveClient()` or `CalendarClient()` runs, a browser
   opens for you to sign in and grant access. After that, a cached
   `token.json` remembers you - never commit either file (both are already
   in `.gitignore`).
5. For scheduling, set `GOOGLE_CALENDAR_ID` (usually `primary`) and
   `INTERVIEWER_EMAILS` in `.env`.

## The package in one screen

```python
from recruiting import (
    DriveClient, extract_candidate, extract_job_description,
    evaluate_candidate, rank_candidates, generate_questions,
    apply_bias_check, CalendarClient,
)

drive = DriveClient()
jd_file = drive.latest(jd_folder_id)                       # the current JD
jd = extract_job_description(drive.fetch_text(jd_file))

resumes = drive.list_files(resumes_folder_id)
candidates = [extract_candidate(drive.fetch_text(f), source_file=f.name) for f in resumes]

evaluations = rank_candidates([evaluate_candidate(c, jd) for c in candidates])
top = evaluations[0]
top.matches           # per-requirement evidence, transferable-skill notes
top.missing_info       # what the resume didn't say
top.inconsistencies    # what didn't add up
apply_bias_check(top)  # re-reads the reasoning above for bias, flags it

questions = generate_questions(top)   # personalized to this candidate's gaps

cal = CalendarClient(calendar_id="primary")
slots = cal.find_free_slots(["interviewer@example.com"])   # read-only
cal.create_event("Interview: " + top.candidate.name, slots[0], ["interviewer@example.com"])  # only after a human picks one
```

## Handling the live-demo curveballs

- **A JD requirement changes, or a candidate submits a new resume**:
  `DriveClient.latest()` and `.list_files()` always re-read the folder, so
  the next `_refresh()` (UI "Refresh" button, or the agent's
  `list_candidates` tool) picks it up. Nothing is hard-cached beyond "does
  this resume's text still match what I last saw".
- **An interviewer becomes unavailable**: `find_free_slots` reads live
  free/busy data across every attendee, so their busy time is already
  excluded.
- **Two candidates have similar qualifications**: `rank_candidates` flags
  `tied_with_next` instead of silently breaking the tie.
- **The system detects potentially biased evaluation criteria**:
  `apply_bias_check` / `check_bias` re-reads the evaluation's reasoning and
  flags it - see notebook `03` for a worked example of it catching one.
- **A recruiter disputes the evaluation**: the UI's "Flag as disputed"
  button records that, visibly, next to the candidate - the system does not
  overwrite or hide a human's disagreement with it.

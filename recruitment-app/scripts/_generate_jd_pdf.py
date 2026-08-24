"""One-off script: renders a polished job-description PDF for sample_data/.

Not part of the app - `fpdf2` is a scratch tool for generating this asset,
not a project dependency. Run with:

    uv run --with fpdf2 python scripts/_generate_jd_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

TEAL = (47, 72, 88)  # matches the app's FB_PRIMARY accent
MUTED = (107, 114, 128)
TEXT = (31, 41, 55)
BORDER = (229, 233, 238)

OUT_PATH = Path(__file__).parent.parent / "sample_data" / "job_description.pdf"

ESSENTIAL = [
    "3+ years of professional software engineering experience building production backend systems",
    "Strong proficiency in Python, with hands-on experience in Django, Flask, or FastAPI",
    "Experience designing, building, and consuming REST APIs",
    "Solid experience with relational databases (PostgreSQL or MySQL), including schema design "
    "and query optimization",
    "Bachelor's degree in Computer Science, Software Engineering, or a related field "
    "(or equivalent practical experience)",
    "Comfortable working in a fast-paced team with regular code review and on-call rotation",
]

PREFERRED = [
    "Experience with Docker and containerized deployments",
    "Familiarity with a major cloud platform (AWS, GCP, or Azure)",
    "Experience with asynchronous task queues such as Celery or RQ",
    "Prior experience mentoring or leading junior engineers",
    "Exposure to CI/CD pipelines and infrastructure-as-code",
    "A relevant certification (e.g. AWS Certified Developer) or active open-source contributions",
]

RESPONSIBILITIES = [
    "Design and ship REST APIs that power our mobile and web clients",
    "Own the schema, performance, and reliability of our core PostgreSQL database",
    "Partner with product and frontend engineers to scope and deliver new features",
    "Participate in code review and a shared on-call rotation",
    "Improve observability - logging, metrics, and alerting - for the services you own",
    "Mentor junior engineers as the team grows",
]

BENEFITS = [
    "Competitive salary and equity",
    "Hybrid work model (Cairo office, 2 days/week on-site)",
    "Full health insurance for you and your dependents",
    "Annual learning and conference budget",
    "25 days of paid annual leave",
]


class JDPdf(FPDF):
    def header(self) -> None:
        pass

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 10, f"NovaLedger Technologies - Page {self.page_no()}", align="C")


def section_title(pdf: JDPdf, text: str) -> None:
    if pdf.will_page_break(20):  # keep a header from stranding alone at page bottom
        pdf.add_page()
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*TEAL)
    pdf.cell(0, 8, text.upper(), new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y()
    pdf.set_draw_color(*TEAL)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, y, pdf.l_margin + 30, y)
    pdf.ln(3)


def bullet_list(pdf: JDPdf, items: list[str]) -> None:
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_text_color(*TEXT)
    for item in items:
        # estimate wrapped height first so the dot and its text never split
        # across a page break - fpdf2 would otherwise happily draw the dot
        # at the bottom of one page and push the text to the next.
        n_lines = len(pdf.multi_cell(0, 5.6, item, dry_run=True, output="LINES"))
        if pdf.will_page_break(n_lines * 5.6 + 1.2):
            pdf.add_page()
        x = pdf.get_x()
        y = pdf.get_y()
        pdf.set_fill_color(*TEAL)
        pdf.ellipse(x + 1, y + 2.6, 1.6, 1.6, style="F")
        pdf.set_x(x + 6)
        pdf.multi_cell(0, 5.6, item, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.2)


def build() -> None:
    pdf = JDPdf(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_margins(18, 16, 18)
    pdf.add_page()

    # -- masthead --------------------------------------------------------
    pdf.set_fill_color(*TEAL)
    pdf.rect(0, 0, pdf.w, 34, style="F")
    pdf.set_xy(18, 9)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, "Backend Software Engineer", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, "NovaLedger Technologies  |  Cairo, Egypt (Hybrid)  |  Full-time")
    pdf.set_y(40)

    # -- about the company -------------------------------------------------
    section_title(pdf, "About NovaLedger")
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_text_color(*TEXT)
    pdf.multi_cell(
        0,
        5.6,
        "NovaLedger Technologies builds the payments infrastructure behind checkout and payouts "
        "for over 400 merchants across the region. Our backend team owns everything from the "
        "public API to the ledger that reconciles every transaction - correctness and reliability "
        "are not optional here.",
    )

    # -- about the role ---------------------------------------------------
    section_title(pdf, "About the Role")
    pdf.set_font("Helvetica", "", 10.5)
    pdf.multi_cell(
        0,
        5.6,
        "We're hiring a Backend Software Engineer to help design and scale the core services "
        "behind our payments platform. You'll design APIs, own data models end to end, and work "
        "closely with product and frontend engineers to ship features that merchants rely on daily.",
    )

    # -- responsibilities --------------------------------------------------
    section_title(pdf, "What You'll Do")
    bullet_list(pdf, RESPONSIBILITIES)

    # -- requirements --------------------------------------------------
    section_title(pdf, "Requirements (Essential)")
    bullet_list(pdf, ESSENTIAL)

    section_title(pdf, "Nice to Have (Preferred)")
    bullet_list(pdf, PREFERRED)

    # -- what we offer --------------------------------------------------
    section_title(pdf, "What We Offer")
    bullet_list(pdf, BENEFITS)

    # -- how to apply --------------------------------------------------
    section_title(pdf, "How to Apply")
    pdf.set_font("Helvetica", "", 10.5)
    pdf.multi_cell(
        0,
        5.6,
        "Send your resume to careers@novaledger.example with the subject line "
        "\"Backend Software Engineer\". We review applications on a rolling basis.",
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_PATH))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    build()

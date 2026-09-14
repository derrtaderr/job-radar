"""End-to-end drafting chain: compile the two stock example fixtures, verify
each PDF against the registry's own page limits and contact literals, then
run ats_report against a synthetic JD and confirm it both hard-passes and
picks up real keyword hits. This is the spec's Phase 2 done-condition,
automated — the LLM drafting step itself is exercised by /apply in real use;
what this proves is that the deterministic chain around it (compile → verify
→ ats_report) actually holds together end to end, against the real registry
and real typst, not against literals typed from memory that could drift out
of sync with templates/registry.yaml.

Skipped when typst isn't on PATH, matching tests/test_compile.py's pattern.
"""
import shutil
from pathlib import Path

import pytest

from engine.draft.compile import compile_pdf
from engine.draft.registry import load_registry
from tools.ats_check import ats_report
from tools.verify_pdf import verify

pytestmark_no_typst = pytest.mark.skipif(
    shutil.which("typst") is None, reason="typst binary not installed")

REPO_ROOT = Path(__file__).parent.parent
RESUME_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "resume_example.typ"
COVER_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "cover_example.typ"

PERSONA_EMAIL = "alex.rivera@example.com"
PERSONA_PHONE = "(303) 555-0142"

# Synthetic ~40-line data-engineer posting. Fictional company; a salary band;
# and real tech keywords the resume fixture actually contains (Python,
# Airflow, dbt, Snowflake), each repeated so jd_keywords' >=2-occurrence
# floor picks every one of them up.
SYNTHETIC_JD = """
Senior Data Engineer — Cascadia Freight Analytics

Cascadia Freight Analytics builds the data platform that mid-market logistics
carriers use to price freight and forecast capacity. We're hiring a Senior
Data Engineer to own the pipelines that feed our pricing models.

Compensation: $145,000 - $175,000 base, plus equity and full benefits.
Location: Remote (US).

What you'll do:
- Design and operate the batch and streaming pipelines that move raw carrier
  telemetry into our warehouse. Python is our primary language for pipeline
  code, and you'll be writing Python daily.
- Own our Airflow deployment end to end — DAG design, scheduling, and
  on-call for pipeline failures. Prior Airflow experience running production
  DAGs is required.
- Build and maintain dbt models that transform raw tables into the marts our
  pricing team queries. You should already be comfortable writing dbt tests
  and documenting dbt models for other engineers.
- Manage our Snowflake warehouse, including query performance tuning and
  cost control. Snowflake experience at scale is a must for this role.
- Partner with the pricing and product teams to instrument new data sources
  as we expand into new freight lanes.

What we're looking for:
- 5+ years of experience as a data engineer, with production Python and
  Airflow experience.
- Hands-on dbt modeling experience, plus a working knowledge of Snowflake
  performance tuning.
- Experience with Kafka or another streaming platform is a plus.
- Strong communication skills — you'll work directly with the pricing team,
  not just other engineers.
- A track record of owning a data platform in production, not just building
  it and handing it off.

Cascadia Freight Analytics is a fully remote company. We offer competitive
salary, equity, and full health benefits.
""".strip()


@pytestmark_no_typst
def test_full_drafting_chain_compiles_verifies_and_ats_checks(tmp_path):
    registry = load_registry(REPO_ROOT)
    resume_limit = registry.default("resume").page_limit
    cover_limit = registry.default("cover").page_limit

    resume_pdf = tmp_path / "resume.pdf"
    cover_pdf = tmp_path / "cover.pdf"

    resume_ok, resume_log = compile_pdf(RESUME_FIXTURE, out=resume_pdf)
    assert resume_ok, resume_log

    cover_ok, cover_log = compile_pdf(COVER_FIXTURE, out=cover_pdf)
    assert cover_ok, cover_log

    resume_violations = verify(resume_pdf, resume_limit, [PERSONA_EMAIL])
    assert resume_violations == []

    cover_violations = verify(cover_pdf, cover_limit, ["Sincerely"])
    assert cover_violations == []

    hard_ok, report = ats_report(
        resume_pdf, SYNTHETIC_JD,
        {"email": PERSONA_EMAIL, "phone": PERSONA_PHONE})

    assert hard_ok is True, report

    # Read hits directly out of the report rather than re-deriving them, so
    # this test exercises ats_report's own output, not a parallel
    # reimplementation of its coverage logic.
    hits_line = next(line for line in report.splitlines()
                      if line.startswith("Hits ("))
    reported_hits = [h.strip() for h in
                      hits_line.split(":", 1)[1].split(",") if h.strip()
                      and h.strip() != "none"]

    assert len(reported_hits) >= 3
    for keyword in ("python", "airflow", "dbt", "snowflake"):
        assert keyword in reported_hits

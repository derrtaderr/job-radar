"""Twelve canned, JobSpy-shaped postings for `tools/demo.py` — the offline
walk of the radar half of the system against `config.example`'s fictional
persona (a data/platform engineer targeting remote or Denver-metro roles,
comp floor $120K, title tiers favoring "data platform engineer").

Every company, title, and posting body here is invented, drawn from the same
fictional vocabulary `tests/fixtures_season.py` already uses (Cobalt Grid,
Larkspur Grid, Tessellate, and so on) so the demo reads as one consistent
fictional world rather than a second invented cast.

Shaped so `config.example`'s rules produce exactly seven survivors and five
kills, one kill per distinct flag, so the demo's queue.md shows the kill
list's breadth rather than five instances of the same rule:

    bdr-scope               — quota language in the JD body
    not-ic                  — "manage a team" / "direct reports" in the body
    legacy-stack            — "SSRS is the core..." in the body
    comp-below-floor-stated — a body-stated salary max under the $120K floor
    location                — non-remote, structured location outside the
                               commute_locations pattern (Denver|Boulder)

Every row not listed as a kill is deliberately clean of all five triggers —
no quota/manage/SSRS/low-salary language, and either remote or inside the
commute pattern — so a survivor never accidentally kills itself on a second
rule the demo wasn't trying to demonstrate.
"""
from __future__ import annotations

# --- survivors (7) ----------------------------------------------------------

_SURVIVORS = [
    {
        "id": "demo-1", "title": "Senior Data Platform Engineer",
        "company": "Cobalt Grid",
        "description": (
            "Cobalt Grid is hiring a Senior Data Platform Engineer to own the "
            "ingestion layer that feeds our reporting marts. You'll design "
            "and operate the pipelines analysts and finance query daily, "
            "working with Python, Airflow, and Snowflake."
        ),
        "location": "", "is_remote": True,
        "min_amount": 165000, "max_amount": 195000, "interval": "yearly",
        "date_posted": "2026-09-11",
        "job_url": "https://example.com/jobs/demo-1",
    },
    {
        "id": "demo-2", "title": "Data Engineer",
        "company": "Larkspur Grid",
        "description": (
            "Larkspur Grid is looking for a Data Engineer to build and "
            "maintain the dbt models our product team relies on. Fully "
            "remote, open to candidates anywhere in the United States."
        ),
        "location": "", "is_remote": True,
        "min_amount": 130000, "max_amount": 150000, "interval": "yearly",
        "date_posted": "2026-09-08",
        "job_url": "https://example.com/jobs/demo-2",
    },
    {
        "id": "demo-3", "title": "Analytics Engineer",
        "company": "Meridian Analytics",
        "description": (
            "Meridian Analytics is hiring an Analytics Engineer to model "
            "the warehouse tables the growth team queries every day. "
            "Remote-friendly, small team, high ownership."
        ),
        "location": "", "is_remote": True,
        "min_amount": None, "max_amount": None, "interval": "yearly",
        "date_posted": "2026-09-09",
        "job_url": "https://example.com/jobs/demo-3",
    },
    {
        "id": "demo-4", "title": "Senior Data Engineer",
        "company": "Tessellate",
        "description": (
            "Tessellate is hiring a Senior Data Engineer to join our small "
            "data team in Denver. This is an in-office role based out of "
            "our Denver headquarters."
        ),
        "location": "Denver, CO", "is_remote": False,
        "min_amount": 145000, "max_amount": 170000, "interval": "yearly",
        "date_posted": "2026-09-07",
        "job_url": "https://example.com/jobs/demo-4",
    },
    {
        "id": "demo-5", "title": "Data Platform Engineer",
        "company": "Pinecrest Software",
        "description": (
            "Pinecrest Software is hiring a Data Platform Engineer to own "
            "our streaming architecture. Fully remote position, open to "
            "candidates across the US."
        ),
        "location": "", "is_remote": True,
        "min_amount": None, "max_amount": None, "interval": "yearly",
        "date_posted": "2026-08-30",
        "job_url": "https://example.com/jobs/demo-5",
    },
    {
        "id": "demo-6", "title": "Senior Pipeline Engineer",
        "company": "Kestrel Dynamics",
        "description": (
            "Kestrel Dynamics is hiring a Senior Pipeline Engineer to build "
            "the ingestion pipeline for our forecasting product. Remote "
            "role, work from anywhere in the US."
        ),
        "location": "", "is_remote": True,
        "min_amount": 140000, "max_amount": 160000, "interval": "yearly",
        "date_posted": "2026-09-12",
        "job_url": "https://example.com/jobs/demo-6",
    },
    {
        "id": "demo-7", "title": "Analytics Engineer",
        "company": "Cindermill Tech",
        "description": (
            "Cindermill Tech is hiring an Analytics Engineer to partner "
            "with the pricing team on the metrics layer. This is a fully "
            "remote role, open to candidates anywhere in the United States."
        ),
        "location": "", "is_remote": True,
        "min_amount": 175000, "max_amount": 190000, "interval": "yearly",
        "date_posted": "2026-09-10",
        "job_url": "https://example.com/jobs/demo-7",
    },
]

# --- kills (5), one per flag -------------------------------------------------

_KILLS = [
    {
        "id": "demo-8", "title": "Data Platform Engineer",
        "company": "Bellweather Labs",
        "description": (
            "Bellweather Labs is hiring for a data-adjacent revenue role. "
            "You will carry a quota of 20 qualified meetings a month and "
            "make outbound calls to prospective accounts."
        ),
        "location": "", "is_remote": True,
        "min_amount": 130000, "max_amount": 150000, "interval": "yearly",
        "date_posted": "2026-09-09",
        "job_url": "https://example.com/jobs/demo-8",
    },  # bdr-scope
    {
        "id": "demo-9", "title": "Senior Data Engineer",
        "company": "Thornwood Data",
        "description": (
            "Thornwood Data is hiring a Senior Data Engineer who will hire "
            "and manage a team of five engineers with direct reports, "
            "owning the platform roadmap."
        ),
        "location": "", "is_remote": True,
        "min_amount": 160000, "max_amount": 185000, "interval": "yearly",
        "date_posted": "2026-09-06",
        "job_url": "https://example.com/jobs/demo-9",
    },  # not-ic
    {
        "id": "demo-10", "title": "Data Platform Engineer",
        "company": "Fernmark Systems",
        "description": (
            "Fernmark Systems is hiring a Data Platform Engineer. Our "
            "reporting stack: SSRS is the core reporting tool used across "
            "finance and operations, and you'll extend it."
        ),
        "location": "", "is_remote": True,
        "min_amount": 135000, "max_amount": 155000, "interval": "yearly",
        "date_posted": "2026-09-05",
        "job_url": "https://example.com/jobs/demo-10",
    },  # legacy-stack
    {
        "id": "demo-11", "title": "Data Engineer",
        "company": "Aldgate Partners",
        "description": (
            "Aldgate Partners is hiring a Data Engineer to support our "
            "reporting team. Compensation: the base salary range for this "
            "role is $95,000 to $110,000 per year, fully remote."
        ),
        "location": "", "is_remote": True,
        "min_amount": None, "max_amount": None, "interval": "yearly",
        "date_posted": "2026-09-04",
        "job_url": "https://example.com/jobs/demo-11",
    },  # comp-below-floor-stated
    {
        "id": "demo-12", "title": "Analytics Engineer",
        "company": "Quill and Sparrow",
        "description": (
            "Quill and Sparrow is hiring an Analytics Engineer to join our "
            "Chicago team, working from our office alongside the rest of "
            "the analytics group."
        ),
        "location": "Chicago, IL", "is_remote": False,
        "min_amount": 140000, "max_amount": 165000, "interval": "yearly",
        "date_posted": "2026-09-03",
        "job_url": "https://example.com/jobs/demo-12",
    },  # location
]

DEMO_ROWS = _SURVIVORS + _KILLS

# Names pinned for tests, so a future edit to the rows above has to keep the
# same shape (7 survivors, one kill per flag) or update the pin deliberately.
EXPECTED_SURVIVOR_COUNT = len(_SURVIVORS)
EXPECTED_KILL_COUNT = len(_KILLS)
EXPECTED_KILL_FLAGS = (
    "bdr-scope", "not-ic", "legacy-stack", "comp-below-floor-stated",
    "location",
)

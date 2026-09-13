def make_row(**overrides):
    row = {"id": "j1", "title": "Data Platform Engineer", "company": "Northwind Analytics",
           "description": "Build and own our data platform. Fully remote (US).",
           "location": "", "is_remote": True, "min_amount": None, "max_amount": None,
           "interval": "yearly", "date_posted": "2026-09-10",
           "job_url": "https://example.com/j1"}
    row.update(overrides)
    return row

def make_report_row(**overrides):
    """A pipeline OUTPUT row — what the report layer renders. Same shape as a
    scraped row plus the fields the pipeline stamps on (score, jid)."""
    row = {"jid": "j1", "title": "Data Platform Engineer",
           "company": "Northwind Analytics", "location": "Remote, US",
           "min_amount": 150000, "max_amount": 190000, "interval": "yearly",
           "date_posted": "2026-09-11", "job_url": "https://example.com/jobs/view/1",
           "score": 80, "is_remote": True, "description": None}
    row.update(overrides)
    return row


BDR_JD ="You will carry a quota of 30 qualified meetings and make 60 calls per day."
QUOTA_DESIGN_JD = "You will design the quota model and territory plan for the sales org."
MANAGER_JD = "You will hire and manage a team of five engineers with direct reports."
MENTOR_JD = "You will mentor junior engineers and lead architecture reviews."

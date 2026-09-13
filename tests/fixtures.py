def make_row(**overrides):
    row = {"id": "j1", "title": "Data Platform Engineer", "company": "Northwind Analytics",
           "description": "Build and own our data platform. Fully remote (US).",
           "location": "", "is_remote": True, "min_amount": None, "max_amount": None,
           "interval": "yearly", "date_posted": "2026-09-10",
           "job_url": "https://example.com/j1"}
    row.update(overrides)
    return row

BDR_JD = "You will carry a quota of 30 qualified meetings and make 60 calls per day."
QUOTA_DESIGN_JD = "You will design the quota model and territory plan for the sales org."
MANAGER_JD = "You will hire and manage a team of five engineers with direct reports."
MENTOR_JD = "You will mentor junior engineers and lead architecture reviews."

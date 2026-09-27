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
           "min_amount": 140000, "max_amount": 185000, "interval": "yearly",
           "date_posted": "2026-09-11", "job_url": "https://example.com/jobs/view/1",
           "score": 80, "is_remote": True, "description": None}
    row.update(overrides)
    return row


BDR_JD = "You will carry a quota of 30 qualified meetings and make 60 calls per day."
QUOTA_DESIGN_JD = "You will design the quota model and territory plan for the sales org."
MANAGER_JD = "You will hire and manage a team of five engineers with direct reports."
MENTOR_JD = "You will mentor junior engineers and lead architecture reviews."


# --- the live wire shape (row 64 fix wave) -----------------------------------
#
# A live LinkedIn scrape hands back `description` as MARKDOWN, and JobSpy escapes
# its punctuation: "This is a fully on\-site position". Every kill pattern in this
# repo is written against prose, so a fixture written in clean prose proves
# nothing about the text the engine actually receives — the on-site rule returned
# no flags on real data while passing every test in the suite.
#
# So fixtures that exercise a punctuation-bearing pattern are written in the WIRE
# shape and put through the real boundary that cleans it. There is exactly one
# such boundary, `engine/radar/scrape.py::_normalize_frame_rows`, which is the
# only module that knows a description is JobSpy markdown; keeping the unescape
# there is what lets the pipeline stay a pure function over plain text.

class _FakeFrame:
    """Stands in for a pandas DataFrame: iterrows() -> (index, dict-like row)."""

    def __init__(self, rows):
        self._rows = rows

    def iterrows(self):
        for i, row in enumerate(self._rows):
            yield i, _FakeRow(row)


class _FakeRow:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return dict(self._data)


def as_scraped(rows):
    """Put JobSpy-shaped rows through the real scrape-boundary normaliser, so a
    test can be written in the wire shape and still assert on what the rest of
    the engine sees. Returns a list of plain dicts."""
    from engine.radar.scrape import _normalize_frame_rows

    return _normalize_frame_rows([_FakeFrame(list(rows))])


def scraped_row(**overrides):
    """One `make_row`, delivered the way the scraper delivers it."""
    return as_scraped([make_row(**overrides)])[0]

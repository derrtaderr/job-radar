"""The scrape adapter — the one module allowed to import JobSpy and touch the
network. `scrape()` itself needs a live JobSpy call to exercise end to end (that
happens in the one required live run, never in this suite), but the row
normalization it depends on is pure and gets tested directly here, and the
module must import cleanly with JobSpy absent so the rest of the CLI stays
testable without the dependency.
"""
import urllib.error

from engine.radar import scrape as scrape_mod


# --- _normalize_frame_rows ---------------------------------------------------

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


def test_normalizes_nan_like_string_values_to_none():
    frame = _FakeFrame([{"id": "1", "min_amount": float("nan"), "notes": "None"}])
    rows = scrape_mod._normalize_frame_rows([frame])
    assert rows == [{"id": "1", "min_amount": None, "notes": None}]


def test_normalizes_pandas_nat_and_pandas_na_strings():
    frame = _FakeFrame([{"date_posted": "NaT", "salary": "<NA>"}])
    rows = scrape_mod._normalize_frame_rows([frame])
    assert rows == [{"date_posted": None, "salary": None}]


def test_truncates_date_posted_to_ten_characters_when_present():
    frame = _FakeFrame([{"date_posted": "2026-09-10T00:00:00"}])
    rows = scrape_mod._normalize_frame_rows([frame])
    assert rows == [{"date_posted": "2026-09-10"}]


def test_leaves_a_none_date_posted_alone():
    frame = _FakeFrame([{"date_posted": None}])
    rows = scrape_mod._normalize_frame_rows([frame])
    assert rows == [{"date_posted": None}]


def test_skips_none_frames():
    frame = _FakeFrame([{"id": "1"}])
    rows = scrape_mod._normalize_frame_rows([None, frame, None])
    assert rows == [{"id": "1"}]


def test_collects_rows_from_multiple_frames_in_order():
    frame_a = _FakeFrame([{"id": "1"}])
    frame_b = _FakeFrame([{"id": "2"}])
    rows = scrape_mod._normalize_frame_rows([frame_a, frame_b])
    assert rows == [{"id": "1"}, {"id": "2"}]


# --- scrape() imports without JobSpy present --------------------------------

def test_module_imports_without_jobspy_installed():
    # jobspy is imported inside scrape(), never at module scope, so a caller
    # that never runs a real scrape (every test, --dry-run, --check) never
    # needs the dependency on the path at all.
    import inspect

    source = inspect.getsource(scrape_mod)
    assert "import jobspy" not in source.split("def scrape(")[0]


# --- http_fetch ---------------------------------------------------------

class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_http_fetch_returns_status_and_decoded_body(monkeypatch):
    def fake_urlopen(req, timeout=None):
        assert timeout == 15
        assert req.get_header("User-agent")
        return _FakeResponse(200, "hello")

    monkeypatch.setattr(scrape_mod.urllib.request, "urlopen", fake_urlopen)
    assert scrape_mod.http_fetch("https://example.com/j1") == (200, "hello")


def test_http_fetch_respects_a_custom_timeout(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        return _FakeResponse(200, "ok")

    monkeypatch.setattr(scrape_mod.urllib.request, "urlopen", fake_urlopen)
    scrape_mod.http_fetch("https://example.com/j1", timeout=3)
    assert seen["timeout"] == 3


def test_http_fetch_unwraps_httperror_instead_of_raising(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            "https://example.com/j1", 404, "Not Found", {},
            fp=_FakeBody("gone"))

    monkeypatch.setattr(scrape_mod.urllib.request, "urlopen", fake_urlopen)
    assert scrape_mod.http_fetch("https://example.com/j1") == (404, "gone")


class _FakeBody:
    def __init__(self, text):
        self._text = text.encode("utf-8")

    def read(self):
        return self._text

    def close(self):
        pass


def test_http_fetch_lets_other_exceptions_propagate(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise TimeoutError("network unreachable")

    monkeypatch.setattr(scrape_mod.urllib.request, "urlopen", fake_urlopen)
    try:
        scrape_mod.http_fetch("https://example.com/j1")
        assert False, "expected TimeoutError to propagate"
    except TimeoutError:
        pass


# --- scrape() query loop, with jobspy faked out ------------------------------

class _FakeConfig:
    def __init__(self, queries, sites=("linkedin",), search_location="United States",
                 results_per_query=25, hours_old=336):
        self.queries = queries
        self.sites = sites
        self.search_location = search_location
        self.results_per_query = results_per_query
        self.hours_old = hours_old


def test_scrape_calls_jobspy_once_per_query_and_normalizes_rows(monkeypatch):
    calls = []

    def fake_scrape_jobs(**kwargs):
        calls.append(kwargs)
        return _FakeFrame([{"id": kwargs["search_term"], "date_posted": "NaT"}])

    fake_jobspy = _FakeModule(scrape_jobs=fake_scrape_jobs)
    monkeypatch.setitem(scrape_mod.sys.modules, "jobspy", fake_jobspy)

    cfg = _FakeConfig(queries=["Data Engineer", "Analytics Engineer"])
    rows = scrape_mod.scrape(cfg)

    assert [c["search_term"] for c in calls] == ["Data Engineer", "Analytics Engineer"]
    assert calls[0]["site_name"] == ("linkedin",)
    assert calls[0]["location"] == "United States"
    assert calls[0]["results_wanted"] == 25
    assert calls[0]["hours_old"] == 336
    assert calls[0]["linkedin_fetch_description"] is True
    assert rows == [{"id": "Data Engineer", "date_posted": None},
                     {"id": "Analytics Engineer", "date_posted": None}]


def test_scrape_continues_past_a_failed_query(monkeypatch, capsys):
    def fake_scrape_jobs(**kwargs):
        if kwargs["search_term"] == "Data Engineer":
            raise RuntimeError("rate limited")
        return _FakeFrame([{"id": "ok"}])

    fake_jobspy = _FakeModule(scrape_jobs=fake_scrape_jobs)
    monkeypatch.setitem(scrape_mod.sys.modules, "jobspy", fake_jobspy)

    cfg = _FakeConfig(queries=["Data Engineer", "Analytics Engineer"])
    rows = scrape_mod.scrape(cfg)

    out = capsys.readouterr().out
    assert "query 'Data Engineer' failed: rate limited" in out
    assert rows == [{"id": "ok"}]


class _FakeModule:
    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)

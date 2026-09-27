"""`radar.py judge` — the one command that makes a morning's decision durable.

Before this, the human read the top survivors' JDs, decided, and wrote the
decision as prose in a markdown tracker nothing parses. The next run could not
see it, so a req killed by hand came back days later as the top-scored row.

Design notes these tests pin:

- **Company and title are backfilled from `state.json`.** The ledger's
  second matching tier is the normalised (company, title) pair, which is what
  catches a req reissued under a new posting id. A row written by jid alone with
  those columns empty would only ever match tier 1, which is the tier that
  already missed.
- **A jid this machine has never seen is a refusal, not a guess.** With a named
  fix, because the two ways to recover (pass the flags, or check the jid) are
  different mistakes.
"""
import datetime
import shutil
from pathlib import Path

from engine.radar.cli import main
from engine.radar.ledger import load_ledger
from tests.fixtures import make_row

EXAMPLE = Path(__file__).parent.parent / "config.example"
TODAY = str(datetime.date.today())


def _config(tmp_path):
    cfg_dir = tmp_path / "config"
    shutil.copytree(EXAMPLE, cfg_dir)
    # The shipped example ledger is a fictional persona's; a test about writing
    # decisions starts from nothing written.
    (cfg_dir / "decisions.csv").unlink(missing_ok=True)
    return cfg_dir


def _seed_state(cfg_dir, rows):
    """Run the radar once so state.json carries what a judge call reads back."""
    assert main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: rows) == 0


def _rows():
    return [make_row(id="j1", company="Northwind Analytics", title="Data Engineer",
                     job_url="https://example.com/jobs/j1",
                     description="Own the reporting stack. Fully remote (US)."),
            make_row(id="j2", company="Cobalt Grid", title="Data Platform Engineer",
                     job_url="https://example.com/jobs/j2",
                     description="Own the ingestion layer. Fully remote (US).")]


# --- recording a decision -----------------------------------------------------

def test_judging_by_jid_writes_a_row_and_backfills_company_and_title(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    capsys.readouterr()

    code = main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
                 "--config", str(cfg_dir)])

    assert code == 0
    decisions = load_ledger(cfg_dir / "decisions.csv")
    assert len(decisions) == 1
    assert decisions[0].jid == "j1"
    assert decisions[0].company == "Northwind Analytics"
    assert decisions[0].title == "Data Engineer"
    assert decisions[0].verdict == "kill"
    assert decisions[0].reason == "bi-analytics"
    assert decisions[0].date == TODAY


def test_it_says_what_it_recorded_and_where(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    capsys.readouterr()

    main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
          "--config", str(cfg_dir)])
    out = capsys.readouterr().out
    assert "Northwind Analytics" in out
    assert "kill" in out
    assert str(cfg_dir / "decisions.csv") in out


def test_a_draft_verdict_records_the_same_way(tmp_path):
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    assert main(["judge", "j2", "--verdict", "draft", "--reason", "strong-fit",
                 "--config", str(cfg_dir)]) == 0
    assert load_ledger(cfg_dir / "decisions.csv")[0].verdict == "draft"


def test_a_second_decision_appends(tmp_path):
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
          "--config", str(cfg_dir)])
    main(["judge", "j2", "--verdict", "draft", "--reason", "strong-fit",
          "--config", str(cfg_dir)])
    assert [d.jid for d in load_ledger(cfg_dir / "decisions.csv")] == ["j1", "j2"]


def test_company_and_title_can_be_given_directly_with_no_jid(tmp_path):
    # A posting read somewhere other than the queue still deserves a decision.
    cfg_dir = _config(tmp_path)
    assert main(["judge", "--company", "Kestrel Dynamics",
                 "--title", "Senior Pipeline Engineer",
                 "--verdict", "kill", "--reason", "bi-analytics",
                 "--config", str(cfg_dir)]) == 0
    decision = load_ledger(cfg_dir / "decisions.csv")[0]
    assert decision.company == "Kestrel Dynamics"
    assert decision.jid == ""


def test_explicit_flags_win_over_what_state_remembers(tmp_path):
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    main(["judge", "j1", "--company", "Northwind Analytics, Inc.",
          "--verdict", "kill", "--reason", "bi-analytics", "--config", str(cfg_dir)])
    decision = load_ledger(cfg_dir / "decisions.csv")[0]
    assert decision.company == "Northwind Analytics, Inc."
    assert decision.title == "Data Engineer"      # still backfilled


def test_a_url_is_recorded_when_given(tmp_path):
    cfg_dir = _config(tmp_path)
    assert main(["judge", "--company", "Kestrel Dynamics", "--title", "Pipeline Engineer",
                 "--verdict", "kill", "--reason", "bi-analytics",
                 "--url", "https://example.com/jobs/k1",
                 "--config", str(cfg_dir)]) == 0
    assert load_ledger(cfg_dir / "decisions.csv")[0].url == \
        "https://example.com/jobs/k1"


# --- refusals -----------------------------------------------------------------

def test_an_unknown_jid_with_no_flags_refuses_and_names_the_fix(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    code = main(["judge", "never-seen", "--verdict", "kill", "--reason", "x",
                 "--config", str(cfg_dir)])
    out = capsys.readouterr().out
    assert code == 2
    assert "never-seen" in out
    assert "--company" in out and "--title" in out
    assert not (cfg_dir / "decisions.csv").exists()


def test_neither_a_jid_nor_a_company_refuses(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    code = main(["judge", "--verdict", "kill", "--reason", "x",
                 "--config", str(cfg_dir)])
    assert code == 2
    assert "--company" in capsys.readouterr().out


def test_a_missing_config_refuses_the_same_way_a_run_does(tmp_path, capsys):
    code = main(["judge", "j1", "--verdict", "kill", "--reason", "x",
                 "--config", str(tmp_path / "nope")])
    assert code == 2
    assert "config.example" in capsys.readouterr().out


def test_an_unknown_verdict_is_refused(tmp_path):
    import pytest

    cfg_dir = _config(tmp_path)
    # argparse enforces the closed enum and exits 2 itself.
    with pytest.raises(SystemExit) as exc:
        main(["judge", "j1", "--verdict", "maybe", "--reason", "x",
              "--config", str(cfg_dir)])
    assert exc.value.code == 2


# --- end to end ---------------------------------------------------------------

def test_a_judged_posting_comes_back_with_its_verdict_attached(tmp_path, capsys):
    # The whole row, in one test. Judge a posting, then let the board reissue it
    # under a new id with identical content, and read the queue.
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
          "--config", str(cfg_dir)])
    capsys.readouterr()

    reissued = make_row(id="reissued", company="Northwind Analytics",
                        title="Data Engineer",
                        job_url="https://example.com/jobs/reissued",
                        description="Own the reporting stack. Fully remote (US).")
    assert main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: [reissued]) == 0

    queue = next((tmp_path / "radar-out").iterdir()) / "queue.md"
    text = queue.read_text()
    assert "Northwind Analytics" in text          # not hidden
    assert "kill (bi-analytics)" in text          # and carrying the verdict
    assert "already judged" in text


def test_a_run_survives_a_ledger_it_cannot_fully_parse(tmp_path, capsys):
    # A half-edited ledger must warn and keep the decisions it can still read,
    # never take down a run — same instinct as a corrupt state file.
    cfg_dir = _config(tmp_path)
    (cfg_dir / "decisions.csv").write_text(
        "jid,company,title,verdict,reason,date,url\n"
        "j1,Northwind Analytics,Data Engineer,kill,bi-analytics,2026-09-25,\n"
        "j2,Cobalt Grid,Data Platform Engineer,perhaps,unsure,2026-09-25,\n")
    assert main(["--config", str(cfg_dir)], scrape_fn=lambda cfg: _rows()) == 0
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "perhaps" in out


# --- judging the same posting twice (R64-08) ---------------------------------

def test_a_second_decision_on_the_same_jid_says_what_it_is_replacing(tmp_path, capsys):
    # The ledger is append-only and people change their minds, so this is a normal
    # day rather than an error. But a silent append looks identical to a no-op, and
    # the reader has no way to tell that the row they are replacing existed.
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
          "--config", str(cfg_dir)])
    capsys.readouterr()

    code = main(["judge", "j1", "--verdict", "draft", "--reason", "reconsidered",
                 "--config", str(cfg_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "already judged" in out
    assert "kill" in out
    assert "recording the newer decision" in out
    assert len(load_ledger(cfg_dir / "decisions.csv")) == 2


def test_the_notice_names_the_date_of_the_decision_being_replaced(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    (cfg_dir / "decisions.csv").write_text(
        "jid,company,title,verdict,reason,date,url\n"
        "j1,Northwind Analytics,Data Engineer,kill,bi-analytics,2026-09-20,\n")
    _seed_state(cfg_dir, _rows())
    capsys.readouterr()
    main(["judge", "j1", "--verdict", "draft", "--reason", "reconsidered",
          "--config", str(cfg_dir)])
    assert "2026-09-20" in capsys.readouterr().out


def test_a_second_decision_on_the_same_company_and_title_also_notices(tmp_path, capsys):
    # Judged once by jid, then again under the reissued posting's new id. Tier 2 is
    # what recognises it, so the notice has to fire on the pair too.
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
          "--config", str(cfg_dir)])
    capsys.readouterr()

    main(["judge", "--company", "Northwind Analytics", "--title", "Data Engineer",
          "--verdict", "draft", "--reason", "reconsidered", "--config", str(cfg_dir)])
    out = capsys.readouterr().out
    assert "already judged" in out
    assert "kill" in out


def test_a_first_decision_says_nothing_about_a_previous_one(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    capsys.readouterr()
    main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
          "--config", str(cfg_dir)])
    assert "already judged" not in capsys.readouterr().out


def test_a_decision_about_a_different_posting_says_nothing(tmp_path, capsys):
    cfg_dir = _config(tmp_path)
    _seed_state(cfg_dir, _rows())
    main(["judge", "j1", "--verdict", "kill", "--reason", "bi-analytics",
          "--config", str(cfg_dir)])
    capsys.readouterr()
    main(["judge", "j2", "--verdict", "draft", "--reason", "strong-fit",
          "--config", str(cfg_dir)])
    assert "already judged" not in capsys.readouterr().out

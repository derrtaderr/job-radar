"""The day's delivery folder: queue.md plus a jd/ file per posting.

Every fixture here is synthetic — fictional employers for the example persona
(a data engineer), fictional posting URLs under example.com.
"""
from engine.radar.report import (
    _comp,
    _jd_filename,
    day_paths,
    render_report,
    write_jds,
    write_report,
)
from tests.fixtures import make_report_row

DAY = "2026-09-13"


def test_comp_range_renders_in_thousands():
    assert _comp({"min_amount": 150000, "max_amount": 190000,
                  "interval": "yearly"}) == "$150-190K"


def test_comp_max_only():
    assert _comp({"min_amount": None, "max_amount": 190000,
                  "interval": "yearly"}) == "to $190K"


def test_comp_min_only():
    assert _comp({"min_amount": 150000, "max_amount": None,
                  "interval": "yearly"}) == "from $150K"


def test_comp_unlisted():
    assert _comp({"min_amount": None, "max_amount": None,
                  "interval": "yearly"}) == "unlisted"


def test_comp_hourly_keeps_the_interval_visible():
    # A non-yearly number must never be silently rendered as a salary band —
    # "$40-60K" for an hourly rate would be a lie the reader can't catch.
    assert _comp({"min_amount": 40, "max_amount": 60,
                  "interval": "hourly"}) == "40-60 hourly"


def test_comp_hourly_single_bound():
    assert _comp({"min_amount": None, "max_amount": 60,
                  "interval": "hourly"}) == "60 hourly"


def test_comp_hourly_unlisted():
    assert _comp({"min_amount": None, "max_amount": None,
                  "interval": "hourly"}) == "unlisted"


def test_comp_interval_absent_defaults_to_yearly_range():
    assert _comp({"min_amount": 100000, "max_amount": 150000,
                  "interval": None}) == "$100-150K"


def test_comp_drops_a_pointless_decimal_on_non_yearly_amounts():
    # Scraped amounts arrive as floats; "40.0-60.0 hourly" is noise.
    assert _comp({"min_amount": 40.0, "max_amount": 60.5,
                  "interval": "hourly"}) == "40-60.5 hourly"


# --- rendering --------------------------------------------------------------

def test_render_returns_none_when_there_is_nothing_to_say():
    # No survivors and no kills means no file — an empty queue.md is worse than
    # no queue.md, because it looks like a finished run that found nothing.
    assert render_report([], [], DAY) is None


def test_render_sorts_by_score_and_carries_frontmatter():
    out = render_report(
        [make_report_row(company="Quarry Systems", score=40),
         make_report_row(company="Cobalt Grid", score=90)], [], DAY)
    assert out.index("Cobalt Grid") < out.index("Quarry Systems")
    assert "read_by: your daily review session" in out
    assert DAY in out


def test_render_frontmatter_reader_is_generic():
    # The report is read by whoever runs the radar, so the reader line names a
    # review session in the abstract and never one person's tooling or notes.
    head = render_report([make_report_row()], [], DAY).split("---")[1]
    assert [line for line in head.splitlines() if line.startswith("read_by:")] == [
        "read_by: your daily review session"]


def test_render_counts_survivors_and_kills_in_the_header():
    out = render_report(
        [make_report_row()],
        [dict(make_report_row(company="Quarry Systems"),
              flags=[("bdr-scope", "carry a quota")])], DAY)
    assert "1 in the queue" in out and "1 killed by rule" in out


def test_render_killed_rows_struck_through_with_quoted_evidence():
    # A kill is never silent: the reader sees the posting, the rule that fired,
    # and the line of the posting that matched, so overruling is a one-liner.
    out = render_report([], [dict(make_report_row(company="Quarry Systems"),
                                  flags=[("bdr-scope", "carry a quota")])], DAY)
    assert "~~" in out
    assert "Quarry Systems" in out
    assert "bdr-scope" in out and "carry a quota" in out


def test_render_shows_every_flag_on_a_multi_kill_row():
    out = render_report([], [dict(make_report_row(),
                                  flags=[("bdr-scope", "carry a quota"),
                                         ("location", "Phoenix, AZ")])], DAY)
    assert "bdr-scope" in out and "location" in out and "Phoenix, AZ" in out


def test_render_missing_fields_show_empty_not_none():
    # A literal "None" in a queue cell reads as data and wastes the reader's time.
    out = render_report([make_report_row(date_posted=None, location=None,
                                         job_url=None)], [], DAY)
    assert "None" not in out


def test_render_killed_missing_job_url_shows_empty_not_none():
    out = render_report([], [dict(make_report_row(job_url=None),
                                  flags=[("bdr-scope", "carry a quota")])], DAY)
    assert "None" not in out


def test_render_escapes_pipe_in_title_and_company():
    # An unescaped pipe in a value would silently break the table columns.
    out = render_report([make_report_row(title="Data Engineer | Platform",
                                         company="Cobalt | Grid")], [], DAY)
    assert "Data Engineer \\| Platform" in out
    assert "Cobalt \\| Grid" in out


# --- local JD files ---------------------------------------------------------

def test_jd_filename_sanitizes_url_fallback_ids():
    # A row with no id falls back to its URL, so slashes and colons must never
    # reach the filesystem.
    name = _jd_filename("https://example.com/jobs/view/1?src=a")
    assert "/" not in name and ":" not in name
    assert name.endswith(".md")


def test_jd_filename_keeps_a_plain_id_readable():
    assert _jd_filename("job-123") == "job-123.md"


def test_write_jds_writes_survivor_and_killed_descriptions(tmp_path):
    # Kills get a JD file too: checking a suspected false kill must not require
    # re-fetching a posting that may already be behind a bot wall.
    survivors = [make_report_row(jid="a", description="Own the data platform end to end.")]
    killed = [dict(make_report_row(company="Quarry Systems", jid="e",
                                   description="You will carry a quota of 30 meetings."),
                   flags=[("bdr-scope", "carry a quota")])]
    assert write_jds(tmp_path, survivors, killed, DAY) == 2

    surv = (tmp_path / "a.md").read_text()
    assert "Own the data platform end to end." in surv
    assert "Data Platform Engineer" in surv and "Northwind Analytics" in surv
    assert "https://example.com/jobs/view/1" in surv
    assert f"captured: {DAY}" in surv

    kill = (tmp_path / "e.md").read_text()
    assert "You will carry a quota of 30 meetings." in kill
    assert "bdr-scope" in kill  # a killed JD names the flag that killed it


def test_write_jds_omits_the_killed_line_for_survivors(tmp_path):
    write_jds(tmp_path, [make_report_row(jid="a", description="Own the pipeline.")],
              [], DAY)
    assert "Killed by:" not in (tmp_path / "a.md").read_text()


def test_write_jds_skips_rows_without_description(tmp_path):
    # No description means no file, and no directory created for nothing.
    assert write_jds(tmp_path / "jd", [make_report_row(jid="a", description=None)],
                     [], DAY) == 0
    assert not (tmp_path / "jd").exists()


def test_write_jds_creates_the_directory_on_demand(tmp_path):
    target = tmp_path / "2026-09-13" / "jd"
    assert write_jds(target, [make_report_row(jid="a", description="Own it.")],
                     [], DAY) == 1
    assert (target / "a.md").exists()


def test_render_survivor_row_links_local_jd():
    out = render_report([make_report_row(jid="job-1", description="Some JD text.")],
                        [], DAY)
    assert "jd/job-1.md" in out


def test_render_killed_line_links_local_jd():
    out = render_report([], [dict(make_report_row(jid="job-2",
                                                  description="carry a quota"),
                                  flags=[("bdr-scope", "carry a quota")])], DAY)
    assert "jd/job-2.md" in out


def test_render_no_jd_link_when_description_missing():
    # No description means no JD file was written, so no link may render — a
    # dead link in the queue is worse than no link.
    assert "jd/" not in render_report([make_report_row(jid="job-3", description=None)],
                                      [], DAY)


# --- the day folder ---------------------------------------------------------

def test_day_paths_compose_one_folder_per_day(tmp_path):
    # Everything for one run lives together, so acting on the queue is "open
    # today's folder" rather than hunting across an output tree.
    day_dir, queue, jd_dir = day_paths(tmp_path, DAY)
    assert day_dir == tmp_path / DAY
    assert queue == tmp_path / DAY / "queue.md"
    assert jd_dir == tmp_path / DAY / "jd"


def test_day_paths_accepts_a_date_object(tmp_path):
    import datetime
    day_dir, _, _ = day_paths(tmp_path, datetime.date(2026, 9, 13))
    assert day_dir.name == "2026-09-13"


def test_write_report_writes_a_fresh_file_and_creates_its_folder(tmp_path):
    path = tmp_path / DAY / "queue.md"
    assert write_report(path, [make_report_row()], [], DAY) is True
    assert f"Job radar — {DAY}" in path.read_text()


def test_write_report_appends_when_the_day_already_has_a_queue(tmp_path):
    # A second run on the same day must never destroy the first run's queue —
    # you may already have acted on it.
    path = tmp_path / "queue.md"
    path.write_text("---\nname: Job radar 2026-09-13\n---\n\nfirst run row here\n")
    assert write_report(path, [make_report_row(company="Tessellate Labs")], [], DAY) is True

    out = path.read_text()
    assert "first run row here" in out
    assert "## Later run (same day)" in out
    assert "Tessellate Labs" in out


def test_write_report_appends_without_a_second_frontmatter_block(tmp_path):
    path = tmp_path / "queue.md"
    write_report(path, [make_report_row()], [], DAY)
    write_report(path, [make_report_row(company="Tessellate Labs")], [], DAY)
    assert path.read_text().count("read_by:") == 1


def test_write_report_leaves_the_file_untouched_when_there_is_nothing_to_write(tmp_path):
    path = tmp_path / "queue.md"
    path.write_text("first run row here\n")
    assert write_report(path, [], [], DAY) is False
    assert path.read_text() == "first run row here\n"


def test_write_report_creates_nothing_when_there_is_nothing_to_write(tmp_path):
    path = tmp_path / DAY / "queue.md"
    assert write_report(path, [], [], DAY) is False
    assert not path.exists()

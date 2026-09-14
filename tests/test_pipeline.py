"""The pipeline: raw scraped rows in, a ranked queue and a visible kill list out.

Every fixture here is synthetic — fictional employers for the example persona
(a data engineer), fictional posting URLs under example.com.
"""
import dataclasses
import datetime
from pathlib import Path

from engine.radar.config import load_config
from engine.radar.pipeline import excluded, pipeline
from tests.fixtures import BDR_JD, make_row

CFG = load_config(Path(__file__).parent.parent / "config.example")
TODAY = datetime.date(2026, 9, 13)


def _cfg(**overrides):
    return dataclasses.replace(CFG, **overrides)


def _row(jid, **overrides):
    return make_row(id=jid, job_url=f"https://example.com/jobs/view/{jid}", **overrides)


def test_excluded_is_substring_and_case_insensitive():
    assert excluded("Northwind Analytics, Inc.", ["northwind"])
    assert excluded("NORTHWIND ANALYTICS", ["northwind"])
    assert not excluded("Cobalt Grid", ["northwind"])
    assert not excluded(None, ["northwind"])
    assert not excluded("Cobalt Grid", [])


def test_pipeline_filters_dedups_and_scores():
    raw = [
        _row("a", company="Cobalt Grid"),                      # fresh survivor
        _row("b", company="Harborlight Data"),                 # already in state
        _row("c", company="Tessellate Labs"),                  # in the tracker
        _row("d", company="Northwind Analytics"),              # in exclusions
        _row("e", company="Quarry Systems", description=BDR_JD),  # killed, visible
        _row("f", company="Meridian Rows", title="Backend Engineer"),  # title-dropped
    ]
    survivors, killed, new_state = pipeline(
        raw, state={"b": "2026-09-12"}, cfg=_cfg(exclusions=["northwind"]),
        tracker_set={"tessellate labs"}, today=TODAY)

    assert [r["company"] for r in survivors] == ["Cobalt Grid"]
    assert survivors[0]["score"] > 0
    assert [r["company"] for r in killed] == ["Quarry Systems"]
    # Seen survivors and kills are recorded; suppressed rows are not, so a
    # company later removed from the tracker can still surface.
    assert set(new_state) == {"a", "b", "e"}


def test_pipeline_records_today_as_the_seen_date():
    _, _, new_state = pipeline([_row("a")], state={}, cfg=CFG,
                               tracker_set=set(), today=TODAY)
    assert new_state["a"] == str(TODAY)


def test_pipeline_does_not_mutate_the_state_it_was_given():
    state = {"b": "2026-09-12"}
    pipeline([_row("a")], state=state, cfg=CFG, tracker_set=set(), today=TODAY)
    assert state == {"b": "2026-09-12"}


def test_pipeline_dedups_same_company_and_title_within_one_run():
    # The same posting listed under two cities arrives as two ids. It must not
    # eat two queue slots, and the skipped twin must not be written to state.
    raw = [_row("a", company="Cobalt Grid", title="Data Platform Engineer"),
           _row("b", company="cobalt grid", title="data platform engineer")]
    survivors, _, new_state = pipeline(raw, state={}, cfg=CFG,
                                       tracker_set=set(), today=TODAY)
    assert len(survivors) == 1
    assert set(new_state) == {"a"}


def test_pipeline_does_not_collide_rows_with_no_job_url():
    # A None job_url must never be treated as a "seen" URL — two distinct
    # postings that both lack a URL are not duplicates of each other, and the
    # second one silently disappearing is the bug this guards against.
    raw = [make_row(id="a", job_url=None, company="Cobalt Grid"),
           make_row(id="b", job_url=None, company="Harborlight Data")]
    survivors, _, new_state = pipeline(raw, state={}, cfg=CFG,
                                       tracker_set=set(), today=TODAY)
    assert [r["company"] for r in survivors] == ["Cobalt Grid", "Harborlight Data"]
    assert set(new_state) == {"a", "b"}


def test_pipeline_does_not_collide_distinct_rows_with_no_id_and_no_url():
    # Both id and job_url missing must not collapse to the literal string
    # "None" for every such row — two distinct postings need two distinct
    # synthetic ids, both surviving and both recorded in state.
    raw = [make_row(id=None, job_url=None, company="Cobalt Grid",
                    title="Data Platform Engineer"),
           make_row(id=None, job_url=None, company="Harborlight Data",
                    title="Platform Reliability Engineer")]
    survivors, _, new_state = pipeline(raw, state={}, cfg=CFG,
                                       tracker_set=set(), today=TODAY)
    assert [r["company"] for r in survivors] == ["Cobalt Grid", "Harborlight Data"]
    assert len(new_state) == 2

    # A THIRD such row, on a second run seeded with the state above, must not
    # be falsely suppressed — that would happen if every no-id/no-url row
    # shared one synthetic key that the first run already wrote to state.
    third = make_row(id=None, job_url=None, company="Quarry Systems",
                     title="Data Engineer")
    survivors2, _, new_state2 = pipeline([third], state=new_state, cfg=CFG,
                                         tracker_set=set(), today=TODAY)
    assert [r["company"] for r in survivors2] == ["Quarry Systems"]
    assert len(new_state2) == 3


def test_pipeline_dedups_by_url_within_one_run():
    raw = [make_row(id="a", job_url="https://example.com/jobs/view/1",
                    company="Cobalt Grid"),
           make_row(id="b", job_url="https://example.com/jobs/view/1",
                    company="Harborlight Data")]
    survivors, _, new_state = pipeline(raw, state={}, cfg=CFG,
                                       tracker_set=set(), today=TODAY)
    assert len(survivors) == 1
    assert set(new_state) == {"a"}


def test_pipeline_empty_raw_rows_leaves_state_unchanged():
    # A zero-row run is a broken scrape, not a quiet day. The pure pipeline must
    # not touch state, so the next run isn't poisoned by a bad run's non-event.
    survivors, killed, new_state = pipeline([], state={"x": "2026-09-12"}, cfg=CFG,
                                            tracker_set=set(), today=TODAY)
    assert survivors == [] and killed == []
    assert new_state == {"x": "2026-09-12"}


def test_pipeline_stamps_jid_on_survivors_and_killed():
    # The JD layer names each file after this id — on kills too, so a suspected
    # false kill can be read off disk.
    survivors, killed, _ = pipeline(
        [_row("a", company="Cobalt Grid"),
         _row("e", company="Quarry Systems", description=BDR_JD)],
        state={}, cfg=CFG, tracker_set=set(), today=TODAY)
    assert survivors[0]["jid"] == "a"
    assert killed[0]["jid"] == "e"


def test_pipeline_jid_falls_back_to_the_job_url():
    row = make_row(company="Cobalt Grid", job_url="https://example.com/jobs/view/7")
    del row["id"]
    survivors, _, new_state = pipeline([row], state={}, cfg=CFG,
                                       tracker_set=set(), today=TODAY)
    assert survivors[0]["jid"] == "https://example.com/jobs/view/7"
    assert "https://example.com/jobs/view/7" in new_state


def test_pipeline_sorts_survivors_by_score_descending():
    raw = [_row("a", company="Cobalt Grid", title="Analytics Engineer"),
           _row("b", company="Harborlight Data", title="Data Platform Engineer")]
    survivors, _, _ = pipeline(raw, state={}, cfg=CFG,
                               tracker_set=set(), today=TODAY)
    assert [r["company"] for r in survivors] == ["Harborlight Data", "Cobalt Grid"]
    assert survivors[0]["score"] > survivors[1]["score"]


def test_pipeline_kills_carry_their_flags_and_never_a_score():
    _, killed, _ = pipeline([_row("e", company="Quarry Systems", description=BDR_JD)],
                            state={}, cfg=CFG, tracker_set=set(), today=TODAY)
    assert [n for n, _ in killed[0]["flags"]] == ["bdr-scope"]
    assert "quota" in dict(killed[0]["flags"])["bdr-scope"]
    assert "score" not in killed[0]


def test_pipeline_tracker_suppression_uses_fuzzy_matching():
    # The tracker cell and the scrape are written by different authors.
    survivors, _, _ = pipeline([_row("a", company="Tessellate Labs, Inc.")],
                               state={}, cfg=CFG,
                               tracker_set={"tessellate labs (via referral)"},
                               today=TODAY)
    assert survivors == []

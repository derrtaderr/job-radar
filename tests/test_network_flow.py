"""The order of steps: ask a warm connection first, give it three business
days, then apply anyway. And the list of what is waiting on the person."""
import datetime

from engine.network.flow import due, gate
from engine.network.paths import ContactPath, PathReport
from engine.network.touches import Touch

D = datetime.date


def report(*paths, company="Harborlight"):
    return PathReport(company=company, paths=tuple(paths), checks=(),
                      status="found" if paths else "unresearched",
                      looked_up=None, stale=False, export_date=None)


WARM = ContactPath("warm", "ana-rivera", "Ana Rivera", "Engineer", "2019-01-15")
HM = ContactPath("cold_hm", "dee-marsh", "Dee Marsh", "VP Growth", "")


def T(date, state, slug="ana-rivera", path="warm", company="Harborlight"):
    return Touch(date=date, posting_id="", company=company, person_slug=slug,
                 path=path, motive="", hook_level="", register="", control="no",
                 state=state, note="")


def test_no_warm_path_proceeds():
    assert gate(report(HM), [], {}, D(2026, 10, 12)).code == 0


def test_warm_and_not_asked_stops_and_names_the_person():
    result = gate(report(WARM, HM), [], {}, D(2026, 10, 12))
    assert result.code == 3
    assert "Ana Rivera" in result.message and "/reach" in result.message


def test_friday_ask_holds_until_wednesday():
    touches = [T("2026-10-09", "asked")]  # a Friday
    assert gate(report(WARM), touches, {}, D(2026, 10, 13)).code == 4  # Tuesday
    assert "2026-10-14" in gate(report(WARM), touches, {}, D(2026, 10, 13)).message
    assert gate(report(WARM), touches, {}, D(2026, 10, 14)).code == 0  # Wednesday


def test_referred_declined_override_and_applied_all_proceed():
    for state in ("referred", "declined", "no_reply"):
        touches = [T("2026-10-12", "asked"), T("2026-10-12", state)]
        assert gate(report(WARM), touches, {}, D(2026, 10, 12)).code == 0
    for state in ("override", "applied"):
        assert gate(report(WARM), [T("2026-10-12", state, slug="", path="")],
                    {}, D(2026, 10, 12)).code == 0


def test_due_lists_expired_warm_asks_and_pending_chats_oldest_first():
    touches = [T("2026-10-08", "asked", slug="eli-park", path="recent_hire"),
               T("2026-10-09", "asked")]
    items, no_reply = due(touches, {}, {}, D(2026, 10, 14))
    assert [i.since for i in items] == ["2026-10-08", "2026-10-09"]
    assert "apply" in items[1].message.lower()
    assert no_reply == []


def test_due_marks_no_reply_after_ten_business_days():
    items, no_reply = due([T("2026-09-28", "asked")], {}, {}, D(2026, 10, 12))
    assert [t.state for t in no_reply] == ["no_reply"]
    assert no_reply[0].date == "2026-10-12" and no_reply[0].path == "warm"


def test_due_owes_a_hiring_manager_note_after_applying():
    touches = [T("2026-10-12", "applied", slug="", path="")]
    items, _ = due(touches, {"harborlight": report(HM)}, {}, D(2026, 10, 12))
    assert len(items) == 1 and "Dee Marsh" in items[0].message
    touches.append(T("2026-10-12", "asked", slug="dee-marsh", path="cold_hm"))
    items, _ = due(touches, {"harborlight": report(HM)}, {}, D(2026, 10, 12))
    assert items == []

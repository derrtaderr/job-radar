from tools.privacy_guard import scan_text


def test_catches_email():
    assert scan_text("contact jane.doe@example.com", []) != []


def test_catches_phone():
    assert scan_text("call 555-867-5309 today", []) != []
    assert scan_text("call (415) 555-0134", []) != []


def test_catches_denylist_entry_case_insensitive():
    assert scan_text("built at ACME Corp", ["acme corp"]) != []


def test_clean_text_passes():
    assert scan_text("kill rules live in config/rules.yaml", ["acme corp"]) == []


def test_version_numbers_are_not_phones():
    assert scan_text("python-jobspy>=1.1.82 on 2026-09-13", []) == []

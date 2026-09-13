import subprocess

from tools.privacy_guard import scan_repo, scan_text


def test_catches_email():
    assert scan_text("contact jane.doe@realcorp.io", []) != []


def test_catches_phone():
    assert scan_text("call 555-867-5309 today", []) != []


def test_catches_denylist_entry_case_insensitive():
    assert scan_text("built at ACME Corp", ["acme corp"]) != []


def test_clean_text_passes():
    assert scan_text("kill rules live in config/rules.yaml", ["acme corp"]) == []


def test_version_numbers_are_not_phones():
    assert scan_text("python-jobspy>=1.1.82 on 2026-09-13", []) == []


def test_reserved_domain_email_is_safe_placeholder():
    # RFC 2606 reserves example.com/.org/.net for documentation — these can
    # never be a real person's address, so fixtures that use them shouldn't
    # trip the guard.
    assert scan_text("contact jane.doe@example.com", []) == []
    assert scan_text("contact jane.doe@example.org", []) == []
    assert scan_text("contact jane.doe@example.net", []) == []


def test_nanp_reserved_fictional_phone_is_safe_placeholder():
    # NANP reserves NPA-555-01XX as the official "this is fake" phone range.
    assert scan_text("call (415) 555-0134", []) == []
    assert scan_text("call 415-555-0199", []) == []


def test_real_looking_email_still_caught():
    # The reserved-placeholder carve-out must not over-exempt: an ordinary
    # domain like gmail.com is not reserved and must still be flagged.
    assert scan_text("contact j.smith@gmail.com", []) != []


def test_reserved_domain_carveout_does_not_bypass_real_subdomain():
    # EMAIL's regex only captures a single label + TLD, so it truncates
    # "example.com.attacker.io" down to "example.com". The carve-out must
    # not trust that truncated match — the real, deliverable domain here is
    # "example.com.attacker.io", which is not reserved and must be caught.
    assert scan_text("realname@example.com.attacker.io", []) != []


def test_reserved_domain_carveout_survives_trailing_sentence_period():
    # Sentence-ending punctuation must not defeat the carve-out: the actual
    # domain is still exactly example.com, just followed by a period.
    assert scan_text("contact jane.doe@example.com.", []) == []


def test_denylist_still_fires_on_placeholder_content():
    # A safe-placeholder email in the same string must not suppress a real
    # denylist hit — only the built-in email/phone patterns get the carve-out.
    assert scan_text("built at ACME Corp, contact jane@example.com", ["acme corp"]) != []


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)


def test_skip_is_scoped_by_path_not_basename(tmp_path):
    # A DIFFERENT file that happens to share a basename with the guard's own
    # test fixture must still be scanned. The exemption must key off the
    # full relative path from git ls-files, not the bare filename, or any
    # file named test_privacy_guard.py anywhere in the tree would silently
    # bypass the guard.
    _init_repo(tmp_path)
    decoy = tmp_path / "scripts" / "test_privacy_guard.py"
    decoy.parent.mkdir(parents=True)
    decoy.write_text("real contact: j.smith@gmail.com\n")
    subprocess.run(["git", "add", "scripts/test_privacy_guard.py"], cwd=tmp_path, check=True)

    violations = scan_repo(tmp_path)
    assert any("scripts/test_privacy_guard.py" in v for v in violations)

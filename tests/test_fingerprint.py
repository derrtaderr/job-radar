"""Content fingerprints — the mechanism that recognises the same req arriving
twice under two ids (row 64, miss 2).

Two shapes of that miss, and they need two different fingerprints:

- **Same req, different territory.** One posting listed as "Eastern US" and
  again as "Western US". The bodies are identical once the territory token is
  gone, so the BODY fingerprint catches it.
- **Aggregator repost.** A job board reposts a client's req under its own name
  with the client anonymised. The prose genuinely differs, so the body
  fingerprint cannot bridge it — but the comp band and the benefits block are
  copied verbatim, so the COMP fingerprint catches it.

Every posting here is invented, as is every company name in it.
"""
from engine.radar.fingerprint import fp_body, fp_comp, fp_equal

_BENEFITS = (
    "We offer full medical, dental and vision coverage, a 401k match, "
    "unlimited PTO, and paid parental leave."
)


def _row(**overrides):
    row = {"company": "Cobalt Grid", "title": "Data Platform Engineer",
           "description": "Own the ingestion layer. " + _BENEFITS,
           "min_amount": 165000, "max_amount": 195000, "interval": "yearly",
           "location": "Denver, CO"}
    row.update(overrides)
    return row


# --- the comp fingerprint -----------------------------------------------------

def test_comp_fingerprint_survives_the_company_name_being_swapped():
    # The aggregator case: same band, same benefits, a different employer name
    # on the posting and the client anonymised out of the prose.
    original = _row(company="Cobalt Grid")
    repost = _row(company="Talent Reach Staffing",
                  description="Our client is hiring for this role. " + _BENEFITS)
    assert fp_equal(fp_comp(original), fp_comp(repost))


def test_comp_fingerprint_ignores_the_order_the_benefits_are_listed_in():
    reworded = _row(description=(
        "Own the ingestion layer. Paid parental leave, unlimited PTO, a 401k "
        "match, and full vision, dental and medical coverage."))
    assert fp_equal(fp_comp(_row()), fp_comp(reworded))


def test_comp_fingerprint_differs_when_the_band_differs():
    assert not fp_equal(fp_comp(_row()), fp_comp(_row(max_amount=210000)))


def test_comp_fingerprint_differs_when_the_benefits_differ():
    lean = _row(description="Own the ingestion layer. We offer a 401k match.")
    assert not fp_equal(fp_comp(_row()), fp_comp(lean))


def test_comp_fingerprint_falls_back_to_a_body_stated_band():
    # No structured amounts, a salary range in the prose. Two postings stating
    # the same range with the same benefits are still the same posting.
    stated = "The base salary range for this role is $165,000 to $195,000. "
    a = _row(min_amount=None, max_amount=None, description=stated + _BENEFITS)
    b = _row(min_amount=None, max_amount=None, company="Talent Reach Staffing",
             description=stated + _BENEFITS)
    assert fp_comp(a) is not None
    assert fp_equal(fp_comp(a), fp_comp(b))


def test_comp_fingerprint_is_none_with_neither_a_band_nor_a_benefit():
    # A fingerprint of nothing would match every thin posting to every other
    # one, which is the false merge this whole mechanism exists to avoid.
    thin = _row(min_amount=None, max_amount=None,
                description="Own the ingestion layer. Apply through our portal.")
    assert fp_comp(thin) is None


# --- the body fingerprint -----------------------------------------------------

def test_body_fingerprint_ignores_the_territory_token():
    east = _row(description="Own the ingestion layer for our Eastern US team.")
    west = _row(description="Own the ingestion layer for our Western US team.")
    assert fp_equal(fp_body(east), fp_body(west))


def test_body_fingerprint_ignores_a_state_or_country_suffix():
    a = _row(description="This role is based in New York, United States.")
    b = _row(description="This role is based in New York, NY.")
    assert fp_equal(fp_body(a), fp_body(b))


def test_body_fingerprint_ignores_the_posting_companys_own_name():
    # The same body with the employer's name swapped is the same body. The
    # company name is the one token guaranteed to differ on a repost.
    a = _row(company="Cobalt Grid",
             description="Cobalt Grid is hiring an engineer to own ingestion.")
    b = _row(company="Larkspur Grid",
             description="Larkspur Grid is hiring an engineer to own ingestion.")
    assert fp_equal(fp_body(a), fp_body(b))


def test_body_fingerprint_differs_on_a_genuinely_different_posting():
    other = _row(description="Run the analytics team's reporting stack. " + _BENEFITS)
    assert not fp_equal(fp_body(_row()), fp_body(other))


def test_body_fingerprint_differs_when_only_the_title_differs():
    # Title is part of the body fingerprint: one company reposting a DIFFERENT
    # role with boilerplate body text is not a repost of the first one.
    assert not fp_equal(fp_body(_row()), fp_body(_row(title="Analytics Engineer")))


def test_body_fingerprint_is_none_without_a_description():
    assert fp_body(_row(description="")) is None
    assert fp_body(_row(description=None)) is None


# --- the None rule ------------------------------------------------------------

def test_two_unknown_fingerprints_never_match():
    # A legacy state entry has no fingerprints. If None matched None, every
    # pre-upgrade posting would read as a repost of every other one.
    assert not fp_equal(None, None)
    assert not fp_equal(None, "abc")
    assert not fp_equal("abc", None)


def test_identical_fingerprints_match():
    assert fp_equal("abc", "abc")

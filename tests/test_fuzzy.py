from raycast_linux.logic.fuzzy import fuzzy_rank, fuzzy_score


def test_subsequence_match():
    assert fuzzy_score("ff", "Firefox") is not None
    assert fuzzy_score("fx", "Firefox") is not None
    assert fuzzy_score("z", "Firefox") is None
    assert fuzzy_score("chrome", "Google Chrome") is not None
    assert fuzzy_score("xyz", "abc") is None


def test_scoring_order():
    ranked = fuzzy_rank("chrom", ["xchrome", "Google Chrome", "chromium-browser", "chrome-extension"])
    # Prefix matches must beat the mid-word match.
    assert ranked.index(2) < ranked.index(0)
    assert ranked.index(3) < ranked.index(0)


def test_case_bonus():
    assert fuzzy_score("Ch", "Chrome") > fuzzy_score("ch", "chrome")


def test_empty_query_matches_all():
    assert fuzzy_score("", "anything") == 0
    assert fuzzy_rank("", ["a", "b"]) == [0, 1]


def test_stable_order():
    assert fuzzy_rank("a", ["ab", "ba"]) == [0, 1]

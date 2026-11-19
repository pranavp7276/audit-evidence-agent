from eval.score import score


def test_perfect():
    t = {("A1", "Q1"), ("A2", "Q3")}
    s = score(t, set(t), 0)
    assert s.recall == 1.0 and s.false_gap_rate == 0.0 and s.passes


def test_missed_and_false():
    truth = {("A1", "Q1"), ("A2", "Q1"), ("A3", "Q2")}
    reported = {("A1", "Q1"), ("A9", "Q1")}
    s = score(truth, reported, 0)
    assert s.matched == 1
    assert round(s.recall, 3) == 0.333
    assert s.false_gap_rate == 0.5
    assert s.missed == [("A2", "Q1"), ("A3", "Q2")]
    assert s.false_gaps == [("A9", "Q1")]
    assert not s.passes


def test_unsupported_claim_fails_even_with_perfect_recall():
    t = {("A1", "Q1")}
    assert not score(t, t, 1).passes


def test_no_true_gaps_and_none_reported_passes():
    assert score(set(), set(), 0).passes

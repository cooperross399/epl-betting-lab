from epl_betting_lab.models.value import american_to_implied, expected_value_per_unit, fair_american_from_prob


def test_american_to_implied_positive():
    assert round(american_to_implied(100), 3) == 0.5


def test_american_to_implied_negative():
    assert round(american_to_implied(-150), 3) == 0.6


def test_expected_value_positive():
    assert expected_value_per_unit(0.55, 100) > 0


def test_fair_american_from_prob():
    assert fair_american_from_prob(0.5) == 100

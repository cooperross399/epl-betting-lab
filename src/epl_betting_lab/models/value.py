from __future__ import annotations


def american_to_decimal(odds: float) -> float:
    odds = float(odds)
    if odds > 0:
        return 1 + odds / 100
    return 1 + 100 / abs(odds)


def decimal_to_american(decimal_odds: float) -> float:
    decimal_odds = float(decimal_odds)
    if decimal_odds <= 1:
        raise ValueError("Decimal odds must be greater than 1.")
    if decimal_odds >= 2:
        return round((decimal_odds - 1) * 100, 0)
    return round(-100 / (decimal_odds - 1), 0)


def american_to_implied(odds: float) -> float:
    odds = float(odds)
    if odds > 0:
        return 100 / (odds + 100)
    return abs(odds) / (abs(odds) + 100)


def fair_american_from_prob(prob: float) -> float:
    if prob <= 0 or prob >= 1:
        raise ValueError("Probability must be between 0 and 1.")
    decimal = 1 / prob
    return decimal_to_american(decimal)


def expected_value_per_unit(model_prob: float, american_odds: float) -> float:
    """Return expected profit per 1 unit staked."""
    decimal = american_to_decimal(american_odds)
    profit_if_win = decimal - 1
    return model_prob * profit_if_win - (1 - model_prob)


def grade_edge(model_prob: float, american_odds: float, min_edge: float = 0.035, max_default_juice: int = -160) -> dict:
    implied = american_to_implied(american_odds)
    edge = model_prob - implied
    ev = expected_value_per_unit(model_prob, american_odds)
    too_juiced = american_odds < max_default_juice

    if too_juiced:
        status = "PASS - too much juice"
    elif edge >= min_edge and ev > 0:
        status = "BETTABLE"
    elif edge >= 0.015 and ev > 0:
        status = "LEAN"
    else:
        status = "PASS"

    return {
        "model_prob": round(model_prob, 4),
        "book_implied": round(implied, 4),
        "edge": round(edge, 4),
        "ev_per_unit": round(ev, 4),
        "fair_american": fair_american_from_prob(model_prob),
        "status": status,
    }

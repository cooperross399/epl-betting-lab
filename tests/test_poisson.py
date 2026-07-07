import pandas as pd

from epl_betting_lab.models.poisson_goals import PoissonGoalsModel


def test_poisson_model_projects_match():
    df = pd.DataFrame({
        "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]),
        "home_team": ["A", "B", "A", "B"],
        "away_team": ["B", "A", "B", "A"],
        "home_goals": [2, 1, 3, 0],
        "away_goals": [1, 1, 0, 2],
    })
    model = PoissonGoalsModel().fit(df)
    probs = model.match_probabilities("A", "B")
    assert probs["home_xg"] > 0
    assert 0 < probs["home_win"] < 1
    assert len(probs["top_scores"]) == 5

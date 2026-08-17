from __future__ import annotations

import pytest

from epl_betting_lab.providers.team_names import (
    CANONICAL_TEAM_NAMES,
    PROVIDER_TEAM_ALIASES,
    is_canonical_team_name,
    is_mapped_team_name,
    normalize_team_name,
    unmapped_team_names,
)


REQUIRED_MAPPINGS = {
    "Brighton and Hove Albion": "Brighton",
    "Coventry City": "Coventry",
    "Hull City": "Hull",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Tottenham Hotspur": "Tottenham",
}


@pytest.mark.parametrize(("provider_name", "expected"), REQUIRED_MAPPINGS.items())
def test_required_odds_api_long_names_map_to_project_names(
    provider_name: str, expected: str
) -> None:
    assert normalize_team_name(provider_name) == expected


def test_mapping_is_case_and_whitespace_insensitive() -> None:
    assert normalize_team_name("  MANCHESTER   city ") == "Man City"
    assert normalize_team_name("nottingham forest") == "Nott'm Forest"


def test_canonical_names_pass_through_unchanged() -> None:
    for name in sorted(CANONICAL_TEAM_NAMES):
        assert normalize_team_name(name) == name


def test_every_alias_targets_a_canonical_name() -> None:
    # A typo in the alias table would silently create an unmappable team.
    for alias, target in PROVIDER_TEAM_ALIASES.items():
        assert target in CANONICAL_TEAM_NAMES, f"{alias} -> {target}"


def test_unknown_name_is_returned_unchanged_not_guessed() -> None:
    # No fuzzy matching: an unknown club must stay visibly unmapped rather than
    # being coerced onto a similar-looking one.
    assert normalize_team_name("Manchester Rovers") == "Manchester Rovers"
    assert is_mapped_team_name("Manchester Rovers") is False


def test_substrings_do_not_accidentally_match() -> None:
    assert normalize_team_name("Man") == "Man"
    assert normalize_team_name("United") == "United"
    assert is_mapped_team_name("United") is False


def test_empty_values_normalize_to_empty_string() -> None:
    assert normalize_team_name("") == ""
    assert normalize_team_name(None) == ""


def test_is_canonical_versus_is_mapped() -> None:
    assert is_canonical_team_name("Man City") is True
    assert is_canonical_team_name("Manchester City") is False
    assert is_mapped_team_name("Manchester City") is True


def test_unmapped_team_names_reports_only_unknowns_sorted() -> None:
    names = [
        "Manchester City",
        "Arsenal",
        "Some New Club",
        "Another New Club",
        "some new club",
    ]
    assert unmapped_team_names(names) == ["Another New Club", "Some New Club"]


def test_the_ten_previously_unmapped_names_are_now_mapped() -> None:
    # These are exactly the names the live shadow run reported as unmapped.
    previously_unmapped = [
        "Brighton and Hove Albion",
        "Coventry City",
        "Hull City",
        "Ipswich Town",
        "Leeds United",
        "Manchester City",
        "Manchester United",
        "Newcastle United",
        "Nottingham Forest",
        "Tottenham Hotspur",
    ]
    assert unmapped_team_names(previously_unmapped) == []
    for name in previously_unmapped:
        assert normalize_team_name(name) in CANONICAL_TEAM_NAMES

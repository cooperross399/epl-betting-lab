from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MANUAL_DIR = DATA_DIR / "manual"
STAGING_DIR = DATA_DIR / "staging"
OUTPUTS_DIR = DATA_DIR / "outputs"
STAGING_PROVENANCE_PATH = STAGING_DIR / "staging_provenance.json"
STAGING_PROVIDER_POLICY_PATH = MANUAL_DIR / "staging_provider_policy.json"

#: How many seasons the model is fitted on, including the one being played.
SEASON_HISTORY_COUNT = 6

#: The month a new Premier League season's code starts counting from. Seasons
#: run August to May, so July is a safe boundary: no season is in progress.
SEASON_ROLLOVER_MONTH = 7


def current_season_code(today: date | None = None) -> str:
    """Football-Data's code for the season being played, e.g. "2627".

    Derived from the date rather than written down. A hardcoded list does not
    fail when it goes stale — it silently keeps fitting the model on seasons
    that ended before the matches it is predicting, and nothing in the output
    says so. Deriving it means the season rolls over on its own each August
    with nobody remembering to do it.
    """
    moment = today or date.today()
    start_year = moment.year if moment.month >= SEASON_ROLLOVER_MONTH else moment.year - 1
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def recent_season_codes(
    count: int = SEASON_HISTORY_COUNT, today: date | None = None
) -> list[str]:
    """The `count` most recent season codes, oldest first, ending with the
    season being played."""
    moment = today or date.today()
    start_year = moment.year if moment.month >= SEASON_ROLLOVER_MONTH else moment.year - 1
    first_year = start_year - (count - 1)
    return [
        f"{year % 100:02d}{(year + 1) % 100:02d}"
        for year in range(first_year, start_year + 1)
    ]


#: Seasons the model is fitted on, oldest first. The last entry is the season
#: being played, and it is expected to be absent or empty before its first
#: match — Football-Data publishes it only once results exist. Every earlier
#: entry is a completed season and must load, so an outage cannot quietly
#: shrink the training set. See `fetch_and_build_dataset`.
DEFAULT_SEASONS = recent_season_codes()
CURRENT_SEASON = DEFAULT_SEASONS[-1]

LEAGUE_CODE = "E0"  # English Premier League on Football-Data.co.uk

# User preference baked in: avoid laying heavy juice unless manually approved.
MAX_DEFAULT_JUICE = -160

#: Longest price the model is trusted to judge. There was a cap on the short
#: side and none on the long side, and the backtest shows why there should be:
#:
#:   +400..+600   83 bets   +6.4% ROI   19.3% win rate
#:   +600..+900   34 bets  -22.3% ROI    8.8% win rate
#:   +900 and up  12 bets  -100.0% ROI   0.0% win rate
#:
#: Twelve claimed chances of roughly one in ten, none of which happened. An
#: independent-Poisson model puts too much mass in the tail of the scoreline
#: distribution, so it overstates exactly these outcomes, and the market's own
#: favourite-longshot bias prices them short on top of that.
#:
#: 600 rather than the ROI-maximising 300: the band from +400 to +600 is
#: profitable, so cutting it would be fitting the threshold to the sample
#: rather than to the failure. Every cap between +300 and +600 is positive in
#: three of four seasons, so this does not balance on the exact number.
MAX_DEFAULT_PRICE = 600
MIN_EDGE = 0.035
BANKROLL_UNIT_DOLLARS = 25.0

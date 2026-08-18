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

#: Seasons the model is fitted on, oldest first. The last entry is the season
#: being played, and it is expected to be absent or empty before its first
#: match — Football-Data publishes it only once results exist. Every earlier
#: entry is a completed season and must load, so an outage cannot quietly
#: shrink the training set. See `fetch_and_build_dataset`.
#:
#: Roll this forward each August. Left alone it does not fail loudly; it just
#: stops learning from the season it is being asked to predict.
DEFAULT_SEASONS = ["2122", "2223", "2324", "2425", "2526", "2627"]
CURRENT_SEASON = DEFAULT_SEASONS[-1]
LEAGUE_CODE = "E0"  # English Premier League on Football-Data.co.uk

# User preference baked in: avoid laying heavy juice unless manually approved.
MAX_DEFAULT_JUICE = -160
MIN_EDGE = 0.035
BANKROLL_UNIT_DOLLARS = 25.0

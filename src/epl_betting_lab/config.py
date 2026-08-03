from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MANUAL_DIR = DATA_DIR / "manual"
STAGING_DIR = DATA_DIR / "staging"
OUTPUTS_DIR = DATA_DIR / "outputs"

DEFAULT_SEASONS = ["2122", "2223", "2324", "2425", "2526"]
LEAGUE_CODE = "E0"  # English Premier League on Football-Data.co.uk

# User preference baked in: avoid laying heavy juice unless manually approved.
MAX_DEFAULT_JUICE = -160
MIN_EDGE = 0.035
BANKROLL_UNIT_DOLLARS = 25.0

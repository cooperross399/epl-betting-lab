# Automated Card Input

Provider-derived odds for the card pipeline. This removes the manual odds-entry step: no price here was typed by hand, and none was invented.

## Status

- Status: **Card input ready**
- Selected window: **2026-08-21 through 2026-08-24**
- Fixtures in window: **10**
- Card input rows written: **50**
- Output: `data/staging/automated_card_current_odds.csv`
- Manual odds entry required: **No**

## Market eligibility

| Market | Status | Fixtures covered | Rows | Usable for picks |
|:-------|:-------|:-----------------|:-----|:-----------------|
| `1x2` | **eligible** | 10/10 | 270 | Yes |
| `total_2_5` | **incomplete** | 8/10 | 80 | No |
| `btts` | **eligible** | 10/10 | 98 | Yes |

- Included markets: **['1x2', 'btts']**
- Excluded markets: **['total_2_5']**
- Unavailable: none
- Incomplete: ['total_2_5']
- Disabled: none

Excluded markets are unavailable, incomplete, or deliberately disabled. They are never reported as passes or no-value calls, and no missing price was invented.

## Reasons

- `1x2`: `1x2` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `total_2_5`: `total_2_5` covers 8 of 10 fixtures in the selected window. The market is excluded rather than partially used.
- `btts`: `btts` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.

## Notes

- Included markets: ['1x2', 'btts']. Excluded: ['total_2_5'].
- 50 row(s) derived from real provider quotes. No price was fabricated and no manual entry is required.

## Safety

- Protected manual files written: **No**
- Odds fabricated: **No**
- Manual odds entry required: **No**
- Bets placed: **No**
- Settlement applied: **No**

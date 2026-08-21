# Automated Card Input

Provider-derived odds for the card pipeline. This removes the manual odds-entry step: no price here was typed by hand, and none was invented.

## Status

- Status: **Card input ready**
- Selected window: **2026-08-21 through 2026-08-24**
- Fixtures in window: **10**
- Card input rows written: **190**
- Output: `data/staging/automated_card_current_odds.csv`
- Manual odds entry required: **No**

## Market eligibility

| Market | Status | Fixtures covered | Rows | Usable for picks |
|:-------|:-------|:-----------------|:-----|:-----------------|
| `1x2` | **eligible** | 10/10 | 330 | Yes |
| `total_2_5` | **eligible** | 10/10 | 170 | Yes |
| `btts` | **eligible** | 10/10 | 166 | Yes |
| `double_chance` | **eligible** | 10/10 | 183 | Yes |
| `draw_no_bet` | **eligible** | 10/10 | 168 | Yes |
| `corners_1x2` | **eligible** | 10/10 | 168 | Yes |
| `corners_total_9_5` | **eligible** | 10/10 | 124 | Yes |
| `corners_total_10_5` | **eligible** | 10/10 | 120 | Yes |

- Included markets: **1x2, total_2_5, btts, double_chance, draw_no_bet, corners_1x2, corners_total_9_5, corners_total_10_5**
- Excluded markets: **none**
- Unavailable: none
- Incomplete: none
- Disabled: none

Excluded markets are unavailable, incomplete, or deliberately disabled. They are never reported as passes or no-value calls, and no missing price was invented.

## Reasons

- `1x2`: `1x2` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `total_2_5`: `total_2_5` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `btts`: `btts` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `double_chance`: `double_chance` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `draw_no_bet`: `draw_no_bet` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `corners_1x2`: `corners_1x2` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `corners_total_9_5`: `corners_total_9_5` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.
- `corners_total_10_5`: `corners_total_10_5` covers all 10 fixtures in the selected window with passing mapping, validation, and freshness.

## Notes

- Included markets: 1x2, btts, corners_1x2, corners_total_10_5, corners_total_9_5, double_chance, draw_no_bet, total_2_5. Excluded: none.
- 190 row(s) derived from real provider quotes. No price was fabricated and no manual entry is required.

## Safety

- Protected manual files written: **No**
- Odds fabricated: **No**
- Manual odds entry required: **No**
- Bets placed: **No**
- Settlement applied: **No**

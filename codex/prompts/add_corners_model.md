# Codex Prompt — Add Corners Model

Read `AGENTS.md` and follow it.

Task:
Add a starter corners model using Football-Data columns:

- `HC` = home corners
- `AC` = away corners

Requirements:

1. Create a model that estimates team corner-for and corner-against tendencies.
2. Add projected home corners, away corners, and total corners for upcoming fixtures.
3. Add support for manual odds markets:
   - `team_corners`
   - `match_corners`
4. Add tests for odds conversion and basic corner projection behavior.
5. Add dashboard output.
6. Do not create fake odds. Use the manual odds CSV format.
7. Run compile checks and tests.

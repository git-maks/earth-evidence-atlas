# Repository instructions

**Earth Evidence Atlas** – NASA Space Apps Challenge 2026 entry (team PollubAI, challenge "Be An Earth System Trend Detective!"). The FastAPI backend (`atlas/`) computes trends and significance from NASA data cubes (`data/cubes/*.nc`). The vanilla-JS frontend (`web/`, no build step) has Globe (MapLibre), Detective (Leaflet + Plotly), False alarms (simulation), Resilience and Methods views. The pitch deck is a separate static site in `presentation/` (see its README).

## Commands

```bash
scripts/run.sh                 # server on 127.0.0.1:8765
scripts/run.sh 8771            # your own test server on another port
.venv/bin/python -m pytest -q  # all tests must pass before you commit
.venv/bin/python -m scripts.build_data [vars] [--region R] [--force]   # rebuild data cubes
cd presentation && python3 publish.py                                  # build the deck's Pages artifact
```

Python 3.11. Keep the frontend build-free. Python changes need a server restart.

## Project rules

- **No AI-generated numbers or scientific claims in the app.** All values come from the cited NASA data; the Detective answers are fixed templates (`atlas/answers.py`), not LLM text. Never state causes of a trend.
- UI text in **English**, short. Use the en dash `–`, not the em dash. No emoji in the UI; icons come from `web/icons.svg` (`<use href="/static/icons.svg#i-NAME">`).
- One tooltip style for everything: `showTip()` / `data-tip` in `web/app.js`; charts go through `plot()`.
- Keep WCAG AA contrast (4.5:1) in light and dark mode; keep layouts working from 390 px to 1440 px wide.
- Licences: list every external asset (data, fonts, libraries, icons) in `README.md`.
- Scientific values in `presentation/` come from `presentation/evidence.json`; never invent numbers or causal claims.

## Data

`data/cubes/` (prebuilt NetCDF cubes) and `data/custom_regions.json` are tracked. Raw downloads (`data/raw`), logs and backups are not; rebuild with `scripts/build_data.py`.

## Public commit identity

Use the human maintainer identity `git-maks <161726800+git-maks@users.noreply.github.com>` for authors and committers. Do not add tool-name signatures or taglines to commit messages. See CONTRIBUTING.md.

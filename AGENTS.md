# AGENTS.md – rules for every coding agent working on this repo

Read this before changing anything. It applies to all agents (Claude Code, Codex, others) and to people.
Several agents work on this folder **at the same time**, for different team members. The goal is that
nobody loses work and nobody breaks someone else's test.

## Project in one paragraph

**Earth Evidence Atlas** – NASA Space Apps Challenge 2026 entry (team PollubAI, challenge "Be An Earth
System Trend Detective!"). FastAPI backend (`atlas/`) computes trends and significance from NASA data cubes
(`data/cubes/*.nc`). Vanilla-JS frontend (`web/`, no build step): Globe (MapLibre), Detective (Leaflet + Plotly),
False alarms (simulation), Methods. Handoff and status: `README.md` (Polish). Challenge, rules, deadlines: `formalne/`.

## Commands

```bash
scripts/run.sh                 # shared server on 127.0.0.1:8765 (see "Ports")
scripts/run.sh 8771            # your own test server on another port
.venv/bin/python -m pytest -q  # all tests must pass before you commit
.venv/bin/python -m scripts.build_data [vars] [--region R] [--force]   # (re)build data cubes
```

Python 3.11 in `.venv` (do not recreate it). Node is too old for a JS build: keep the frontend build-free.

## Working side by side (most important)

1. **Small, exact edits.** Re-read a file right before you edit it and change only the lines you need.
   Never rewrite a whole file from an old copy, never "restore" a file from your memory or a backup.
2. **Never undo changes you did not make.** If something unexpected changed, leave it and tell your user.
3. **Commit your own work early and often** (see "Git"), so a lost edit can always be recovered.
4. **Before a bigger change** (new module, renaming, moving code, changing an API response), add a line to
   "Who is working on what" below and check nobody else holds that area.
5. **Do not delete or regenerate shared data** (`data/cubes`, `data/custom_regions.json`, `data/raw`)
   unless your user asked for exactly that.
6. **Server:** do not kill or restart the shared server on port 8765 unless you are its owner. Test on your own port.
   The server has no auto-reload: Python changes need a restart of *your* server only.

### Ports

| Port | Use |
|---|---|
| 8765 | shared server (the one people open through the SSH tunnel) – restart only by agreement |
| 8771 | Claude Code (Maks) |
| 8772–8779 | free – write your agent here when you take one |

### Who is working on what

Add a line when you start a larger task and remove it when you are done.

| Who (person / agent) | Area / files | Since |
|---|---|---|
| Maks / Claude Code | Detective answers (`atlas/answers.py`), UI polish (`web/style.css`) | 2026-11-15 |

## Git

- The repo was initialised on 2026-11-15. `data/`, `.venv/`, `tmp/` are **not** in git (data is rebuilt with
  `scripts/build_data.py` or copied separately for deployment).
- The machine's global git identity belongs to one person. **Commit with your own identity**, e.g.
  `git -c user.name="<name>" -c user.email="<email>" commit ...`, and say in the message which agent made it.
- Commit only files you changed (`git add <paths>`, not `git add -A` when others have work in progress).
- Do not rewrite history (`reset --hard`, `rebase`, `push --force`) and do not switch branches in this folder:
  everyone shares this one working tree. Use a separate `git worktree` if you need a branch.

## Project rules

- **AI disclosure is required by the hackathon rules.** Every new code file starts with a comment saying it was
  written with an AI assistant (see existing headers). AI-generated images/videos need a visible watermark.
- **No AI-generated numbers or scientific claims in the app.** All values come from the cited NASA data;
  the Detective answers are fixed templates (`atlas/answers.py`), not LLM text. Never state causes of a trend.
- UI text in **English** (submission requirement), short. Docs for the team may be Polish.
- Use the en dash `–`, not the em dash. No emoji in the UI; icons come from `web/icons.svg` (`<use href="/static/icons.svg#i-NAME">`).
- One tooltip style for everything: `showTip()` / `data-tip` in `web/app.js`; charts go through `plot()`.
- Keep WCAG AA contrast (4.5:1) in light and dark mode; keep layouts working from 390 px to 1440 px wide.
- Licences: list every external asset (data, fonts, libraries, icons) in `README.md`.

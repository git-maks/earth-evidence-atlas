# Earth Evidence Atlas – PollubAI presentation

Static seven-slide English pitch, a frozen evidence snapshot and a matching PDF for the **Earth Evidence Atlas** project (NASA Space Apps Challenge 2026, team PollubAI). It lives in the `presentation/` folder of the main repository, next to the application code.

- Published site: **https://git-maks.github.io/earth-evidence-atlas/**.
- Repository: **https://github.com/git-maks/earth-evidence-atlas** (application in the repository root, this deck in `presentation/`).
- Local entry point: `index.html`; submission PDF: `earth-evidence-atlas.pdf`.
- The live demo server shown in the recorded evidence has been taken offline; the deck keeps the frozen, verified results.

**Hosting:** GitHub Pages uses **GitHub Actions** as its source. The workflow in `.github/workflows/pages.yml` runs `publish.py` in this folder and deploys only `presentation/_site/`. It never starts the application, reads its data cubes or calls NASA.

## Local build and preview

Python **3.11+** is sufficient. Run from the `presentation/` folder:

```bash
python3 publish.py
python3 -m http.server 8773 --directory _site
```

Open http://127.0.0.1:8773/. Alternatively, open `index.html` directly. Fonts, images, charts, scripts and the evidence record are embedded in the HTML, so the slides work offline; source links and the live demo require internet access.

`publish.py` builds `index.html`, validates the frozen snapshot and verified artifacts, then copies the public files into `_site/`. The output contains the HTML, current seven-page PDF, evidence JSON, preview and verification records. Development scripts, source inputs and historical Canva exports are excluded. `.nojekyll` also permits serving the root as plain static files if you later choose deployment from a branch instead of Actions.

The folder is self-contained: building and publishing need nothing from the application code or its data. The application is only needed to refresh evidence and figures (`capture.py`, `render_assets.py`, `capture_cover.py`).

## Using the deck

- Arrow keys, Space and Home/End navigate; **F** toggles fullscreen.
- **D / Details & sources** opens challenge coverage, implemented features, sources, limitations and reproduction details.
- **Reading view** shows all slides with a layout suitable for phones.
- Slide 4 switches between recorded examples of temporal memory, outliers and season selection. Printing uses the temporal-memory example.
- Slide 7 shows the three supplied team portraits and fixed names/roles. The published jury deck has no editing or upload controls.
- **Print / PDF** prints seven slides. Detail panels do not add pages.

The PDF contains seven English slides including the title, matching the supplied local submission/judging guides. Updating the presentation is not a new audit of the competition rules. No submission has been sent automatically.

The team is listed alphabetically by surname: **Maks Kozieł – Platform & Reliability Lead; Jan Kwapiński – Science & Data Lead; Maja Sykuła – Product & Experience Lead**. Responsibilities follow the team's confirmed allocation.

## Edit and verify

Edit `deck.template.html`, then run:

```bash
python3 build.py
python3 /path/to/presentation/verify.py
python3 publish.py
```

`verify.py` needs the optional packages in `requirements-dev.txt`, Google Chrome at `/usr/bin/google-chrome`, and Poppler's `pdfinfo` and `pdftotext`. On the shared project machine the existing environment already supplies the Python packages:

```bash
../.venv/bin/python verify.py
```

The full browser check regenerates the PDF, preview and `validation.json`. It checks seven slides/pages, footer clearance, offline rendering with zero remote requests, evidence-download equality, three laboratory examples, detail panels, fixed team names/roles, three embedded portraits, absence of authoring controls, the SVG favicon and the 390 px reading view. Commit the regenerated HTML/PDF/verification record together. Publication rejects artifacts changed since this check, preventing a stale PDF from silently accompanying updated HTML.

Normal verification checks the bundled snapshot; it does not claim that a separately evolving application still matches that snapshot. To additionally check every captured application-source hash, pass `--project-root /path/to/application`. This strict check will fail after relevant application changes until the evidence and figures are refreshed.

## Refresh scientific evidence and screenshots

This optional maintenance step requires a separate application checkout, its existing Python environment and a freshly started private test API. It is never run during Pages deployment. Do not restart the shared application or public demo server.

Example from the site repository, using a private server on port 8776:

```bash
APP_PYTHON=../.venv/bin/python
APP_ROOT=..
"$APP_PYTHON" capture.py --project-root "$APP_ROOT" --base-url http://127.0.0.1:8776
"$APP_PYTHON" render_assets.py --project-root "$APP_ROOT" --base-url http://127.0.0.1:8776
python3 build.py
"$APP_PYTHON" verify.py --project-root "$APP_ROOT"
python3 publish.py
```

`capture.py` reads API responses only. It does not download data or rebuild cubes. It records parameters, the application Git revision and source hashes, and rejects capture if sources change during the run. It also executes the actual client `addSpikes()` function with Node. `render_assets.py` uses the application's vendored Plotly and the real running interface to generate figures/screenshots; it checks the displayed results against the frozen evidence.

`inputs/` supplies independent copies of the font, icon sprite, challenge brief and resource index. `inputs/provenance.json` records their original application paths and SHA-256 hashes. Keep that manifest consistent if intentionally updating these inputs. Public-demo availability is recorded separately in `deployment-check.json`; refresh that check when the deployment changes.

## Evidence and scientific limits

- `evidence.json` records 13 real analyses, the validation table, a Resilience response and explicitly synthetic experiments. The same record is embedded in and downloadable from the HTML.
- The main example is POWER/MERRA-2 air temperature in Central Europe, 1981–2025: **+0.509551 °C/decade**, 95% CI **[0.254052, 0.765551]**. Direction agrees in 133/136 tested windows; 45 have that direction and p < 0.05. Windows overlap and are not independent replications. GISTEMP over the same period gives +0.509067 °C/decade.
- The synthetic temporal-memory experiment uses 200 runs, 10 years, φ = 0.7, seed 1000: 83 naive alarms versus 5 with the current monthly/yearly memory checks (41.5% versus 2.5%). Error bars are Wilson 95% intervals; 5% is a reference level. These are not Earth observations.
- The two-outlier exercise records the current client function separately: 5 years, seed 15, φ = 0.25, σ = 0.35. The older mean-step exercise is historical.
- Eight analytical series cover MODIS, POWER/MERRA-2, GPCP and GISTEMP. POWER series share provenance; eight series do not mean eight independent sources. Native-resolution MODIS quality screening precedes aggregation; NDVI retains good and marginal pixels. Limitations include orbital drift, approximate month assignment, reanalysis dependence and spatial resolution. Comparisons do not establish causes or full independence.
- Actual UI captures include Globe, area selection, Detective, the period matrix, laboratory and Resilience. Resilience supports regional screening for civilian and defense infrastructure; the deck presents implemented functions separately from roadmap ideas.
- The public Resilience UI was checked with four cards using its older-API compatibility fallback; the dedicated public `/api/resilience` returned 404 at that time. The recorded availability check is time-specific. The static presentation stays viewable if the live application is unavailable.

## Assets, credits and historical exports

Project screenshots and figures come from the real application and frozen responses. Figures are Plotly SVG exports, not fabricated results. Original data citations and caveats remain in the embedded source panel and `evidence.json`.

- NASA data and imagery: [MODIS](https://modis.gsfc.nasa.gov/), [NASA POWER](https://power.larc.nasa.gov/), [MERRA-2](https://gmao.gsfc.nasa.gov/reanalysis/MERRA-2/), [GISTEMP](https://data.giss.nasa.gov/gistemp/), [GPCP V2.3](https://psl.noaa.gov/data/gridded/data.gpcp.html), [NASA GIBS](https://www.earthdata.nasa.gov/engage/open-data-services-and-software/earthdata-developer-portal/gibs-api). Product-specific citations/licenses are retained in the evidence catalog.
- [Plotly.js](https://github.com/plotly/plotly.js): MIT; used to export the figures, with no runtime dependency in the deck.
- [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/): public domain; boundaries visible in screenshots.
- Yale Bright Star Catalogue via [d3-celestial](https://github.com/ofrohn/d3-celestial): BSD-3-Clause for the package; star background visible in screenshots.
- `inputs/nasalization.ttf`: existing team-supplied font, internal family “Nasa”, CSS alias “Nasalization”; embedded metadata “Freeware by Ray Larabie 1997”.
- `inputs/icons.svg`: icon sprite supplied by the project team.
- `inputs/challenge-brief.txt` and `inputs/challenge-resources.json`: supplied reference copies with original source URLs/provenance, retained to reproduce the details panel.
- Optional maintenance tools: [Playwright](https://github.com/microsoft/playwright-python) (Apache-2.0), [Pillow](https://github.com/python-pillow/Pillow) (HPND). Neither is needed to build/deploy the frozen site.


The jury edition embeds the team-supplied portraits stored in `assets/`. `favicon.svg` uses the SVG supplied by the team, credited to Font Awesome Pro 7.3.1 / Fonticons, Inc. (commercial license), on the same dark tile and light foreground as the application favicon. Its original attribution is retained. Both portraits and favicon are embedded for offline viewing.

Cover refresh: `python capture_cover.py` captures only the actual MODIS daytime land-surface-temperature globe at 2× device resolution, with a square frame and no enlarged application UI. `capture-validation.json` records the selected imagery/time and file hash separately from the frozen scientific figures. Slides 2 and 6 display the complete screenshots with `object-fit: contain`. After a cover refresh, run `build.py`, `verify.py` and `publish.py` as usual.

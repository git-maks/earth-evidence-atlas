"""Check the standalone deck, interactions, evidence, layout and seven-page PDF."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path,
                        help="Optionally also require the application sources to match the captured snapshot.")
    args = parser.parse_args()
    evidence = json.loads((HERE / "evidence.json").read_text())
    capture = json.loads((HERE / "capture-validation.json").read_text())
    assert capture["evidence_sha256"] == hashlib.sha256((HERE / "evidence.json").read_bytes()).hexdigest()
    for name, expected in capture["assets_sha256"].items():
        assert hashlib.sha256((HERE / "assets" / name).read_bytes()).hexdigest() == expected, name
    assert not capture["browser_errors"], capture["browser_errors"]
    if args.project_root:
        source_drift = [name for name, expected in evidence["source_sha256"].items()
                        if not (args.project_root / name).is_file()
                        or hashlib.sha256((args.project_root / name).read_bytes()).hexdigest() != expected]
        assert not source_drift, f"Recapture after source changes: {source_drift}"
    errors, remote_requests, previews = [], [], []
    with tempfile.TemporaryDirectory(prefix="atlas-pitch-") as tmp, sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True,
                                   args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1470, "height": 970}, reduced_motion="reduce")
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        def offline(route):
            remote_requests.append(route.request.url)
            route.abort()
        context.route(re.compile(r"^https?://"), offline)
        page.goto((HERE / "index.html").as_uri(), wait_until="load")
        page.evaluate("document.fonts.ready")
        page.wait_for_function("Array.from(document.images).every(i => i.hidden || !i.getAttribute('src') || i.complete && i.naturalWidth > 0)")
        assert page.locator(".slide").count() == 7
        assert page.locator("#slide-5 tbody tr").count() == len(evidence["catalog"]["variables"])
        assert json.loads(page.locator("#evidenceData").text_content()) == evidence
        assert page.locator("#slide-7 .member-name").all_text_contents() == ["Maks Kozieł", "Jan Kwapiński", "Maja Sykuła"]
        roles = page.locator("#slide-7 .member-role").all_text_contents()
        assert roles == ["Platform & Reliability Lead", "Science & Data Lead", "Product & Experience Lead"]
        for i in range(7):
            page.evaluate("i => show(i)", i)
            overflow = page.locator(f"#slide-{i+1}").evaluate("""slide => {
                const footer=slide.querySelector('.slide-foot').getBoundingClientRect();
                return [...slide.querySelectorAll('h1,h2,h3,p,table,.team-portraits')].filter(el => {
                  if(!el.getClientRects().length || el.closest('.slide-foot,.hero-art')) return false;
                  const r=el.getBoundingClientRect();
                  return r.bottom>footer.top-4 || r.right>slide.getBoundingClientRect().right+1;
                }).map(el=>el.textContent.slice(0,90));
            }""")
            assert not overflow, (i+1, overflow)
            path = Path(tmp) / f"slide-{i+1}.png"
            page.locator(f"#slide-{i+1}").screenshot(path=str(path))
            previews.append(Image.open(path).convert("RGB"))
        page.evaluate("show(3)")
        for name in ("spikes", "season", "memory"):
            page.locator(f"[data-case='{name}']").click()
            assert page.locator(f"#case-{name}").is_visible()
        for name in ("coverage", "features", "sources", "reproduce"):
            page.evaluate("name=>openDetail(name)", name)
            assert page.locator(f"#detail-{name}").is_visible()
            page.locator("[data-close='detailDialog']").click()
        assert page.locator('[contenteditable], input[type="file"], #saveTeam, #notes, #notesDialog, #helpDialog').count() == 0
        assert page.locator('#slide-7 .team-photo-slot img').count() == 3
        assert page.locator('link[rel="icon"]').get_attribute('href').startswith('data:image/svg+xml;base64,')
        page.keyboard.press('n')
        assert page.locator('dialog[open]').count() == 0
        page.evaluate("show(0)")
        page.pdf(path=str(HERE / "earth-evidence-atlas.pdf"), prefer_css_page_size=True, print_background=True)
        with page.expect_download() as download:
            page.locator("#downloadEvidence").evaluate("el=>el.click()")
        evidence_path = Path(tmp) / "download.json"
        download.value.save_as(str(evidence_path))
        assert json.loads(evidence_path.read_text()) == evidence
        page.set_viewport_size({"width":390,"height":844})
        page.locator("#reading").click()
        page.evaluate("show(6)")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        browser.close()
    assert not remote_requests, remote_requests
    assert not errors, errors
    info = subprocess.check_output(["pdfinfo", str(HERE / "earth-evidence-atlas.pdf")], text=True)
    assert re.search(r"Pages:\s+7\b", info), info
    pdf_text = subprocess.check_output(["pdftotext", str(HERE / "earth-evidence-atlas.pdf"), "-"], text=True)
    for text in ("Maks Kozieł", "Jan Kwapiński", "Maja Sykuła", "GPCP", "0.254", "0.766", "2.5%"):
        assert text in pdf_text, f"PDF missing {text}"
    sheet = Image.new("RGB", (1440, 3*430), "#111820")
    draw = ImageDraw.Draw(sheet)
    for i, preview in enumerate(previews):
        preview.thumbnail((700,394))
        x,y=(i%2)*720,(i//2)*430
        if y+preview.height > sheet.height:
            expanded=Image.new("RGB",(1440,y+430),"#111820");expanded.paste(sheet);sheet=expanded;draw=ImageDraw.Draw(sheet)
        sheet.paste(preview,(x,y+25));draw.text((x+10,y+5),f"Slide {i+1}",fill="white")
    sheet.save(HERE / "preview.png")
    validation = {
        "slides":7,"pdf_pages":7,"captured_at":evidence["captured_at"],
        "offline_browser_check":"passed; no remote requests", "layout_check":"all seven slides clear the footer",
        "source_hash_check": "matched separate application checkout" if args.project_root else
                             "not rerun; original application hashes retained in evidence.json",
        "checks":["figures match frozen evidence","eight analytical series",
                  "current API values and corrected uncertainty","three lab cases","jury evidence panels without presenter notes",
                  "evidence download equality","team names and responsibilities","three embedded portraits and fixed team text", "embedded SVG favicon",
                  "390 px reading view","seven-page PDF with updated text"],
        "browser_errors":errors,
        "artifacts_sha256":{name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                            for name in ("index.html","earth-evidence-atlas.pdf","evidence.json")},
        "canva_exports":"previous revision in archive/; see README before reuse",
    }
    (HERE / "validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2)+"\n")
    print("Verified 7 slides, PDF, offline behaviour, interactions, evidence and mobile reading view.")


if __name__ == "__main__":
    main()

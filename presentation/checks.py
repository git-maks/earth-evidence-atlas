"""Validate the frozen evidence and the self-contained HTML using only Python's stdlib."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC_FILES = (
    "index.html", "earth-evidence-atlas.pdf", "evidence.json", "preview.png",
    "validation.json", "capture-validation.json", "deployment-check.json", ".nojekyll", "favicon.svg",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_snapshot(root: Path = HERE):
    evidence_path = root / "evidence.json"
    evidence = json.loads(evidence_path.read_text())
    capture = json.loads((root / "capture-validation.json").read_text())
    assert capture["evidence_sha256"] == sha256(evidence_path), "Figures must match evidence.json."
    assert not capture["browser_errors"], capture["browser_errors"]
    for name, expected in capture["assets_sha256"].items():
        assert sha256(root / "assets" / name) == expected, f"Figure changed: {name}"
    provenance = json.loads((root / "inputs/provenance.json").read_text())
    for name, origin in provenance.items():
        assert sha256(root / "inputs" / name) == origin["sha256"], f"Build input changed: {name}"
    assert evidence["source_sha256"], "Keep the captured application's provenance."
    return evidence


class DeckParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.slides = 0
        self.ids = set()
        self.references = []
        self.evidence_text = ""
        self.in_evidence = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.slides += "slide" in attrs.get("class", "").split()
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "script" and attrs.get("id") == "evidenceData":
            self.in_evidence = True
        # Navigation links may point at external sources; media and scripts must be embedded.
        for attribute in ("src", "poster", "srcset"):
            if attrs.get(attribute):
                assert attrs[attribute].startswith("data:"), (tag, attribute, attrs[attribute])
        if tag in ("link", "use") and attrs.get("href"):
            assert attrs["href"].startswith(("#", "data:")), (tag, attrs["href"])
        if tag == "a" and attrs.get("href", "").startswith("#"):
            self.references.append(attrs["href"][1:])

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_evidence = False

    def handle_data(self, data):
        if self.in_evidence:
            self.evidence_text += data


def check_artifacts(root: Path = HERE):
    evidence = json.loads((root / "evidence.json").read_text())
    validation = json.loads((root / "validation.json").read_text())
    assert validation["slides"] == validation["pdf_pages"] == 7
    assert validation["captured_at"] == evidence["captured_at"]
    assert not validation["browser_errors"], validation["browser_errors"]
    for name in ("index.html", "earth-evidence-atlas.pdf", "evidence.json"):
        assert sha256(root / name) == validation["artifacts_sha256"].get(name), (
            f"{name} changed since browser/PDF verification. Run build.py and verify.py first."
        )
    html = (root / "index.html").read_text()
    assert "@@" not in html, "Unresolved template placeholder."
    assert "data:font/ttf;base64," in html, "Font must be embedded."
    deck = DeckParser()
    deck.feed(html)
    assert deck.slides == 7, deck.slides
    assert json.loads(deck.evidence_text) == evidence, "Embedded evidence differs from downloadable JSON."
    assert all(target in deck.ids for target in deck.references if target), "Broken slide link."
    return deck


if __name__ == "__main__":
    check_snapshot()
    check_artifacts()
    print("Checked frozen inputs, figure hashes, seven slides, offline assets and verified HTML/PDF hashes.")


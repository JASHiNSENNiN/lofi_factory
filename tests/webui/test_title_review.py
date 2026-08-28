"""
Unit tests for _read_title_variants() (webui/app.py), the pure-data helper
behind the "Upload with title…" pre-publish review dialog on a completed
"Render only" job (see _upload_with_title_dialog()). Parses a seo_*.json
file's already-generated title_variants so a human can pick/edit one before
uploading -- the dialog itself needs a live NiceGUI context and isn't unit
tested here, same as the existing bandit-posteriors panels.
"""
import json

from webui.app import _read_title_variants


def test_read_title_variants_reads_variants_and_strategies(tmp_path):
    seo_path = tmp_path / "seo_20260824_000000.json"
    seo_path.write_text(json.dumps({
        "title": "lofi hip hop · minecraft cozy · study, focus, relax — 1 hour",
        "title_variants": [
            "lofi hip hop · minecraft cozy · study, focus, relax — 1 hour",
            "lofi · 6am alarm focus mix — study, chill · 1 hour",
            "1 hour lofi hip hop mix for coding",
        ],
        "title_variant_strategies": ["benefit_list", "statement", "spec_led"],
    }))
    title, variants, strategies = _read_title_variants(str(seo_path))
    assert title == "lofi hip hop · minecraft cozy · study, focus, relax — 1 hour"
    assert len(variants) == 3
    assert strategies == ["benefit_list", "statement", "spec_led"]


def test_read_title_variants_falls_back_to_chosen_title_only(tmp_path):
    # Older seo_*.json predating title_variants being logged.
    seo_path = tmp_path / "seo_old.json"
    seo_path.write_text(json.dumps({"title": "lofi beats for studying"}))
    title, variants, strategies = _read_title_variants(str(seo_path))
    assert title == "lofi beats for studying"
    assert variants == ["lofi beats for studying"]
    assert strategies == []


def test_read_title_variants_missing_file_returns_empty():
    title, variants, strategies = _read_title_variants("/nonexistent/seo.json")
    assert title == ""
    assert variants == []
    assert strategies == []

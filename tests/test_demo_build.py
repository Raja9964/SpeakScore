import json
import re

import pytest

from scripts.build_demo import normalize_base_path, write_pages
from speakscore.web import create_app

WHEELS = ["speakscore-1.0.0-py3-none-any.whl", "vaderSentiment-3.3.2-py2.py3-none-any.whl"]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    write_pages(out, WHEELS, "/SpeakScore")
    return out


def engine_config(html: str) -> dict:
    match = re.search(r'<script id="engine-config" type="application/json">(.*?)</script>', html)
    return json.loads(match.group(1))


def test_demo_page_uses_the_base_path(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="/SpeakScore/static/style.css"' in html
    assert 'src="/SpeakScore/static/pyodide-scorer.js"' in html
    assert 'src="/SpeakScore/static/app.js"' in html
    assert "/api/" not in html


def test_demo_page_has_banner_and_engine(site):
    html = (site / "index.html").read_text(encoding="utf-8")
    assert "the Python engine runs in your browser (WebAssembly)" in html
    assert 'id="engine-status"' in html
    config = engine_config(html)
    assert config["wheels"] == [f"/SpeakScore/wheels/{name}" for name in WHEELS]
    assert config["pyodide"].startswith("https://cdn.jsdelivr.net/pyodide/v")
    assert config["max_chars"] == 20_000


def test_static_files_and_404_fallback(site):
    copied = {path.name for path in (site / "static").iterdir()}
    assert {"app.js", "pyodide-scorer.js", "style.css", "favicon.svg"} <= copied
    fallback = (site / "404.html").read_text(encoding="utf-8")
    assert 'location.replace("/SpeakScore/" + location.search + location.hash)' in fallback


def test_flask_page_has_no_demo_parts():
    html = create_app({"TESTING": True}).test_client().get("/").get_data(as_text=True)
    assert "Live demo" not in html
    assert "pyodide-scorer.js" not in html
    assert 'data-sample="strong"' in html


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", ""), ("/", ""), ("/SpeakScore", "/SpeakScore"), ("SpeakScore/", "/SpeakScore")],
)
def test_base_path_is_normalized(raw, expected):
    assert normalize_base_path(raw) == expected


def test_odd_base_path_is_rejected():
    with pytest.raises(ValueError):
        normalize_base_path('/a"b')

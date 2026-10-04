"""Build the static GitHub Pages demo: the web UI plus the wheels Pyodide installs in the browser.

Usage: python -m scripts.build_demo --out _site --base-path /SpeakScore
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from speakscore.web import create_app

ROOT = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://github.com/Raja9964/SpeakScore"
PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.29.5/full/"
BROWSER_DEPENDENCY = "vaderSentiment"

# Pages serves this for unknown paths: send visitors to the demo and keep any #sample link.
NOT_FOUND_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SpeakScore</title>
  <script>location.replace("{home}" + location.search + location.hash);</script>
</head>
<body>
  <p>Nothing here. Go to the <a href="{home}">SpeakScore demo</a>.</p>
</body>
</html>
"""


def normalize_base_path(base_path: str) -> str:
    base = base_path.strip().strip("/")
    if base and not re.fullmatch(r"[\w.-]+(/[\w.-]+)*", base):
        raise ValueError(f"unexpected base path {base_path!r}")
    return f"/{base}" if base else ""


def pinned(name: str) -> str:
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.lower().startswith(f"{name.lower()}=="):
            return line.strip()
    raise SystemExit(f"{name} must be pinned with == in requirements.txt")


def build_wheels(dest: Path) -> list[str]:
    pip = [sys.executable, "-m", "pip", "--disable-pip-version-check"]
    download = ["download", "--no-deps", "--only-binary=:all:", "--dest", str(dest)]
    subprocess.run([*pip, "wheel", "--no-deps", "--wheel-dir", str(dest), str(ROOT)], check=True)
    subprocess.run([*pip, *download, pinned(BROWSER_DEPENDENCY)], check=True)
    return sorted(path.name for path in dest.glob("*.whl"))


def write_pages(out: Path, wheels: list[str], base_path: str = "") -> None:
    base = normalize_base_path(base_path)
    app = create_app()
    demo = {
        "source_url": SOURCE_URL,
        "engine": {
            "pyodide": PYODIDE_URL,
            "wheels": [f"{base}/wheels/{name}" for name in wheels],
            "max_chars": app.config["MAX_TRANSCRIPT_CHARS"],
        },
    }
    # Render the real index view, as if the app were mounted under the Pages base path.
    app.context_processor(lambda: {"demo": demo})
    response = app.test_client().get("/", base_url=f"https://pages.invalid{base}/")
    if response.status_code != 200:
        raise SystemExit(f"rendering the page failed with HTTP {response.status_code}")

    out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "speakscore" / "static", out / "static", dirs_exist_ok=True)
    (out / "index.html").write_text(response.get_data(as_text=True), encoding="utf-8")
    (out / "404.html").write_text(NOT_FOUND_PAGE.format(home=f"{base}/"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the static SpeakScore demo.")
    parser.add_argument("--out", type=Path, default=ROOT / "_site", help="output folder")
    parser.add_argument("--base-path", default="", help="URL path the site is served from")
    args = parser.parse_args()
    base = normalize_base_path(args.base_path)

    for stale in ("static", "wheels"):
        shutil.rmtree(args.out / stale, ignore_errors=True)
    wheels = build_wheels(args.out / "wheels")
    write_pages(args.out, wheels, base)
    print(f"Demo written to {args.out} with {', '.join(wheels)}")


if __name__ == "__main__":
    main()

import json
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def load_sample(name: str) -> tuple[str, float]:
    manifest = json.loads((SAMPLES_DIR / "samples.json").read_text(encoding="utf-8"))
    entry = next(e for e in manifest if e["file"] == f"{name}.txt")
    return (SAMPLES_DIR / entry["file"]).read_text(encoding="utf-8"), entry["duration_seconds"]

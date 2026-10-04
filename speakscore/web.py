import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flask import Blueprint, Flask, current_app, jsonify, render_template, request
from werkzeug.exceptions import BadRequest, HTTPException

from . import __version__
from .engine import InvalidInput, Scorer
from .rubric import DEFAULT_RUBRIC_PATH, load_rubric

PROJECT_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)

api = Blueprint("api", __name__, url_prefix="/api")


def create_app(overrides: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        RUBRIC_PATH=str(DEFAULT_RUBRIC_PATH),
        SAMPLES_DIR=str(PROJECT_DIR / "samples"),
        MAX_TRANSCRIPT_CHARS=20_000,
        MAX_CONTENT_LENGTH=256 * 1024,
    )
    # SPEAKSCORE_RUBRIC_PATH, SPEAKSCORE_MAX_TRANSCRIPT_CHARS, ... override the defaults.
    app.config.from_prefixed_env("SPEAKSCORE")
    if overrides:
        app.config.update(overrides)
    app.json.sort_keys = False

    scorer = Scorer(load_rubric(app.config["RUBRIC_PATH"]))
    app.extensions["speakscore"] = scorer
    samples = _load_samples(Path(app.config["SAMPLES_DIR"]))

    @app.get("/")
    def index():
        return render_template(
            "index.html", rubric=scorer.rubric, samples=samples, version=__version__
        )

    app.register_blueprint(api)
    app.register_error_handler(HTTPException, _http_error)
    app.register_error_handler(Exception, _unexpected_error)
    return app


@api.get("/health")
def health():
    rubric = current_app.extensions["speakscore"].rubric
    return {"status": "ok", "version": __version__, "rubric": rubric.name}


@api.post("/score")
def score():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise BadRequest("Request body must be a JSON object with a 'transcript' field.")

    transcript = payload.get("transcript")
    if not isinstance(transcript, str):
        raise BadRequest("'transcript' is required and must be a string.")
    limit = current_app.config["MAX_TRANSCRIPT_CHARS"]
    if len(transcript) > limit:
        raise BadRequest(f"'transcript' must be at most {limit} characters.")

    scorer: Scorer = current_app.extensions["speakscore"]
    try:
        report = scorer.score(transcript, payload.get("duration_seconds"))
    except InvalidInput as exc:
        raise BadRequest(str(exc)) from exc
    return jsonify(report.to_dict())


def _http_error(exc: HTTPException):
    if not request.path.startswith("/api/"):
        return exc
    return jsonify(error=exc.description), exc.code


def _unexpected_error(exc: Exception):
    log.exception("Unhandled error on %s", request.path)
    if not request.path.startswith("/api/"):
        return "Internal server error", 500
    return jsonify(error="Internal server error."), 500


def _load_samples(directory: Path) -> list[dict[str, Any]]:
    manifest = directory / "samples.json"
    if not manifest.is_file():
        return []
    samples = []
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        path = directory / entry["file"]
        if path.is_file():
            samples.append(
                {
                    "label": entry["label"],
                    "duration_seconds": entry.get("duration_seconds"),
                    "transcript": path.read_text(encoding="utf-8").strip(),
                }
            )
    return samples

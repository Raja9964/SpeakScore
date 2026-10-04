// Static demo only: runs the speakscore wheel on Pyodide so nothing leaves the browser.
(() => {
  const config = JSON.parse(document.getElementById("engine-config").textContent);
  const status = document.getElementById("engine-status");
  const message = document.getElementById("engine-message");

  // Same checks and messages as the Flask endpoint.
  const ENTRY = `
import json

from speakscore import InvalidInput, score_transcript


def score(payload, max_chars):
    data = json.loads(payload)
    transcript = data.get("transcript")
    if not isinstance(transcript, str):
        return json.dumps({"error": "'transcript' is required and must be a string."})
    if len(transcript) > max_chars:
        return json.dumps({"error": f"'transcript' must be at most {max_chars} characters."})
    try:
        report = score_transcript(transcript, data.get("duration_seconds"))
    except InvalidInput as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps(report.to_dict())


score
`;

  const scorer = { status: "loading" };

  const setStatus = (state, text) => {
    scorer.status = state;
    status.dataset.state = state;
    message.textContent = text;
  };

  const boot = async () => {
    const { loadPyodide } = await import(`${config.pyodide}pyodide.mjs`);
    const pyodide = await loadPyodide({ indexURL: config.pyodide });
    setStatus("loading", "Installing the speakscore package\u2026");
    const wheels = config.wheels.map((path) => new URL(path, location.href).href);
    await pyodide.loadPackage(wheels, { messageCallback: () => {} });
    const score = pyodide.runPython(ENTRY);
    score(JSON.stringify({ transcript: "Hello, my name is Asha." }), config.max_chars);
    const version = pyodide.runPython("import sys; sys.version.split()[0]");
    setStatus("ready", `Engine ready \u00b7 Python ${version} is running in your browser`);
    return score;
  };

  const engine = boot();
  engine.catch((err) => {
    console.error(err);
    setStatus("error", "The scoring engine could not load. Check your connection and reload the page.");
  });

  scorer.score = async (body) => {
    const score = await engine.catch(() => {
      throw new Error("The scoring engine is not available. Reload the page to try again.");
    });
    const result = JSON.parse(score(JSON.stringify(body), config.max_chars));
    if (result.error) throw new Error(result.error);
    return result;
  };

  window.speakscoreScorer = scorer;
})();

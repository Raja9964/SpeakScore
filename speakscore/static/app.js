(() => {
  const form = document.getElementById("score-form");
  const transcript = document.getElementById("transcript");
  const duration = document.getElementById("duration");
  const submit = document.getElementById("submit");
  const errorBox = document.getElementById("error");
  const wordCount = document.getElementById("word-count");
  const empty = document.getElementById("empty");
  const results = document.getElementById("results");
  const samples = JSON.parse(document.getElementById("samples-data").textContent);
  const singleColumn = window.matchMedia("(max-width: 900px)");

  // Flask scores through the API; the static demo swaps in an in-browser scorer.
  const apiScorer = {
    async score(body) {
      const response = await fetch("/api/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
      return data;
    },
  };
  const scorer = window.speakscoreScorer || apiScorer;
  let run = 0;

  const escapeHtml = (value) =>
    String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  const colorFor = (ratio) => (ratio >= 0.75 ? "var(--good)" : ratio >= 0.5 ? "var(--ok)" : "var(--bad)");

  const humanize = (key) => key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

  const formatValue = (value) => {
    if (value === null || value === undefined) return "n/a";
    if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
    return value;
  };

  const updateCount = () => {
    const words = transcript.value.match(/[A-Za-z0-9']+/g) || [];
    wordCount.textContent = `${words.length} word${words.length === 1 ? "" : "s"}`;
  };

  const showError = (message) => {
    errorBox.textContent = message;
    errorBox.hidden = !message;
  };

  const setBusy = (label) => {
    submit.disabled = Boolean(label);
    submit.textContent = label || "Score transcript";
  };

  const ring = (score, color) => {
    const r = 62;
    const circumference = 2 * Math.PI * r;
    const offset = circumference * (1 - score / 100);
    return `
      <div class="ring">
        <svg viewBox="0 0 148 148">
          <circle class="track" cx="74" cy="74" r="${r}"></circle>
          <circle class="value" cx="74" cy="74" r="${r}" stroke="${color}"
            stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"></circle>
        </svg>
        <div class="label"><span class="number">${Math.round(score)}</span><span class="of">out of 100</span></div>
      </div>`;
  };

  const chips = (metrics) =>
    Object.entries(metrics)
      .map(([k, v]) => `<span class="chip">${escapeHtml(humanize(k))} <b>${escapeHtml(formatValue(v))}</b></span>`)
      .join("");

  const renderCheck = (check) => {
    if (check.score === null) {
      return `<div class="check"><div class="check-head"><span>${escapeHtml(check.label)}</span><span class="pts">not scored</span></div>
        <p class="unscored">${escapeHtml(check.feedback)}</p></div>`;
    }
    const ratio = check.score / check.max;
    return `
      <div class="check">
        <div class="check-head"><span>${escapeHtml(check.label)}</span><span class="pts">${check.score} / ${check.max}</span></div>
        <div class="bar small"><span style="width:${ratio * 100}%;background:${colorFor(ratio)}"></span></div>
        <p>${escapeHtml(check.feedback)}</p>
        <div class="chips">${chips(check.metrics)}</div>
      </div>`;
  };

  const renderCriterion = (c) => {
    const ratio = c.scored ? c.score / c.max : 0;
    return `
      <article class="criterion">
        <div class="criterion-head">
          <h4>${escapeHtml(c.name)}</h4>
          <span class="pts">${c.scored ? `${c.score} / ${c.max}` : "not scored"}</span>
        </div>
        <div class="bar"><span style="width:${ratio * 100}%;background:${colorFor(ratio)}"></span></div>
        ${c.checks.map(renderCheck).join("")}
      </article>`;
  };

  const render = (report) => {
    const color = colorFor(report.score / 100);
    const stats = { words: report.stats.words, sentences: report.stats.sentences };
    if (report.stats.duration_seconds) stats.duration = `${report.stats.duration_seconds}s`;
    if (report.stats.wpm) stats.pace = `${report.stats.wpm} wpm`;

    results.innerHTML = `
      <div class="summary">
        ${ring(report.score, color)}
        <div class="headline">
          <span class="grade" style="background:${color}">Grade ${escapeHtml(report.grade)}</span>
          <h2>${escapeHtml(report.label)}</h2>
          <div class="stats">${chips(stats)}</div>
        </div>
      </div>
      ${report.warnings.length ? `<div class="warnings"><ul>${report.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul></div>` : ""}
      ${report.improvements.length ? `<div class="improve"><h3>Top improvements</h3><ol>${report.improvements.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ol></div>` : ""}
      <div class="criteria"><h3>Breakdown</h3>${report.criteria.map(renderCriterion).join("")}</div>`;
    empty.hidden = true;
    results.hidden = false;
    if (singleColumn.matches) results.parentElement.scrollIntoView({ block: "start" });
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError("");
    if (!transcript.value.trim()) {
      showError("Paste a transcript first.");
      return;
    }
    const body = { transcript: transcript.value };
    if (duration.value) body.duration_seconds = Number(duration.value);

    // Only the latest request may render, so a slow earlier one can't overwrite it.
    const current = ++run;
    setBusy(scorer.status === "loading" ? "Loading\u2026" : "Scoring\u2026");
    try {
      const report = await scorer.score(body);
      if (current === run) render(report);
    } catch (err) {
      if (current === run) showError(err.message);
    } finally {
      if (current === run) setBusy("");
    }
  });

  // Samples show up as #sample=<id>, so a result can be shared or refreshed.
  const findSample = (id) => samples.find((s) => s.id === id);
  const linkedSample = () => findSample(new URLSearchParams(location.hash.slice(1)).get("sample"));
  const forgetSample = () => {
    if (location.hash.startsWith("#sample=")) history.replaceState(null, "", location.pathname + location.search);
  };

  const loadSample = (sample) => {
    transcript.value = sample.transcript;
    duration.value = sample.duration_seconds ?? "";
    updateCount();
    form.requestSubmit();
  };

  document.getElementById("clear").addEventListener("click", () => {
    run += 1;
    setBusy("");
    transcript.value = "";
    duration.value = "";
    showError("");
    updateCount();
    forgetSample();
    results.hidden = true;
    empty.hidden = false;
  });

  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      const sample = findSample(button.dataset.sample);
      history.replaceState(null, "", `#sample=${encodeURIComponent(sample.id)}`);
      loadSample(sample);
    });
  });

  transcript.addEventListener("input", () => {
    updateCount();
    forgetSample();
  });
  duration.addEventListener("input", forgetSample);
  window.addEventListener("hashchange", () => {
    const sample = linkedSample();
    if (sample) loadSample(sample);
  });

  updateCount();
  const linked = linkedSample();
  if (linked) loadSample(linked);
})();

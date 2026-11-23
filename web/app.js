/* LIVE Experimentation Lab - single-page dashboard (vanilla JS + Chart.js). */
"use strict";

// ---------------------------------------------------------------- helpers
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1, sign = true) => (x == null || isNaN(x) ? "–" : (sign && x > 0 ? "+" : "") + (x * 100).toFixed(d) + "%");
const num = (x, d = 0) => (x == null ? "–" : Number(x).toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }));
const pfmt = (p) => (p == null ? "–" : p < 0.001 ? p.toExponential(1) : p.toFixed(3));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const alpha = (hex, a) => { const c = hex.replace("#", ""); const n = parseInt(c.length === 3 ? c.split("").map((x) => x + x).join("") : c, 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; };

const cache = {};
async function load(name) {
  if (cache[name]) return cache[name];
  let res;
  try { res = await fetch("api/" + name); if (!res.ok) throw new Error(); }
  catch { res = await fetch("data/" + name + ".json"); }
  if (!res.ok) throw new Error("Could not load " + name);
  return (cache[name] = await res.json());
}

let charts = [];
function chart(canvas, cfg) { const c = new Chart(canvas, cfg); charts.push(c); return c; }
function clearCharts() { charts.forEach((c) => c.destroy()); charts = []; }

function themeCharts() {
  Chart.defaults.color = css("--muted");
  Chart.defaults.borderColor = css("--border");
  Chart.defaults.font.family = css("--font");
  Chart.defaults.font.size = 12;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.tooltip.backgroundColor = css("--surface-3");
  Chart.defaults.plugins.tooltip.titleColor = css("--text");
  Chart.defaults.plugins.tooltip.bodyColor = css("--text");
  Chart.defaults.plugins.tooltip.borderColor = css("--border");
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.maintainAspectRatio = false;
}

// Dashed vertical marker (launch day, incident start)
Chart.register({
  id: "vline",
  afterDraw(c, _a, o) {
    if (o == null || o.x == null) return;
    const { ctx, chartArea: { top, bottom }, scales: { x } } = c;
    const px = x.getPixelForValue(o.x);
    ctx.save(); ctx.strokeStyle = o.color; ctx.lineWidth = 1.5; ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(px, top); ctx.lineTo(px, bottom); ctx.stroke();
    if (o.label) { ctx.setLineDash([]); ctx.fillStyle = o.color; ctx.font = "600 11px " + css("--font"); ctx.fillText(o.label, px + 6, top + 12); }
    ctx.restore();
  },
});
// Horizontal reference line (zero effect, true effect)
Chart.register({
  id: "hline",
  afterDraw(c, _a, o) {
    if (!o || !o.lines) return;
    const { ctx, chartArea: { left, right, top, bottom }, scales } = c;
    o.lines.forEach((l) => {
      const axis = scales[l.axis || "y"];
      const p = axis.getPixelForValue(l.value);
      ctx.save(); ctx.strokeStyle = l.color; ctx.lineWidth = l.width || 1; ctx.setLineDash(l.dash || []);
      ctx.beginPath();
      if ((l.axis || "y") === "y") { ctx.moveTo(left, p); ctx.lineTo(right, p); } else { ctx.moveTo(p, top); ctx.lineTo(p, bottom); }
      ctx.stroke();
      if (l.label) { ctx.fillStyle = l.color; ctx.font = "600 11px " + css("--font");
        if ((l.axis || "y") === "y") ctx.fillText(l.label, right - ctx.measureText(l.label).width - 4, p - 6); else ctx.fillText(l.label, p + 6, top + 12); }
      ctx.restore();
    });
  },
});

const TONE = { Ship: "good", "Don't ship": "bad", "No clear effect": "neutral", "Invalid - rerun": "invalid" };
const effectTone = (m) => (!m.significant ? "neutral" : m.rel_lift * m.direction > 0 ? "good" : "bad");
const toneColor = (t) => ({ good: css("--good"), bad: css("--bad"), neutral: css("--neutral"), invalid: css("--warn") }[t]);
const decisionBadge = (d) => `<span class="badge ${d.tone}">${esc(d.decision)}</span>`;

function forest(m, scale, showTruth) {
  const pos = (v) => `${50 + (Math.max(-scale, Math.min(scale, v)) / scale) * 50}%`;
  const t = effectTone(m);
  const left = 50 + (Math.max(-scale, m.ci_low) / scale) * 50, right = 50 + (Math.min(scale, m.ci_high) / scale) * 50;
  const truth = showTruth && m.true_lift != null ? `<div class="truth" style="left:${pos(m.true_lift)}" title="True effect ${pct(m.true_lift)}"></div>` : "";
  return `<div class="forest" title="${pct(m.rel_lift)} (95% CI ${pct(m.ci_low)} to ${pct(m.ci_high)})"><div class="axis"></div>
    <div class="zero" style="left:50%"></div><div class="ci ${t}" style="left:${left}%;width:${Math.max(1, right - left)}%"></div>
    <div class="est ${t}" style="left:${pos(m.rel_lift)}"></div>${truth}</div>`;
}

// ---------------------------------------------------------------- router
const routes = [
  [/^\/?$/, "overview", renderOverview],
  [/^\/exp\/(EXP-\d+)$/, "exp", renderExperiment],
  [/^\/uplift$/, "uplift", renderUplift],
  [/^\/causal$/, "causal", renderCausal],
  [/^\/monitor$/, "monitor", renderMonitor],
  [/^\/planner$/, "planner", renderPlanner],
  [/^\/copilot$/, "copilot", renderCopilot],
  [/^\/trust$/, "trust", renderTrust],
];

async function router() {
  const path = (location.hash || "#/").slice(1).split("?")[0];
  clearCharts(); themeCharts();
  const view = $("#view");
  for (const [re, name, fn] of routes) {
    const m = path.match(re);
    if (m) {
      document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active",
        a.dataset.route === name && (name !== "exp" || a.getAttribute("href") === "#" + path)));
      try { await fn(view, ...m.slice(1)); } catch (e) { console.error(e); view.innerHTML = `<div class="card empty">Could not load this page: ${esc(e.message)}<br>Run <span class="mono">python -m lab.pipeline</span> first.</div>`; }
      window.scrollTo(0, 0);
      return;
    }
  }
  location.hash = "#/";
}

function setCrumbs(...parts) { $("#crumbs").innerHTML = parts.map((p, i) => (i === parts.length - 1 ? `<b>${esc(p)}</b>` : esc(p))).join(" / "); }

// ---------------------------------------------------------------- overview
async function renderOverview(view) {
  setCrumbs("Lab", "Portfolio");
  const [exps, mon, up, val, ev, causal] = await Promise.all([load("experiments"), load("monitoring"), load("uplift"), load("validation"), load("copilot_eval"), load("causal")]);
  const counts = {};
  exps.forEach((e) => (counts[e.decision.decision] = (counts[e.decision.decision] || 0) + 1));
  const vr = exps.map((e) => e.metrics.find((m) => m.variance_reduction)?.variance_reduction).filter(Boolean);
  const avgVr = vr.reduce((a, b) => a + b, 0) / vr.length;
  const users = exps.reduce((a, e) => a + e.n_users, 0);
  const rc = mon.root_cause;
  const did = causal.did.estimate;

  view.innerHTML = `
  <div class="page-head"><div><h1>Experiment portfolio</h1>
    <p class="lead">Five LIVE-streaming experiments analysed end to end with CUPED, guardrails and sample-ratio checks, plus causal studies, uplift models and an AI copilot. The data is simulated with known true effects, so every number can be checked.</p></div>
    <a class="btn primary" href="#/copilot">Ask the copilot</a></div>
  ${mon.first_alert_date ? `<div class="alert"><span class="pulse"></span><div><b>Live alert:</b> ${esc(mon.metric)} is down ${pct(Math.abs(mon.week_over_week.change_pct), 1, false)} week over week.
    Root cause found automatically: <b>${esc(rc.country_name)} · ${esc(rc.segment.split(" / ")[1].replace("_", " "))}</b> ${rc.share_of_change >= 0.95 ? "accounts for the whole drop" : "explains " + pct(rc.share_of_change, 0, false) + " of the drop"}.</div>
    <a class="btn" style="white-space:nowrap" href="#/monitor">Investigate →</a></div>` : ""}
  <div class="grid g-4 section">
    <div class="card kpi"><div class="label">Experiments analysed</div><div class="value">${exps.length}</div>
      <div class="foot">${Object.entries(counts).map(([k, v]) => `${v} ${k.toLowerCase()}`).join(" · ")}</div></div>
    <div class="card kpi"><div class="label">Users in experiments</div><div class="value">${num(users)}</div><div class="foot">14-day tests, randomised per user</div></div>
    <div class="card kpi"><div class="label">Variance removed by CUPED</div><div class="value">${pct(avgVr, 0, false)}</div><div class="foot">≈ ${(1 / (1 - avgVr)).toFixed(1)}× more traffic for free</div></div>
    <div class="card kpi"><div class="label">Copilot answer accuracy</div><div class="value">${pct(ev.answer_key_fact_rate, 0, false)}</div><div class="foot">${ev.n_questions} test questions · retrieval hit@3 ${pct(ev.retrieval.hybrid["hit@3"], 0, false)}</div></div>
  </div>
  <div class="section"><div class="section-title"><h2>A/B tests</h2><span>Click a test for the full readout</span></div>
    <div class="grid g-3" id="exp-grid"></div></div>
  <div class="section"><div class="section-title"><h2>Beyond A/B tests</h2><span>When you can't randomise, or need to know who benefits</span></div>
    <div class="grid g-3">
      <a class="card exp-card" href="#/uplift"><div class="top"><div><div class="meta">Machine learning</div><div class="name">Who benefits from low-latency mode?</div></div><span class="badge accent">${up.best_model.replace("_", "-")}</span></div>
        <div class="metric-row"><span class="muted">True gain captured when treating only ${pct(up.targeting.share_targeted, 0, false)} of users</span><span class="big pos">${pct(up.targeting.share_of_total_gain_captured, 0, false)}</span></div>
        <div class="story">LightGBM meta-learners rank users by predicted lift and recover the low-end Android segment.</div></a>
      <a class="card exp-card" href="#/causal"><div class="top"><div><div class="meta">Difference-in-differences</div><div class="name">Gifting v3 rollout (BR, MX)</div></div><span class="badge accent">Causal</span></div>
        <div class="metric-row"><span class="muted">Naive ${pct(causal.did.naive_before_after_pct / 100)} → DiD</span><span class="big pos">${pct(did.effect_pct / 100)}</span></div>
        <div class="story">True effect ${pct(causal.did.truth_pct / 100)}. The naive before/after doubles it by mixing in the platform trend.</div></a>
      <a class="card exp-card" href="#/trust"><div class="top"><div><div class="meta">Validation</div><div class="name">Can we trust the statistics?</div></div><span class="badge good">Checked</span></div>
        <div class="metric-row"><span class="muted">False positives with daily peeking<br>(${pct(val.aa_peeking.fixed_horizon_false_positive_rate, 1, false)} with one planned look)</span><span class="big neg">${pct(val.aa_peeking.daily_peeking_false_positive_rate, 1, false)}</span></div>
        <div class="story">1,000 simulated A/A tests show why the lab never stops a test early.</div></a>
    </div></div>`;

  const grid = $("#exp-grid");
  exps.forEach((e) => {
    const p = e.metrics.find((m) => m.role === "primary");
    const scale = Math.max(0.08, Math.abs(p.ci_low), Math.abs(p.ci_high)) * 1.15;
    grid.insertAdjacentHTML("beforeend", `
      <a class="card exp-card" href="#/exp/${e.id}">
        <div class="top"><div><div class="meta"><span class="pill">${e.id}</span> · ${esc(e.owner_team)}</div><div class="name" style="margin-top:6px">${esc(e.name)}</div></div>${decisionBadge(e.decision)}</div>
        <div class="metric-row"><span class="muted">${esc(p.label)}</span><span class="big ${effectTone(p) === "good" ? "pos" : effectTone(p) === "bad" ? "neg" : ""}">${pct(p.rel_lift)}</span></div>
        ${forest(p, scale, false)}
        <div class="story">${esc(e.story)}</div>
      </a>`);
  });
  grid.insertAdjacentHTML("beforeend", `<a class="card exp-card" href="#/planner" style="border-style:dashed;justify-content:center;align-items:center;text-align:center;min-height:200px">
    <div style="font-size:28px;color:var(--accent-2)">＋</div><div class="name">Plan the next test</div>
    <div class="meta">Sample size and duration, with or without CUPED</div></a>`);
}

// ---------------------------------------------------------------- experiment
let showTruth = false;
async function renderExperiment(view, id) {
  const e = (await load("experiments")).find((x) => x.id === id);
  if (!e) throw new Error("Unknown experiment " + id);
  setCrumbs("Lab", "Experiments", e.name);
  const p = e.metrics.find((m) => m.role === "primary");
  const cupedM = e.metrics.find((m) => m.variance_reduction);
  const scale = Math.max(...e.metrics.map((m) => Math.max(Math.abs(m.ci_low), Math.abs(m.ci_high)))) * 1.1;
  const srm = e.srm;

  view.innerHTML = `
  <div class="page-head"><div><div class="muted" style="margin-bottom:6px"><span class="pill">${e.id}</span> · ${esc(e.owner_team)} · ${num(e.n_users)} users · ${e.days} days</div>
    <h1>${esc(e.name)}</h1><p class="lead">${esc(e.hypothesis)}</p></div>
    <div style="display:flex;gap:12px;align-items:center">
      <label class="toggle" title="Overlay the true effect known from the simulation"><input type="checkbox" id="truth-tg" ${showTruth ? "checked" : ""}><span class="sw"></span>Show simulation truth</label>
      <button class="btn" id="ask-exp">Ask copilot</button></div></div>
  <div class="decision ${e.decision.tone}"><div><h3>Recommendation</h3><div class="verdict">${esc(e.decision.decision)}</div></div>
    <ul>${e.decision.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></div>
  <div class="grid g-3 section">
    <div class="card"><div class="check"><div class="mark ${srm.passed ? "ok" : "fail"}">${srm.passed ? "✓" : "!"}</div><div>
      <h2>Sample ratio check</h2><div class="card-sub">Treatment share <b>${pct(srm.treatment_share, 2, false)}</b> vs 50% planned · χ² p = ${pfmt(srm.p_value)}</div>
      <div class="foot-note">${srm.passed ? "Assignment is healthy." : "Mismatch: users were lost unevenly, so every metric may be biased. Fix and rerun."}</div></div></div></div>
    <div class="card"><div class="check"><div class="mark ok">σ</div><div><h2>CUPED variance reduction</h2>
      ${cupedM ? `<div class="card-sub">Pre-period watch time removes <b>${pct(cupedM.variance_reduction, 0, false)}</b> of the variance.</div>
      <div class="foot-note">Raw CI ${pct(e.primary_raw.ci_low)} to ${pct(e.primary_raw.ci_high)} → CUPED ${pct(cupedM.ci_low)} to ${pct(cupedM.ci_high)}</div>` : `<div class="card-sub">Not applied to the primary metric.</div>`}</div></div></div>
    <div class="card"><div class="check"><div class="mark ${e.peeking.first_day_p_below_05 && e.decision.tone === "neutral" ? "fail" : "ok"}">⏱</div><div><h2>Peeking check</h2>
      <div class="card-sub">${e.peeking.first_day_p_below_05 ? `p first dipped below 0.05 on day <b>${e.peeking.first_day_p_below_05}</b>` : "p never dipped below 0.05 during the test"}; final p = ${pfmt(e.peeking.final_p)}.</div>
      <div class="foot-note">The decision uses the planned 14-day horizon only.</div></div></div></div>
  </div>
  <div class="card section"><div class="card-head"><div><h2>Scorecard</h2><div class="card-sub">Relative lift vs control with 95% confidence intervals; p-values adjusted with Benjamini-Hochberg</div></div>
    <div class="legend"><span><i style="background:var(--good)"></i>Better</span><span><i style="background:var(--bad)"></i>Worse</span><span><i style="background:var(--neutral)"></i>Not significant</span>${showTruth ? '<span><i style="background:var(--warn)"></i>True effect</span>' : ""}</div></div>
    <div style="overflow-x:auto"><table class="table"><thead><tr><th>Metric</th><th class="num">Control</th><th class="num">Treatment</th><th class="num">Lift</th><th class="num">95% CI</th><th style="width:30%">Effect</th><th class="num">Adj. p</th></tr></thead>
    <tbody>${e.metrics.map((m) => `<tr><td><div style="font-weight:600">${esc(m.label)} ${m.breached ? '<span class="badge bad" style="margin-left:6px">Breached</span>' : ""}</div><div class="role">${m.role}${m.method !== "welch" ? " · " + m.method : ""}</div></td>
      <td class="num">${num(m.control_mean * (m.unit === "%" ? 100 : 1), 2)}${m.unit === "%" ? "%" : ""}</td><td class="num">${num(m.treatment_mean * (m.unit === "%" ? 100 : 1), 2)}${m.unit === "%" ? "%" : ""}</td>
      <td class="num ${effectTone(m) === "good" ? "pos" : effectTone(m) === "bad" ? "neg" : ""}" style="font-weight:700">${pct(m.rel_lift)}</td>
      <td class="num muted">${pct(m.ci_low)} … ${pct(m.ci_high)}</td><td>${forest(m, scale, showTruth)}</td><td class="num mono">${pfmt(m.p_adjusted)}</td></tr>`).join("")}</tbody></table></div>
    ${showTruth ? `<div class="foot-note">Simulation truth: ${e.metrics.filter((m) => m.truth_in_ci).length} of ${e.metrics.length} true effects fall inside the 95% CI${e.srm.passed ? "" : " — misses here come from the sample ratio mismatch bias"}.</div>` : ""}
  </div>
  <div class="grid g-21 section">
    <div class="card"><div class="card-head"><div><h2>Effect as data accumulated</h2><div class="card-sub">${esc(p.label)} · cumulative unadjusted lift with 95% CI by day</div></div></div><div class="chart-box"><canvas id="cum"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Segments</h2><div class="card-sub">Primary metric lift by segment</div></div>
      <select id="seg-dim" style="width:auto"><option value="device">Device</option><option value="country">Country</option><option value="is_new">New user</option></select></div>
      <div class="chart-box"><canvas id="seg"></canvas></div><div class="foot-note">Segment results are adjusted for multiple testing; treat them as hypotheses unless planned.</div></div>
  </div>`;

  $("#truth-tg").onchange = (ev) => { showTruth = ev.target.checked; router(); };
  $("#ask-exp").onclick = () => goAsk(`Should we ship ${e.name}?`.replace("Should we ship", e.decision.tone === "invalid" ? "Can we trust" : "Should we ship"));

  const c = e.cumulative;
  chart($("#cum"), {
    type: "line",
    data: { labels: c.map((d) => "Day " + d.day), datasets: [
      { label: "CI low", data: c.map((d) => d.ci_low * 100), borderWidth: 0, pointRadius: 0, fill: false },
      { label: "95% CI", data: c.map((d) => d.ci_high * 100), borderWidth: 0, pointRadius: 0, backgroundColor: alpha(css("--accent"), 0.18), fill: "-1" },
      { label: "Lift", data: c.map((d) => d.rel_lift * 100), borderColor: css("--accent-2"), borderWidth: 2.5, pointRadius: 3, pointBackgroundColor: css("--accent-2"), tension: 0.25 },
    ] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: (t) => `${t.dataset.label}: ${t.parsed.y.toFixed(2)}%` } },
      hline: { lines: [{ value: 0, color: css("--faint"), dash: [4, 4] }, ...(showTruth && p.true_lift != null ? [{ value: p.true_lift * 100, color: css("--warn"), dash: [6, 4], width: 1.5, label: "true effect" }] : [])] } },
      scales: { y: { ticks: { callback: (v) => v + "%" }, grid: { color: alpha(css("--border"), 0.6) } }, x: { grid: { display: false } } } },
  });

  const drawSeg = () => {
    const dim = $("#seg-dim").value;
    const rows = e.segments.filter((s) => s.dimension === dim).sort((a, b) => b.rel_lift - a.rel_lift);
    const ex = charts.find((ch) => ch.canvas.id === "seg"); if (ex) { ex.destroy(); charts = charts.filter((x) => x !== ex); }
    chart($("#seg"), {
      type: "bar",
      data: { labels: rows.map((r) => (dim === "is_new" ? (r.segment === "True" ? "New users" : "Returning") : r.segment.replace("_", " "))),
        datasets: [{ label: "CI", data: rows.map((r) => [r.ci_low * 100, r.ci_high * 100]), backgroundColor: rows.map((r) => alpha(r.p_adjusted < 0.05 ? (r.rel_lift > 0 ? css("--good") : css("--bad")) : css("--neutral"), 0.35)), borderRadius: 4, barPercentage: 0.55, grouped: false },
          { type: "scatter", label: "Lift", data: rows.map((r, i) => ({ x: r.rel_lift * 100, y: i })), pointRadius: 5, pointBackgroundColor: css("--text"), yAxisID: "y2" }] },
      options: { indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (t) => (t.dataset.type === "scatter" ? `Lift ${t.parsed.x.toFixed(2)}%` : `95% CI ${t.raw[0].toFixed(1)}% to ${t.raw[1].toFixed(1)}%`) } },
        hline: { lines: [{ axis: "x", value: 0, color: css("--faint"), dash: [4, 4] }] } },
        scales: { x: { ticks: { callback: (v) => v + "%" }, grid: { color: alpha(css("--border"), 0.6) } }, y: { grid: { display: false } },
          y2: { display: false, min: -0.5, max: rows.length - 0.5, reverse: true, type: "linear" } } },
    });
  };
  $("#seg-dim").onchange = drawSeg;
  drawSeg();
}

// ---------------------------------------------------------------- uplift
async function renderUplift(view) {
  setCrumbs("Lab", "Advanced methods", "Uplift modelling");
  const u = await load("uplift");
  const best = u.models[u.best_model];
  const lift = best.auuc / u.auuc_random - 1;
  view.innerHTML = `
  <div class="page-head"><div><h1>Who benefits from low-latency mode?</h1>
    <p class="lead">Average lift hides who actually gains. T-learner and X-learner meta-models on LightGBM estimate each user's treatment effect from EXP-105, trained on half the users and scored on the other half against the true effects known from the simulation.</p></div>
    <a class="btn" href="#/exp/EXP-105">Open EXP-105 →</a></div>
  <div class="grid g-4">
    <div class="card kpi"><div class="label">Best model</div><div class="value" style="font-size:24px">${u.best_model === "x_learner" ? "X-learner" : "T-learner"}</div><div class="foot">LightGBM base learners · ${num(u.n_test)} test users</div></div>
    <div class="card kpi"><div class="label">Qini area vs random targeting</div><div class="value pos">${pct(lift, 0)}</div><div class="foot">Oracle (perfect knowledge): ${pct(u.auuc_oracle / u.auuc_random - 1, 0)}</div></div>
    <div class="card kpi"><div class="label">Targeting policy</div><div class="value">${pct(u.targeting.share_targeted, 0, false)}</div><div class="foot">of users treated · captures ${pct(u.targeting.share_of_total_gain_captured, 0, false)} of the true gain</div></div>
    <div class="card kpi"><div class="label">Correlation with true effect</div><div class="value">${best.corr_with_truth.toFixed(2)}</div><div class="foot">user level; segment ranking is far more reliable</div></div>
  </div>
  <div class="grid g-2 section">
    <div class="card"><div class="card-head"><div><h2>Qini curve</h2><div class="card-sub">Extra watch minutes gained when treating users in order of predicted uplift</div></div></div><div class="chart-box"><canvas id="qini"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Lift by predicted decile</h2><div class="card-sub">Decile 1 = users the model expects to gain most</div></div></div><div class="chart-box"><canvas id="dec"></canvas></div></div>
  </div>
  <div class="card section"><div class="card-head"><div><h2>Top segments by predicted uplift</h2><div class="card-sub">Country × device, test half · true effect shown for checking</div></div></div>
    <table class="table"><thead><tr><th>Segment</th><th class="num">Users</th><th class="num">Predicted lift</th><th style="width:35%"></th><th class="num">True lift</th></tr></thead><tbody>
    ${u.top_segments.map((s) => `<tr><td><b>${esc(s.country)}</b> · ${esc(s.device.replace("_", " "))}</td><td class="num">${num(s.n)}</td><td class="num pos" style="font-weight:700">${pct(s.pred)}</td>
      <td><div class="bar-inline"><i style="width:${Math.min(100, (s.pred / u.top_segments[0].pred) * 100)}%;background:var(--accent)"></i></div></td><td class="num ${s.true > 0 ? "pos" : "muted"}">${pct(s.true)}</td></tr>`).join("")}</tbody></table>
    <div class="foot-note">The model has no idea which segment was simulated to benefit; it finds low-end Android in emerging markets from the data alone. Two non-emerging segments slip into the list, which is why the lab recommends a follow-up targeted test before rollout.</div></div>`;

  const q = u.qini;
  chart($("#qini"), {
    type: "line",
    data: { labels: q.model.map((p) => Math.round(p.share_targeted * 100) + "%"), datasets: [
      { label: "Oracle", data: q.oracle.map((p) => p.incremental), borderColor: css("--warn"), borderDash: [6, 4], pointRadius: 0, borderWidth: 2 },
      { label: u.best_model === "x_learner" ? "X-learner" : "T-learner", data: q.model.map((p) => p.incremental), borderColor: css("--accent-2"), backgroundColor: alpha(css("--accent"), 0.15), fill: "+1", pointRadius: 0, borderWidth: 2.5, tension: 0.2 },
      { label: "Random", data: q.random.map((p) => p.incremental), borderColor: css("--neutral"), pointRadius: 0, borderWidth: 1.5 },
    ] },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { ticks: { callback: (v) => (v / 1000).toFixed(0) + "k" }, title: { display: true, text: "incremental minutes" } }, x: { title: { display: true, text: "share of users targeted" }, grid: { display: false } } } },
  });
  chart($("#dec"), {
    type: "bar",
    data: { labels: u.deciles.map((d) => "D" + d.decile), datasets: [
      { label: "Observed lift", data: u.deciles.map((d) => d.observed * 100), backgroundColor: alpha(css("--accent"), 0.75), borderRadius: 4 },
      { label: "True lift", data: u.deciles.map((d) => d.true * 100), backgroundColor: alpha(css("--warn"), 0.7), borderRadius: 4 },
    ] },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { ticks: { callback: (v) => v + "%" } }, x: { grid: { display: false } } } },
  });
}

// ---------------------------------------------------------------- causal
async function renderCausal(view) {
  setCrumbs("Lab", "Advanced methods", "Causal inference");
  const c = await load("causal");
  const d = c.did, ps = c.propensity;
  const aipw = ps.estimates.find((x) => x.key === "aipw"), naive = ps.estimates.find((x) => x.key === "naive");
  view.innerHTML = `
  <div class="page-head"><div><h1>Causal inference without an A/B test</h1>
    <p class="lead">Some launches can't be randomised. The lab estimates their effects with difference-in-differences (a market rollout) and propensity-score methods (an opt-in programme), and checks both against the true effects.</p></div></div>
  <div class="section-title"><h2>1 · Gifting v3 rollout in ${d.treated_countries.join(" & ")}</h2><span>Difference-in-differences with country and day fixed effects, clustered by country</span></div>
  <div class="grid g-3">
    <div class="card kpi"><div class="label">Naive before / after</div><div class="value neg">${pct(d.naive_before_after_pct / 100)}</div><div class="foot">Mixes the launch with the platform-wide trend</div></div>
    <div class="card kpi"><div class="label">Difference-in-differences</div><div class="value pos">${pct(d.estimate.effect_pct / 100)}</div><div class="foot">95% CI ${pct(d.estimate.ci_low_pct / 100)} to ${pct(d.estimate.ci_high_pct / 100)}</div></div>
    <div class="card kpi"><div class="label">True effect (simulation)</div><div class="value" style="color:var(--warn)">${pct(d.truth_pct / 100)}</div><div class="foot">${d.truth_in_ci ? "Inside the DiD confidence interval ✓" : "Outside the CI"}</div></div>
  </div>
  <div class="grid g-21 section" style="margin-top:16px">
    <div class="card"><div class="card-head"><div><h2>Gift revenue per DAU</h2><div class="card-sub">Average of launch countries vs other countries, coins per day</div></div></div><div class="chart-box"><canvas id="did"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Event study</h2><div class="card-sub">Effect by week relative to launch; flat pre-launch weeks support parallel trends</div></div></div><div class="chart-box"><canvas id="event"></canvas></div></div>
  </div>
  <div class="section-title section"><h2>2 · Does Creator Academy make creators stream more?</h2><span>${num(ps.n_creators)} creators, ${pct(ps.share_joined, 0, false)} opted in</span></div>
  <div class="grid g-21">
    <div class="card"><div class="card-head"><div><h2>Estimated effect on weekly streaming hours</h2><div class="card-sub">Bootstrap 95% CIs (200 resamples); dashed line = true effect ${ps.truth_hours} h</div></div></div><div class="chart-box short"><canvas id="ps"></canvas></div>
      <div class="foot-note">Joiners already streamed more before the programme, so the naive gap (${naive.estimate.toFixed(2)} h) is mostly selection. Doubly robust estimation gives ${aipw.estimate.toFixed(2)} h (CI ${aipw.ci_low.toFixed(2)}–${aipw.ci_high.toFixed(2)}).</div></div>
    <div class="card"><div class="card-head"><div><h2>Covariate balance</h2><div class="card-sub">Standardised mean difference; |SMD| &lt; 0.1 is balanced</div></div></div>
      <table class="table"><thead><tr><th>Covariate</th><th class="num">Before</th><th class="num">After IPW</th></tr></thead><tbody>
      ${ps.balance.map((b) => `<tr><td>${esc(b.covariate.replace(/_/g, " "))}</td><td class="num neg">${b.smd_before.toFixed(2)}</td><td class="num pos">${b.smd_after.toFixed(3)}</td></tr>`).join("")}</tbody></table>
      <div style="margin-top:14px" class="chart-box short"><canvas id="overlap"></canvas></div></div>
  </div>`;

  const days = d.daily.map((r) => r.day);
  const preT = d.daily.filter((r) => r.day < d.launch_day).reduce((a, r) => a + r.treated, 0) / d.launch_day;
  const preC = d.daily.filter((r) => r.day < d.launch_day).reduce((a, r) => a + r.control, 0) / d.launch_day;
  chart($("#did"), {
    type: "line",
    data: { labels: days.map((x) => "D" + x), datasets: [
      { label: "Launch countries (indexed)", data: d.daily.map((r) => (r.treated / preT) * 100), borderColor: css("--accent-2"), pointRadius: 0, borderWidth: 2.2, tension: 0.3 },
      { label: "Other countries (indexed)", data: d.daily.map((r) => (r.control / preC) * 100), borderColor: css("--neutral"), pointRadius: 0, borderWidth: 2, tension: 0.3 },
    ] },
    options: { plugins: { legend: { position: "bottom" }, vline: { x: d.launch_day, color: css("--warn"), label: "launch" } },
      scales: { y: { title: { display: true, text: "index (pre-launch = 100)" } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } } } },
  });
  chart($("#event"), {
    type: "bar",
    data: { labels: d.event_study.map((r) => (r.week < 0 ? "W" + r.week : "W+" + r.week)), datasets: [
      { label: "95% CI", data: d.event_study.map((r) => [r.ci_low_pct, r.ci_high_pct]), backgroundColor: d.event_study.map((r) => alpha(r.week >= 0 ? css("--accent") : css("--neutral"), 0.45)), borderRadius: 4, barPercentage: 0.5 },
      { type: "line", label: "Estimate", data: d.event_study.map((r) => r.effect_pct), borderColor: css("--text"), pointBackgroundColor: css("--text"), showLine: false, pointRadius: 4 },
    ] },
    options: { plugins: { legend: { display: false }, hline: { lines: [{ value: 0, color: css("--faint"), dash: [4, 4] }, { value: d.truth_pct, color: css("--warn"), dash: [6, 4], label: "true 7%" }] } },
      scales: { y: { ticks: { callback: (v) => v + "%" } }, x: { grid: { display: false } } } },
  });
  const est = ps.estimates;
  chart($("#ps"), {
    type: "bar",
    data: { labels: est.map((x) => x.method), datasets: [
      { label: "95% CI", data: est.map((x) => [x.ci_low, x.ci_high]), backgroundColor: est.map((x) => alpha(x.key === "naive" ? css("--bad") : x.truth_in_ci ? css("--good") : css("--warn"), 0.5)), borderRadius: 4, barPercentage: 0.55, grouped: false },
      { type: "scatter", label: "Estimate", data: est.map((x, i) => ({ x: x.estimate, y: i })), pointRadius: 5, pointBackgroundColor: css("--text"), yAxisID: "y2" },
    ] },
    options: { indexAxis: "y", plugins: { legend: { display: false }, hline: { lines: [{ axis: "x", value: ps.truth_hours, color: css("--warn"), dash: [6, 4], width: 1.5 }] } },
      scales: { x: { min: 0, title: { display: true, text: "extra hours per week" } }, y: { grid: { display: false } }, y2: { display: false, type: "linear", min: -0.5, max: est.length - 0.5, reverse: true } } },
  });
  const o = ps.overlap;
  chart($("#overlap"), {
    type: "bar",
    data: { labels: o.bins.slice(0, -1).map((b) => b.toFixed(2)), datasets: [
      { label: "Joined", data: o.joined, backgroundColor: alpha(css("--accent"), 0.75) },
      { label: "Did not join", data: o.not_joined, backgroundColor: alpha(css("--neutral"), 0.55) },
    ] },
    options: { plugins: { legend: { position: "bottom" }, title: { display: true, text: "Propensity score overlap", color: css("--muted"), font: { weight: 500 } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6 } }, y: { display: false } } },
  });
}

// ---------------------------------------------------------------- monitor
async function renderMonitor(view) {
  setCrumbs("Lab", "Monitor & root cause");
  const m = await load("monitoring");
  const rc = m.root_cause, wow = m.week_over_week;
  const combo = m.decomposition.country_x_device.rows.slice(0, 10);
  view.innerHTML = `
  <div class="page-head"><div><h1>Metric monitoring &amp; root cause</h1>
    <p class="lead">${esc(m.metric)} is checked daily against a same-weekday baseline. When it breaks, the change is decomposed across countries and devices into rate and mix effects to find where it came from.</p></div>
    <button class="btn primary" id="ask-inc">Ask copilot for the incident summary</button></div>
  <div class="grid g-4">
    <div class="card kpi"><div class="label">Week over week</div><div class="value neg">${pct(wow.change_pct)}</div><div class="foot">${wow.previous.toFixed(1)} → ${wow.current.toFixed(1)} min per DAU</div></div>
    <div class="card kpi"><div class="label">First alert</div><div class="value" style="font-size:24px">${esc(m.first_alert_date)}</div><div class="foot">Incident started ${esc(m.incident_start_truth)} · detected same day</div></div>
    <div class="card kpi"><div class="label">Root cause</div><div class="value" style="font-size:24px">${esc(rc.country_name)}</div><div class="foot">${esc(rc.segment.split(" / ")[1].replace("_", " "))} · segment ${pct(rc.segment_change_pct, 0)}</div></div>
    <div class="card kpi"><div class="label">Share of drop explained</div><div class="value">${pct(rc.share_of_change, 0, false)}</div><div class="foot">other segments slightly offset it</div></div>
  </div>
  <div class="card section"><div class="card-head"><div><h2>${esc(m.metric)}</h2><div class="card-sub">Daily value, same-weekday baseline (median of previous 4 weeks) and alerts (robust z &gt; 4)</div></div>
    <div class="legend"><span><i style="background:var(--accent-2)"></i>Actual</span><span><i style="background:var(--neutral)"></i>Baseline</span><span><i style="background:var(--bad)"></i>Alert</span></div></div>
    <div class="chart-box tall"><canvas id="series"></canvas></div></div>
  <div class="grid g-21 section">
    <div class="card"><div class="card-head"><div><h2>Contribution to the change</h2><div class="card-sub">Country × device, last 7 days vs previous 7 · rate effect + mix effect (min per DAU)</div></div></div><div class="chart-box tall"><canvas id="contrib"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Where is it concentrated?</h2><div class="card-sub">Share of the change explained by the top segment of each dimension</div></div></div>
      <div class="stat-list">${["country", "device", "country_x_device"].map((k) => { const dd = m.decomposition[k]; return `<div><div class="stat-row"><span class="k">${k.replace(/_x_/, " × ")}</span><span class="v">${esc(dd.rows[0].segment)} · ${pct(dd.top_share, 0, false)}</span></div>
        <div class="bar-inline"><i style="width:${Math.min(100, dd.top_share * 100)}%;background:var(--bad)"></i></div></div>`; }).join("")}</div>
      <div style="margin-top:18px" class="chart-box short"><canvas id="segseries"></canvas></div></div>
  </div>`;

  $("#ask-inc").onclick = () => goAsk("What caused the drop in watch time last week?");
  const s = m.series;
  const alertIdx = s.findIndex((r) => r.anomaly);
  chart($("#series"), {
    type: "line",
    data: { labels: s.map((r) => r.date.slice(5)), datasets: [
      { label: "Baseline", data: s.map((r) => r.baseline), borderColor: css("--neutral"), borderDash: [5, 4], pointRadius: 0, borderWidth: 1.5 },
      { label: "Actual", data: s.map((r) => r.value), borderColor: css("--accent-2"), backgroundColor: alpha(css("--accent"), 0.08), fill: true, borderWidth: 2.2, tension: 0.25,
        pointRadius: s.map((r) => (r.anomaly ? 5 : 0)), pointBackgroundColor: s.map((r) => (r.anomaly ? css("--bad") : css("--accent-2"))) },
    ] },
    options: { plugins: { legend: { display: false }, vline: alertIdx >= 0 ? { x: alertIdx, color: css("--bad"), label: "first alert" } : {} },
      scales: { y: { title: { display: true, text: "minutes per DAU" } }, x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } } } },
  });
  chart($("#contrib"), {
    type: "bar",
    data: { labels: combo.map((r) => r.segment.replace("_", " ")), datasets: [
      { label: "Rate effect", data: combo.map((r) => r.rate_effect), backgroundColor: alpha(css("--bad"), 0.8), borderRadius: 3 },
      { label: "Mix effect", data: combo.map((r) => r.mix_effect), backgroundColor: alpha(css("--warn"), 0.8), borderRadius: 3 },
    ] },
    options: { indexAxis: "y", plugins: { legend: { position: "bottom" } }, scales: { x: { stacked: true, title: { display: true, text: "change in minutes per DAU" } }, y: { stacked: true, grid: { display: false } } } },
  });
  const ss = m.segment_series;
  chart($("#segseries"), {
    type: "line",
    data: { labels: ss.map((r) => r.date.slice(5)), datasets: [{ label: "ID · android low", data: ss.map((r) => r.value), borderColor: css("--bad"), pointRadius: 0, borderWidth: 2, tension: 0.25 }] },
    options: { plugins: { legend: { display: false }, title: { display: true, text: "Indonesia · low-end Android, min per DAU", color: css("--muted"), font: { weight: 500 } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6 } } } },
  });
}

// ---------------------------------------------------------------- planner
function normInv(p) { // Acklam's approximation of the inverse normal CDF
  const a = [-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924];
  const b = [-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857];
  const c = [-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878];
  const d = [0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742];
  const pl = 0.02425;
  let q, r;
  if (p < pl) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  if (p > 1 - pl) { q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
  q = p - 0.5; r = q * q;
  return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
}
const nPerArm = (mean, sd, mde, alphaV, power, vr) => Math.ceil((2 * (normInv(1 - alphaV / 2) + normInv(power)) ** 2 * sd * sd * (1 - vr)) / (mean * mde) ** 2);

async function renderPlanner(view) {
  setCrumbs("Lab", "Tools", "Test planner");
  const base = await load("baselines");
  view.innerHTML = `
  <div class="page-head"><div><h1>Test planner</h1><p class="lead">How many users and days does a test need? Baselines come from the control groups of past LIVE experiments. The formula was checked by simulation: it delivered 79.4% power when 80% was promised.</p></div></div>
  <div class="grid g-12">
    <div class="card">
      <div class="field"><label>Primary metric</label><select id="pl-metric">${Object.entries(base).map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`).join("")}</select></div>
      <div class="field"><label>Minimum detectable effect <b id="pl-mde-v"></b></label><input type="range" id="pl-mde" min="0.5" max="10" step="0.5" value="3"></div>
      <div class="grid g-2" style="gap:12px">
        <div class="field"><label>Significance (α)</label><select id="pl-alpha"><option value="0.05">5%</option><option value="0.01">1%</option><option value="0.1">10%</option></select></div>
        <div class="field"><label>Power</label><select id="pl-power"><option value="0.8">80%</option><option value="0.9">90%</option><option value="0.95">95%</option></select></div>
      </div>
      <div class="field"><label>Eligible users per day</label><input type="number" id="pl-daily" value="40000" min="100" step="1000"></div>
      <label class="toggle" id="pl-cuped-wrap"><input type="checkbox" id="pl-cuped" checked><span class="sw"></span>Use CUPED (pre-period watch time)</label>
    </div>
    <div class="card"><div class="grid g-3">
      <div class="kpi"><div class="label">Users per arm</div><div class="big-number" id="pl-n"></div></div>
      <div class="kpi"><div class="label">Total users</div><div class="big-number" id="pl-total"></div></div>
      <div class="kpi"><div class="label">Run for</div><div class="big-number" id="pl-days"></div><div class="foot" id="pl-days-foot"></div></div></div>
      <div class="section"><div class="card-sub" style="margin-bottom:8px">Users per arm needed for each minimum detectable effect</div><div class="chart-box"><canvas id="pl-chart"></canvas></div></div>
    </div>
  </div>`;
  let c = null;
  const update = () => {
    const k = $("#pl-metric").value, b = base[k];
    const mde = +$("#pl-mde").value / 100, a = +$("#pl-alpha").value, pw = +$("#pl-power").value, daily = Math.max(1, +$("#pl-daily").value || 1);
    const canCuped = b.cuped_variance_reduction != null;
    $("#pl-cuped-wrap").style.display = canCuped ? "" : "none";
    const vr = canCuped && $("#pl-cuped").checked ? b.cuped_variance_reduction : 0;
    const n = nPerArm(b.mean, b.sd, mde, a, pw, vr);
    const days = Math.ceil((2 * n) / daily);
    $("#pl-mde-v").textContent = (mde * 100).toFixed(1) + "% relative";
    $("#pl-n").textContent = num(n); $("#pl-total").textContent = num(2 * n);
    $("#pl-days").textContent = days + (days === 1 ? " day" : " days");
    $("#pl-days-foot").textContent = `Round up to ${Math.max(1, Math.ceil(days / 7))} full week(s) to cover weekday patterns`;
    const mdes = Array.from({ length: 20 }, (_, i) => (i + 1) * 0.5);
    const ds = [{ label: "Without CUPED", data: mdes.map((m) => nPerArm(b.mean, b.sd, m / 100, a, pw, 0)), borderColor: css("--neutral"), pointRadius: 0, borderWidth: 2, tension: 0.3 }];
    if (canCuped) ds.push({ label: "With CUPED", data: mdes.map((m) => nPerArm(b.mean, b.sd, m / 100, a, pw, b.cuped_variance_reduction)), borderColor: css("--accent-2"), pointRadius: 0, borderWidth: 2.5, tension: 0.3 });
    if (c) { c.destroy(); charts = charts.filter((x) => x !== c); }
    c = chart($("#pl-chart"), { type: "line", data: { labels: mdes.map((m) => m + "%"), datasets: ds },
      options: { plugins: { legend: { position: "bottom" }, vline: { x: mdes.indexOf(mde * 100), color: css("--warn"), label: "your MDE" } },
        scales: { y: { type: "logarithmic", ticks: { callback: (v) => ([1e3, 1e4, 1e5, 1e6, 1e7].includes(v) ? num(v) : "") } }, x: { grid: { display: false }, title: { display: true, text: "minimum detectable effect" } } } } });
  };
  ["#pl-metric", "#pl-mde", "#pl-alpha", "#pl-power", "#pl-daily", "#pl-cuped"].forEach((s) => ($(s).oninput = update));
  update();
}

// ---------------------------------------------------------------- copilot
const SUGGESTIONS = ["Why didn't we ship autoplay previews?", "Can we trust the beauty filter result?", "Who benefits from low-latency mode?",
  "What caused the drop in watch time last week?", "Does Creator Academy actually make creators stream more?", "How does CUPED reduce noise?"];
let chatLog = [];
let pendingQuestion = null;

function goAsk(q) { pendingQuestion = q; if (location.hash === "#/copilot") router(); else location.hash = "#/copilot"; }

function renderAnswer(r) {
  const body = esc(r.answer).replace(/\[(\d+)\]/g, (_, n) => `<span class="cite" data-n="${n}">${n}</span>`);
  const facts = r.facts && r.facts.length && !r.answer.includes(r.facts[0].slice(0, 40)) ? `<div class="facts"><b>From the results database</b><div>${r.facts.map(esc).join("<br>")}</div></div>` : "";
  const src = r.sources && r.sources.length ? `<div class="sources">${r.sources.map((s) => `<details class="source" data-n="${s.n}"><summary><span class="cite">${s.n}</span>${esc(s.title)} — ${esc(s.section)}</summary><p>${esc(s.text)}</p></details>`).join("")}</div>` : "";
  return `<div>${body}</div>${facts}${src}<div class="meta-line"><span>backend: ${esc(r.backend)}</span>${r.experiments && r.experiments.length ? `<span>linked: ${r.experiments.map(esc).join(", ")}</span>` : ""}</div>`;
}

async function renderCopilot(view) {
  setCrumbs("Lab", "Tools", "AI Copilot");
  view.innerHTML = `
  <div class="page-head"><div><h1>Experiment Copilot</h1><p class="lead">Ask about any experiment, metric or method. Answers come from retrieval over the lab's readouts and method guides (hybrid BM25 + embeddings), exact figures from the results database, and an LLM when one is configured. Every claim is cited.</p></div></div>
  <div class="card chat"><div class="chat-log" id="log"></div>
    <form class="composer" id="composer" autocomplete="off"><input id="q" placeholder="Ask a question about the experiments…"><button class="btn primary">Ask</button></form></div>`;
  const log = $("#log");
  const add = (role, html) => { log.insertAdjacentHTML("beforeend", `<div class="msg ${role}"><div class="avatar">${role === "user" ? "You" : "AI"}</div><div class="bubble">${html}</div></div>`); log.scrollTop = log.scrollHeight; return log.lastElementChild; };
  if (!chatLog.length) add("bot", `Hi! I can explain results, trade-offs and methods for the LIVE experiments. Try one of these:<div class="chips" style="margin-top:10px">${SUGGESTIONS.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}</div>`);
  chatLog.forEach((m) => add(m.role, m.html));
  log.addEventListener("click", (ev) => {
    const chip = ev.target.closest(".chip"); if (chip) { ask(chip.textContent); return; }
    const cite = ev.target.closest(".cite");
    if (cite && !cite.closest("summary")) {
      const det = cite.closest(".bubble").querySelector(`.source[data-n="${cite.dataset.n}"]`);
      if (det) { det.open = true; det.classList.add("flash"); setTimeout(() => det.classList.remove("flash"), 1200); det.scrollIntoView({ block: "nearest", behavior: "smooth" }); }
    }
  });
  async function ask(q) {
    q = q.trim(); if (!q) return;
    const uh = esc(q); add("user", uh); chatLog.push({ role: "user", html: uh });
    const pending = add("bot", `<span class="typing"><span></span><span></span><span></span></span>`);
    try {
      const res = await fetch("api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const html = renderAnswer(await res.json());
      pending.querySelector(".bubble").innerHTML = html; chatLog.push({ role: "bot", html });
    } catch (e) {
      const html = `The copilot needs the Python backend. Start it with <span class="mono">uvicorn lab.api:app</span> and reload this page.`;
      pending.querySelector(".bubble").innerHTML = html;
    }
    log.scrollTop = log.scrollHeight;
  }
  $("#composer").onsubmit = (ev) => { ev.preventDefault(); const v = $("#q").value; $("#q").value = ""; ask(v); };
  const urlQ = new URLSearchParams((location.hash.split("?")[1] || "")).get("q");
  if (!pendingQuestion && urlQ && !chatLog.length) pendingQuestion = urlQ;
  if (pendingQuestion) { const q = pendingQuestion; pendingQuestion = null; ask(q); }
}

// ---------------------------------------------------------------- trust
async function renderTrust(view) {
  setCrumbs("Lab", "Tools", "Can we trust it?");
  const [v, exps, ev] = await Promise.all([load("validation"), load("experiments"), load("copilot_eval")]);
  const a = v.aa_peeking, cov = v.coverage, pw = v.power;
  const valid = exps.filter((e) => e.srm.passed).flatMap((e) => e.metrics.filter((m) => m.true_lift != null));
  const inCi = valid.filter((m) => m.truth_in_ci).length;
  view.innerHTML = `
  <div class="page-head"><div><h1>Can we trust these numbers?</h1><p class="lead">Because the platform is simulated, the lab knows the true answer to every question. These checks show the statistics deliver what they promise, and how they fail when used wrongly.</p></div></div>
  <div class="grid g-4">
    <div class="card kpi"><div class="label">A/A false positive rate</div><div class="value pos">${pct(a.fixed_horizon_false_positive_rate, 1, false)}</div><div class="foot">target 5% · ${num(a.n_sims)} simulated A/A tests</div></div>
    <div class="card kpi"><div class="label">…with daily peeking</div><div class="value neg">${pct(a.daily_peeking_false_positive_rate, 1, false)}</div><div class="foot">stopping at the first p &lt; 0.05 over ${a.looks} looks</div></div>
    <div class="card kpi"><div class="label">95% CI coverage</div><div class="value">${pct(cov.coverage_raw, 1, false)}</div><div class="foot">CUPED ${pct(cov.coverage_cuped, 1, false)} with ${pct(1 - cov.mean_ci_width_cuped / cov.mean_ci_width_raw, 0, false)} narrower intervals</div></div>
    <div class="card kpi"><div class="label">Power delivered</div><div class="value">${pct(pw.observed_power, 1, false)}</div><div class="foot">promised ${pct(pw.target_power, 0, false)} at ${num(pw.n_per_arm)} users per arm</div></div>
  </div>
  <div class="grid g-2 section">
    <div class="card"><div class="card-head"><div><h2>False positives: one look vs daily peeking</h2><div class="card-sub">A/A tests have no real effect, so every "win" is a false positive</div></div></div><div class="chart-box short"><canvas id="fp"></canvas></div></div>
    <div class="card"><div class="card-head"><div><h2>Truth check on the real experiments</h2><div class="card-sub">${inCi} of ${valid.length} true effects fall inside the 95% CIs (tests that passed SRM)</div></div></div>
      <div class="stat-list">${exps.map((e) => { const ms = e.metrics.filter((m) => m.true_lift != null); const k = ms.filter((m) => m.truth_in_ci).length;
        return `<div class="stat-row"><span class="k"><span class="pill">${e.id}</span> ${esc(e.name)}</span><span class="v ${e.srm.passed ? "" : "warn"}">${k}/${ms.length}${e.srm.passed ? "" : " · SRM bias"}</span></div>`; }).join("")}</div></div>
  </div>
  <div class="card section"><div class="card-head"><div><h2>Copilot evaluation</h2><div class="card-sub">${ev.n_questions} hand-written questions · answer contains the key fact in ${pct(ev.answer_key_fact_rate, 0, false)} of cases (offline extractive backend) · out-of-scope questions declined ${esc(ev.out_of_scope_refusals)}</div></div></div>
    <div class="chart-box short"><canvas id="ret"></canvas></div></div>`;
  chart($("#fp"), {
    type: "bar",
    data: { labels: ["One look at day 14", "Peek every day"], datasets: [{ data: [a.fixed_horizon_false_positive_rate * 100, a.daily_peeking_false_positive_rate * 100], backgroundColor: [alpha(css("--good"), 0.75), alpha(css("--bad"), 0.75)], borderRadius: 6, barPercentage: 0.5 }] },
    options: { plugins: { legend: { display: false }, hline: { lines: [{ value: 5, color: css("--warn"), dash: [6, 4], label: "promised 5%" }] } }, scales: { y: { beginAtZero: true, ticks: { callback: (x) => x + "%" } }, x: { grid: { display: false } } } },
  });
  const r = ev.retrieval, modes = [["bm25", "BM25 keywords"], ["dense", "LSA embeddings"], ["hybrid", "Hybrid (RRF)"]];
  chart($("#ret"), {
    type: "bar",
    data: { labels: ["hit@1", "hit@3", "MRR"], datasets: modes.map(([k, l], i) => ({ label: l, data: [r[k]["hit@1"], r[k]["hit@3"], r[k].mrr].map((x) => x * 100),
      backgroundColor: alpha([css("--neutral"), css("--info"), css("--accent")][i], 0.8), borderRadius: 4 })) },
    options: { plugins: { legend: { position: "bottom" } }, scales: { y: { min: 50, max: 100, ticks: { callback: (x) => x + "%" } }, x: { grid: { display: false } } } },
  });
}

// ---------------------------------------------------------------- boot
async function boot() {
  try {
    const exps = await load("experiments");
    $("#exp-links").innerHTML = exps.map((e) => `<a href="#/exp/${e.id}" data-route="exp"><span class="dot" style="background:${toneColor(e.decision.tone)};margin:0 5px"></span>${esc(e.name)}</a>`).join("");
    const mon = await load("monitoring");
    if (mon.first_alert_date) $("#alert-count").innerHTML = `<span class="dot" style="background:var(--bad)"></span>`;
  } catch (e) { console.warn(e); }
  $("#ask-form").onsubmit = (ev) => { ev.preventDefault(); const v = $("#ask-input").value.trim(); if (v) { $("#ask-input").value = ""; goAsk(v); } };
  $("#theme-btn").onclick = () => { document.documentElement.classList.toggle("light");
    try { localStorage.setItem("lx-theme", document.documentElement.classList.contains("light") ? "light" : "dark"); } catch (e) {}
    router(); };
  window.addEventListener("hashchange", router);
  router();
}
boot();

"use strict";
const $ = id => document.getElementById(id);
const state = { overview: null, selected: null, detail: null, csrf: null, config: null, configId: null, lastFailure: null };
const number = (n, decimals = 0) => n == null || !Number.isFinite(Number(n)) ? "—" : Number(n).toLocaleString("fr-FR", { maximumFractionDigits: decimals });
const node = (tag, text, className) => { const item = document.createElement(tag); if (text != null) item.textContent = String(text); if (className) item.className = className; return item; };
const empty = element => element.replaceChildren();
function toast(message, error = false) { const item = $("notice"); item.hidden = false; item.className = error ? "error" : ""; item.textContent = message; }
async function request(url, data) {
  const options = data === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf }, body: JSON.stringify(data) };
  const response = await fetch(url, options);
  let value;
  try { value = await response.json(); } catch { throw new Error("Réponse du serveur illisible"); }
  if (!response.ok) throw new Error(value.error || `Erreur HTTP ${response.status}`);
  return value;
}
async function operation(path, payload, message) {
  try { const result = await request(`/api/actions/${path}`, payload); toast(message || "Action prise en compte"); await refresh(); return result; }
  catch (error) { toast(error.message, true); return null; }
}
function option(select, value, text) { const item = node("option", text); item.value = value; select.append(item); }
function setOptions(select, choices, placeholder) {
  const old = select.value; empty(select);
  if (placeholder) option(select, "", placeholder);
  for (const [id, label] of choices) option(select, id, label);
  if ([...select.options].some(o => o.value === old)) select.value = old;
}
function badge(phase) {
  const text = ({ running: "En cours", stopped: "Arrêté", finished_budget: "Budget atteint", diverged: "Divergence", crashed: "Erreur", aborted: "Interrompu" })[phase] || phase || "—";
  const p = node("span", text, "pill" + (["diverged", "crashed", "aborted"].includes(phase) ? " error" : phase === "running" ? "" : " idle"));
  return p;
}
function metric(label, value, foot) { const p = node("div", null, "metric"); p.append(node("span", label, "label"), node("strong", value), node("small", foot || "")); return p; }
function drawProgress(episodes) {
  const data = episodes.filter(e => typeof e.progress_max === "number");
  if (!data.length) return node("p", "Pas encore d'épisodes enregistrés.", "hint");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 400 135"); svg.setAttribute("preserveAspectRatio", "none"); svg.setAttribute("class", "chart"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Progression maximale des derniers épisodes");
  const axis = document.createElementNS(svg.namespaceURI, "line"); axis.setAttribute("x1", "0"); axis.setAttribute("x2", "400"); axis.setAttribute("y1", "128"); axis.setAttribute("y2", "128"); axis.setAttribute("class", "axis"); svg.append(axis);
  const line = document.createElementNS(svg.namespaceURI, "polyline");
  line.setAttribute("points", data.map((e, i) => `${8 + i * 384 / Math.max(data.length - 1, 1)},${125 - Math.min(1, Math.max(0, e.progress_max)) * 115}`).join(" "));
  svg.append(line); return svg;
}
function table(headers, rows) {
  const wrapper = node("div", null, "table-wrap"); const t = node("table");
  const head = node("thead"), tr = node("tr"); headers.forEach(h => tr.append(node("th", h))); head.append(tr); t.append(head);
  const body = node("tbody"); for (const values of rows) { const row = node("tr"); values.forEach(v => row.append(node("td", v))); body.append(row); } t.append(body); wrapper.append(t); return wrapper;
}
function renderDetails() {
  const d = state.detail, target = $("run-detail");
  const expanded = Boolean(target.querySelector("details[open]")); empty(target);
  if (!d) { target.textContent = "Sélectionnez un run pour voir les données."; return; }
  $("run-phase").replaceWith(Object.assign(badge(d.status.phase), { id: "run-phase" }));
  const s = d.status; const cells = node("div", null, "stats-grid");
  for (const [label, val] of [["Transitions", number(s.timesteps)], ["Budget", s.budget_transitions == null ? "∞" : number(s.budget_transitions)], ["Épisodes", number(s.episodes)], ["Arrivées", number(s.finishes)], ["Progression médiane", d.trend ? number(d.trend.slices.at(-1).progress_max_median * 100, 1) + " %" : "—"], ["Meilleur chrono", s.best_finish_ms ? number(s.best_finish_ms / 1000, 3) + " s" : "—"]]) {
    const c = node("div"); c.append(node("span", label), node("strong", val)); cells.append(c);
  }
  target.append(cells, drawProgress(d.episodes));
  target.append(node("p", `Derniers ${d.episodes.length} épisodes · progression maximale sur la référence (pas un chrono).`, "hint"));
  if (d.trend) target.append(node("p", `Tendance indicative : ${d.trend.verdict}. Ne remplace pas une évaluation figée.`, "hint"));
  if (s.stop_reason) target.append(node("p", `Raison d'arrêt : ${s.stop_reason}`, "hint"));
  if (d.incidents.length) target.append(node("p", `Dernier incident : ${d.incidents.at(-1).kind || "—"}`, "hint"));
  const full = node("details"), summary = node("summary", "Statut complet et configuration du run");
  full.open = expanded;
  const pre = node("pre", JSON.stringify({ status: d.status, config: d.config }, null, 2), "log compact");
  full.append(summary, pre); target.append(full);
  renderEvalHistory(d);
}
function renderEvalHistory(detail) {
  const target = $("eval-history");
  const expanded = new Set([...target.querySelectorAll(".history-item details[open]")].map(x => x.parentElement.querySelector("b")?.textContent));
  empty(target);
  if (!detail || !detail.evals.length) { target.textContent = "Aucune évaluation terminée pour ce run."; return; }
  for (const result of detail.evals) {
    const item = node("div", null, "history-item"); item.append(node("b", result.id));
    item.append(node("span", `${number(result.episodes)} essai(s) · ${number(result.finishes)} arrivée(s) · meilleur ${result.best_finish_ms ? number(result.best_finish_ms / 1000, 3) + " s" : "—"} · ${result.mode || "—"} ×${result.speed || "—"}`));
    const full = node("details"); full.open = expanded.has(result.id);
    full.append(node("summary", "Résumé complet"));
    const pre = node("pre", JSON.stringify(result, null, 2), "log compact");
    full.append(pre); item.append(full); target.append(item);
  }
}
async function loadRun(id) {
  if (!id) { state.selected = null; state.detail = null; renderDetails(); return; }
  try { const detail = await request(`/api/runs/${encodeURIComponent(id)}`); state.selected = id; state.detail = detail; $("run-picker").value = id; renderDetails(); }
  catch (error) { toast(error.message, true); }
}
async function loadEvalRun(id) {
  if (!id) { setOptions($("eval-checkpoint"), []); renderEvalHistory(null); return; }
  try {
    const detail = await request(`/api/runs/${encodeURIComponent(id)}`);
    setOptions($("eval-checkpoint"), [["latest", "Dernier checkpoint"], ...detail.checkpoints.map(c => [c.id, `${c.id} · ${number(c.timesteps)} transitions`])]);
    renderEvalHistory(detail);
  } catch (error) { toast(error.message, true); }
}
function renderOverview(o) {
  const active = o.runs.filter(r => r.phase === "running");
  $("controller-badge").textContent = o.controller ? `Jeu occupé · ${o.controller.command || "commande"}` : "Jeu libre";
  $("controller-badge").classList.toggle("busy", Boolean(o.controller));
  empty($("summary-cards"));
  $("summary-cards").append(metric("Runs", number(o.runs.length), "expériences enregistrées"), metric("En cours", number(active.length), "run actif"), metric("Arrivées", number(o.runs.reduce((n, r) => n + (r.finishes || 0), 0)), "épisodes d'entraînement"), metric("Configurations", number(o.templates.length), "modèles de départ"));
  const list = $("runs-table"); empty(list);
  if (!o.runs.length) list.append(node("p", "Aucun run. Préparez une configuration puis lancez un entraînement.", "hint"));
  else {
    const t = node("table"); const head = node("thead"); const h = node("tr"); ["Run", "État", "Transitions", "Épisodes", "Arrivées", "Mis à jour"].forEach(x => h.append(node("th", x))); head.append(h); t.append(head);
    const body = node("tbody"); for (const r of o.runs) {
      const row = node("tr"); if (r.id === state.selected) row.className = "selected";
      row.append(node("td", r.id, "run-name")); const status = node("td"); status.append(badge(r.phase)); row.append(status);
      row.append(node("td", `${number(r.timesteps)} / ${r.budget_transitions == null ? "∞" : number(r.budget_transitions)}`), node("td", number(r.episodes)), node("td", number(r.finishes)), node("td", r.updated || "—", "muted"));
      row.addEventListener("click", () => loadRun(r.id)); body.append(row);
    } t.append(body); list.append(t);
  }
  const pairs = o.runs.map(r => [r.id, r.id]);
  for (const select of [$("run-picker"), $("resume-run"), $("eval-run")]) setOptions(select, pairs, "Choisir un run");
  if (state.selected && o.runs.some(r => r.id === state.selected)) $("run-picker").value = state.selected;
  const configs = o.templates.map(c => [c.id, c.id]);
  for (const select of [$("train-config"), $("edit-config")]) setOptions(select, configs, "Choisir une configuration");
  renderCompareList(o.runs);
  const presence = o.tensorboard_presence;
  $("tensor-state").textContent = o.dashboard?.running ? "TensorBoard actif sur 127.0.0.1:6006 (lancé ici)" : presence === "tensorboard" ? "TensorBoard actif sur 127.0.0.1:6006 (lancé ailleurs)" : presence === "occupied" ? "Port 6006 occupé par un autre service" : o.dashboard ? `TensorBoard terminé (code ${o.dashboard.returncode})` : "TensorBoard arrêté";
  $("tensor-start").disabled = presence === "occupied";
  $("tensor-stop").disabled = !o.dashboard?.running;
  updateTemplateSummary();
}
function renderCompareList(runs) {
  const target = $("compare-list"); const checked = new Set([...target.querySelectorAll("input:checked")].map(x => x.value)); empty(target);
  for (const r of runs) { const label = node("label"), input = node("input"); input.type = "checkbox"; input.value = r.id; input.checked = checked.has(r.id); label.append(input, node("span", r.id)); target.append(label); }
}
function updateTemplateSummary() {
  const c = state.overview?.templates.find(x => x.id === $("train-config").value);
  $("train-config-summary").replaceChildren();
  if (!c) return;
  const summary = $("train-config-summary"); summary.append(node("b", c.name));
  summary.append(document.createTextNode(` · ${c.codec} · budget ${number(c.budget)} transitions`));
  if (c.description) summary.append(node("div", c.description));
  const warning = c.reward?.progress_mode === "delta" ? "Récompense v2 · coefficients proposés, non validés" : "Récompense v1 · peut favoriser l'immobilité";
  summary.append(node("small", warning));
}
async function refresh() {
  try {
    const o = await request("/api/overview"); state.csrf = o.csrf; state.overview = o; renderOverview(o);
    $("connection-dot").classList.remove("off"); $("connection").textContent = "Interface locale";
    if (state.selected && o.runs.some(r => r.id === state.selected)) await loadRun(state.selected);
    else if (!state.selected && o.runs.length) await loadRun(o.runs[0].id);
    if (!state.config && o.templates.length) await loadConfig(o.templates[0].id);
    if ($("eval-run").value) await loadEvalRun($("eval-run").value);
    const log = await request("/api/log/controller");
    $("job-log").textContent = log.lines?.length ? log.lines.join("").slice(-9000) : "Aucune commande lancée depuis cette interface.";
    $("job-log").scrollTop = $("job-log").scrollHeight;
    if (o.job && !o.job.running && o.job.returncode !== 0 && state.lastFailure !== o.job.pid) {
      state.lastFailure = o.job.pid;
      toast(`La commande ${o.job.label} a échoué (code ${o.job.returncode}). Voir le journal.`, true);
    }
  } catch (error) { $("connection-dot").classList.add("off"); $("connection").textContent = "Connexion perdue"; toast(error.message, true); }
}
const fields = { "config-name": ["name"], "config-seed": ["seed"], "config-speed": ["speed"], "config-budget": ["budget", "transitions"], "config-cap": ["budget", "cap_transitions"], "config-checkpoint": ["checkpoint_every_transitions"], "config-codec": ["action_codec"], "reward-mode": ["reward", "progress_mode"], "reward-progress": ["reward", "progress_scale"], "reward-time": ["reward", "time_cost_per_s"], "reward-finish": ["reward", "finish_bonus"], "reward-discount": ["reward", "discount_per_second"] };
function syncFields(cfg) {
  for (const [id, path] of Object.entries(fields)) {
    const value = path.reduce((obj, key) => obj?.[key], cfg);
    $(id).value = value ?? (id === "reward-mode" ? "potential" : "");
  }
}
function editField(id) {
  try {
    const cfg = JSON.parse($("config-json").value); const path = fields[id];
    let obj = cfg; for (const key of path.slice(0, -1)) { obj[key] ||= {}; obj = obj[key]; }
    const field = $(id), value = field.value;
    if (value !== "") obj[path.at(-1)] = field.type === "number" ? Number(value) : value;
    else if (id === "config-cap") delete obj[path.at(-1)];
    else if (id === "config-budget") obj[path.at(-1)] = null;
    $("config-json").value = JSON.stringify(cfg, null, 2);
    $("json-error").textContent = "";
  } catch (error) { $("json-error").textContent = error.message; }
}
async function loadConfig(id) {
  if (!id) return;
  try {
    const cfg = await request(`/api/configs/${encodeURIComponent(id)}`);
    state.config = cfg; state.configId = id; $("edit-config").value = id;
    $("config-json").value = JSON.stringify(cfg, null, 2); syncFields(cfg); $("new-config-id").value = "";
    $("json-error").textContent = "";
  } catch (error) { toast(error.message, true); }
}
function formNumber(id) { return $(id).value === "" ? null : Number($(id).value); }
function choosePage(name) {
  for (const nav of document.querySelectorAll("nav button")) nav.classList.toggle("active", nav.dataset.page === name);
  for (const page of document.querySelectorAll(".page")) page.classList.toggle("active", page.id === name);
  $("page-title").textContent = document.querySelector(`nav button[data-page="${name}"]`).textContent;
  window.location.hash = name;
}
function wire() {
  for (const item of document.querySelectorAll("nav button")) item.addEventListener("click", () => choosePage(item.dataset.page));
  const initial = window.location.hash.slice(1); if (document.getElementById(initial)?.classList.contains("page")) choosePage(initial);
  $("refresh").addEventListener("click", refresh); $("log-refresh").addEventListener("click", refresh);
  $("run-picker").addEventListener("change", e => { empty($("trend-result")); loadRun(e.target.value); });
  $("trend-button").addEventListener("click", async () => {
    if (!state.selected) return toast("Choisir un run", true);
    const result = await operation("trend", { run: state.selected, slices: formNumber("trend-slices") }, "Tendance calculée");
    if (!result) return;
    const target = $("trend-result"); empty(target);
    target.append(node("p", `Verdict indicatif : ${result.verdict}. Ce n'est pas une évaluation figée.`, "hint"));
    target.append(table(["Épisodes", "Transitions", "Progression médiane", "Meilleur", "Arrivées", "Commande max", "|direction|"],
      result.slices.map(s => [s.episodes, number(s.timesteps_end), number(s.progress_max_median, 3), number(s.progress_max_best, 3), number(s.finishes), number(s.command_share_max, 2), number(s.steer_abs_mean, 2)])));
  });
  $("train-config").addEventListener("change", updateTemplateSummary);
  $("train-unlimited").addEventListener("change", e => { $("train-budget").disabled = e.target.checked; });
  $("resume-unlimited").addEventListener("change", e => { $("resume-budget").disabled = e.target.checked; });
  $("train-form").addEventListener("submit", async e => {
    e.preventDefault(); const config = $("train-config").value; if (!config) return toast("Choisir une configuration", true);
    if (!confirm(`Lancer l'entraînement avec ${config} ? Le jeu doit être ouvert sur la bonne map.`)) return;
    const data = { config, speed: formNumber("train-speed"), budget: formNumber("train-budget"), until_stopped: $("train-unlimited").checked, trace: $("train-trace").checked };
    const result = await operation("train", data, "Commande lancée. Vérifier le journal : connexion au jeu et entraînement peuvent encore échouer.");
    if (result) { choosePage("overview"); state.selected = result.run; window.setTimeout(refresh, 1000); }
  });
  $("resume-button").addEventListener("click", async () => {
    const run = $("resume-run").value; if (!run) return toast("Choisir un run", true);
    if (!confirm(`Reprendre ${run} depuis son dernier checkpoint ?`)) return;
    await operation("resume", { run, budget: formNumber("resume-budget"), speed: formNumber("resume-speed"), until_stopped: $("resume-unlimited").checked, trace: $("resume-trace").checked }, "Reprise demandée. Vérifier le journal.");
  });
  $("stop-button").addEventListener("click", async () => {
    const run = $("resume-run").value; if (!run) return toast("Choisir un run", true);
    await operation("stop", { run }, "Arrêt demandé. La sauvegarde peut prendre du temps.");
  });
  $("eval-run").addEventListener("change", e => loadEvalRun(e.target.value));
  $("eval-form").addEventListener("submit", async e => {
    e.preventDefault(); const run = $("eval-run").value; if (!run) return toast("Choisir un run", true);
    const data = { run, checkpoint: $("eval-checkpoint").value, episodes: formNumber("eval-episodes"), speed: formNumber("eval-speed"), mode: $("eval-mode").value, first_episode: formNumber("eval-first"), official_finish: $("eval-official").checked, trace: $("eval-trace").checked };
    if (!confirm(`Voir ${run} conduire à vitesse ×${data.speed} (${data.mode}) ? Ouvrir la map dans le jeu avant de continuer.`)) return;
    await operation("eval", data, "Évaluation lancée. Observer le jeu et le journal.");
  });
  $("tensor-start").addEventListener("click", async () => { const result = await operation("dashboard", {}, "TensorBoard disponible sur 127.0.0.1:6006"); if (result) window.open("http://127.0.0.1:6006", "_blank", "noopener"); });
  $("tensor-stop").addEventListener("click", () => operation("dashboard-stop", {}, "TensorBoard arrêté"));
  $("compare-button").addEventListener("click", async () => {
    const runs = [...$("compare-list").querySelectorAll("input:checked")].map(x => x.value);
    const fraction = formNumber("compare-fraction");
    const result = await operation("compare", { runs, last_fraction: fraction }, "Comparaison calculée");
    if (!result) return; const target = $("compare-result"); empty(target);
    const wrapper = node("div", null, "result"); wrapper.append(node("p", result.controlled ? "Comparaison contrôlée selon D25 (vérifier aussi l'évaluation figée)." : `Non contrôlée. Différences : ${result.differences.join(", ") || "seeds ou nombre de runs insuffisant"}.`, "hint"));
    wrapper.append(node("p", `Budget commun : ${number(result.common_transitions)} transitions.`, "hint"));
    wrapper.append(table(["Run", "Seed", "Épisodes", "Arrivées", "Progression médiane (fin)", "Meilleur temps"], result.runs.map(r => [r.run, r.seed, r.episodes, r.finishes, number(r.tail_progress_max_median, 3), r.best_finish_ms ? number(r.best_finish_ms / 1000, 3) + " s" : "—"]))); target.append(wrapper);
  });
  $("edit-config").addEventListener("change", e => loadConfig(e.target.value));
  for (const id of Object.keys(fields)) $(id).addEventListener("change", () => editField(id));
  $("config-json").addEventListener("change", () => { try { syncFields(JSON.parse($("config-json").value)); $("json-error").textContent = ""; } catch (error) { $("json-error").textContent = error.message; } });
  $("save-config").addEventListener("click", async () => {
    try {
      const config = JSON.parse($("config-json").value), id = $("new-config-id").value.trim();
      if (!id) throw new Error("Indiquer un identifiant pour le nouveau fichier");
      const saved = await request("/api/configs", { id, config }); toast(`Configuration ${saved.id} enregistrée. Sélectionnez-la pour entraîner.`);
      state.config = null; await refresh(); await loadConfig(saved.id);
    } catch (error) { toast(error.message, true); $("json-error").textContent = error.message; }
  });
}
wire(); refresh(); window.setInterval(refresh, 5000);

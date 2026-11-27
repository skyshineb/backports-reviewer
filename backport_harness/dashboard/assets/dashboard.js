"use strict";

const $ = (id) => document.getElementById(id);
const pages = ["timeline", "queue", "settings"];
const settingsFields = {
  upstream: "lance-format/lance", upstream_branch: "main", base_ref: "",
  fork_path: "", target_branch: "", interval_minutes: 30,
  analysis_limit: 5, match_words: "fix bug bugfix",
};
const states = {
  applicable: "Применим", conflict: "Конфликт", empty: "Пустой патч",
  pending: "Ожидает проверки", error: "Ошибка Git",
  applied: "Применён", skipped: "Пропущен",
};
const jobStates = {
  queued: "В очереди", running: "В работе", awaiting_confirmation: "Нужен просмотр diff",
  confirmed: "Подтверждён", committing: "Запись в ветку", succeeded: "Завершён",
  failed: "Ошибка", canceled: "Отменён", stale: "HEAD изменился",
};
const jobNames = {
  scan: "Сканирование", rescan: "Обход от базы", probe: "Проверка Git",
  analysis: "Анализ Codex", apply: "Apply", adapt: "Адаптация Codex",
};
const recommendations = { apply: "Apply", skip: "Skip", review: "На рассмотрение" };
const relevance = {
  affected: "Проблема актуальна", already_fixed: "Уже исправлено",
  not_affected: "Проблема неактуальна", unclear: "Нужна ручная проверка",
};
const shortDate = new Intl.DateTimeFormat("ru", { day: "numeric", month: "short" });
const dateTime = new Intl.DateTimeFormat("ru", { dateStyle: "short", timeStyle: "short" });
const clock = new Intl.DateTimeFormat("ru", { hour: "2-digit", minute: "2-digit" });
const fragment = location.hash.slice(1);
if (/^[A-Za-z0-9_-]{24,}$/.test(fragment)) {
  sessionStorage.setItem("backports-token", fragment);
  history.replaceState(null, "", location.pathname);
}
const token = sessionStorage.getItem("backports-token") || "";
let page = "timeline";
let project = null;
let panel = null;
let timelinePage = 0;
let queuePage = 0;
let signature = "";
let generation = 0;
let refreshing = false;
let noticeTimeout;

function node(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value !== null && value !== undefined) element.setAttribute(name, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined && child !== false) {
      element.append(child instanceof Node ? child : String(child));
    }
  }
  return element;
}

function button(label, action, id, style = "button", extra = {}) {
  return node("button", {
    type: "button", class: style, "data-action": action, "data-id": id, ...extra,
  }, label);
}

function notice(message, error = false) {
  for (const id of ["notice", "sheet-notice"]) {
    const element = $(id);
    element.textContent = message;
    element.classList.toggle("error", error);
    element.hidden = !message;
  }
  clearTimeout(noticeTimeout);
  if (message && !error) noticeTimeout = setTimeout(() => notice(""), 3500);
}

async function api(path, body) {
  const headers = { Authorization: "Bearer " + token };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch("/api/" + path, {
    headers, method: body === undefined ? "GET" : "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Не удалось выполнить запрос.");
  return result;
}

function date(value, formatter = dateTime) {
  if (!value) return "—";
  const normalized = typeof value === "string" && !value.includes("T")
    ? value.replace(" ", "T") + "Z" : value;
  const time = new Date(normalized);
  return isNaN(time.valueOf()) ? "—" : formatter.format(time);
}

function metadata(id, pairs) {
  $(id).replaceChildren(...pairs.flatMap(([label, value]) => [
    node("dt", {}, label), node("dd", {}, value),
  ]));
}

function updateHeader(data) {
  const profile = data.profile;
  $("project-source").textContent = profile?.upstream || settingsFields.upstream;
  $("project-branch").textContent = profile?.upstream_branch || settingsFields.upstream_branch;
  $("connection").textContent = profile?.paused ? "На паузе" : "Локальный режим";
  $("scan-timeline").disabled = !profile;
  for (const control of $("queue").querySelectorAll(".queue-controls button")) {
    control.disabled = !profile;
  }
  $("pause").textContent = profile?.paused ? "Возобновить" : "Пауза";
  const next = !profile ? "30 мин" : profile.rewrite_detected ? "Требуется обход от базы"
    : profile.paused ? "Пауза" : (profile.next_scan_at ? date(profile.next_scan_at * 1000, clock) : "Сейчас");
  const warning = data.fork_error || data.last_scan?.error || "";
  $("timeline-warning").textContent = warning;
  $("timeline-warning").hidden = !warning;
  metadata("source-meta", [
    [profile ? "Следующий обход" : "Интервал", next],
    ...(profile ? [["Целевая ветка", profile.target_branch]] : []),
    ...(data.counts ? [["На рассмотрении", String(data.counts.review)], ["Применено", String(data.counts.applied)]] : []),
  ]);
  metadata("queue-meta", [
    [profile ? "Следующий обход" : "Интервал", next],
    ...(data.last_scan ? [["Последний обход", jobStates[data.last_scan.status]]] : []),
  ]);
}

function empty(title, message, control, art = false) {
  return node("div", { class: art ? "empty" : "empty single" },
    node("div", { class: "empty-copy" }, node("h2", {}, title), node("p", {}, message), control),
    art ? node("div", { class: "drawing" },
      node("img", { src: "/assets/drafting.webp", alt: "", width: "600", height: "400" })) : null,
  );
}

function pagination(data, action) {
  if (!data.total || data.total <= data.page_size) return null;
  const last = Math.ceil(data.total / data.page_size) - 1;
  return node("div", { class: "pagination" },
    button("Назад", action, data.page - 1, "button small", { disabled: data.page === 0 ? "" : null }),
    String(data.page + 1) + " / " + String(last + 1),
    button("Дальше", action, data.page + 1, "button small", { disabled: data.page >= last ? "" : null }),
  );
}

function commitRow(commit) {
  const status = states[commit.decision || commit.applicability];
  const summary = [
    commit.recommendation ? "Рекомендация " + recommendations[commit.recommendation] : "",
    commit.stale ? "HEAD изменился" : "",
    commit.notes ? "Есть заметки Codex" : "",
  ].filter(Boolean).join(" · ");
  const apply = commit.decision ? null : button("Apply",
    commit.applicability === "conflict" ? "adapt-prompt" : "apply", commit.id,
    "button primary small", { disabled: commit.applicability === "pending" ? "" : null });
  const skip = commit.decision === "applied" ? null : button(
    commit.decision === "skipped" ? "Отменить Skip" : "Skip",
    commit.decision === "skipped" ? "unskip" : "skip", commit.id, "text-button");
  return node("li", { class: "commit" },
    node("div", { class: "commit-time" },
      node("time", { datetime: commit.committed_at }, date(commit.committed_at, shortDate)),
      node("code", {}, commit.sha.slice(0, 10))),
    node("div", {},
      button(commit.subject || "Коммит " + commit.sha.slice(0, 10), "commit", commit.id, "subject",
        { title: commit.description || commit.subject }),
      summary ? node("p", { class: "commit-summary" }, summary) : null),
    node("div", { class: "commit-state" }, node("span", {}, status),
      commit.severity ? node("span", { class: "severity " + commit.severity }, commit.severity) : null),
    node("div", { class: "row-actions" }, apply, skip,
      button("Analyze", "analysis-prompt", commit.id, "text-button")),
  );
}

function renderTimeline(data) {
  const content = $("timeline-content");
  content.setAttribute("aria-busy", "false");
  if (!data.profile) {
    content.replaceChildren(empty("Настройте проект", "Укажите базовую версию upstream и ветку локального форка.",
      button("Открыть настройки", "go-settings", null, "button primary"), true));
    return;
  }
  if (!data.commits.length) {
    const filtered = $("search").value || $("filter").value;
    const controls = pagination(data, "timeline-page");
    content.replaceChildren(empty(
      filtered ? "Совпадений нет" : "Пока нет фиксов",
      filtered ? "Измените запрос или статус." : "Подходящие коммиты появятся после сканирования upstream.",
      null, !filtered,
    ), ...(controls ? [controls] : []));
    return;
  }
  const controls = pagination(data, "timeline-page");
  content.replaceChildren(node("ol", { class: "commit-list" }, data.commits.map(commitRow)),
    ...(controls ? [controls] : []));
}

function jobRow(job) {
  const title = job.subject || jobNames[job.kind];
  const text = [jobStates[job.status], job.cancel_requested && job.status === "running" ? "Запрошена отмена" : "",
    date(job.updated_at)].filter(Boolean).join(" · ");
  return node("article", { class: "queue-row" },
    node("div", {}, button(title, "job", job.id, "job-name"),
      node("p", { class: job.error ? "failed" : "" }, text, job.error ? " · " + job.error : "")),
    button(job.status === "awaiting_confirmation" ? "Открыть diff" : "Подробнее", "job", job.id, "button small"),
  );
}

function renderQueue(data) {
  const controls = pagination(data, "queue-page");
  $("queue-content").replaceChildren(
    ...(data.jobs.length ? data.jobs.map(jobRow) : [empty("Очередь пуста", "Здесь появятся сканирования и попытки обработки.")]),
    ...(controls ? [controls] : []),
  );
}

function fillSettings() {
  const values = { ...settingsFields, ...project?.profile };
  for (const name of Object.keys(settingsFields)) {
    $("profile-form").elements.namedItem(name).value = values[name];
  }
}

function activate(tab) {
  page = tab;
  signature = "";
  for (const id of pages) $(id).hidden = id !== tab;
  for (const nav of document.querySelectorAll("nav button")) {
    if (nav.dataset.tab === tab) nav.setAttribute("aria-current", "page");
    else nav.removeAttribute("aria-current");
  }
  if (tab === "settings") fillSettings();
  refresh();
}

async function refresh(poll = false) {
  if (poll && refreshing) return;
  const request = ++generation;
  const activePage = page;
  refreshing = true;
  try {
    const params = new URLSearchParams({
      q: activePage === "timeline" ? $("search").value : "",
      state: activePage === "timeline" ? $("filter").value : "",
      page: String(activePage === "timeline" ? timelinePage : 0),
    });
    const data = await api("overview?" + params);
    if (request !== generation) return;
    project = data;
    updateHeader(data);
    $("provider-note").textContent = data.codex_available ? "Провайдер Codex настроен."
      : "Для анализа Codex задайте OPENAI_API_KEY при запуске сервиса.";
    if (activePage === "timeline") {
      const next = JSON.stringify([data.profile?.id, data.commits, data.total, timelinePage, params.toString()]);
      if (next !== signature) renderTimeline(data);
      signature = next;
    }
    if (activePage === "queue") {
      const queue = await api("queue?page=" + queuePage);
      if (request !== generation) return;
      const next = JSON.stringify(queue);
      if (next !== signature) renderQueue(queue);
      signature = next;
    }
    if (poll && $("sheet").open && panel?.type === "job" && panel.live) {
      const current = panel;
      const job = await api("jobs/" + current.id);
      if (panel === current && $("sheet").open) showJob(job);
    }
  } catch (error) {
    if (request !== generation) return;
    $("connection").textContent = "Сервис недоступен";
    if (!project) {
      $("timeline-content").setAttribute("aria-busy", "false");
      $("timeline-content").replaceChildren(empty("Откройте локальную ссылку", error.message));
    }
    if (!poll) notice(error.message, true);
  } finally {
    if (request === generation) refreshing = false;
  }
}

function sheet(title, label, children) {
  $("sheet-title").textContent = title;
  $("sheet-label").textContent = label;
  $("sheet-body").replaceChildren(...children);
  if (!$("sheet").open) $("sheet").showModal();
}

function section(title, ...contents) {
  return node("section", {}, node("h3", {}, title), contents);
}

async function openCommit(id) {
  const detail = await api("commits/" + id);
  const commit = detail.commit;
  panel = { type: "commit", id };
  const contents = [
    section("Статус", node("p", {}, states[commit.decision || commit.applicability],
      commit.severity ? " · " + commit.severity : "",
      commit.recommendation ? " · " + recommendations[commit.recommendation] : ""),
      commit.fork_sha ? node("p", {}, "Проверено на ", node("code", {}, commit.fork_sha)) : null,
      commit.applied_sha ? node("p", {}, "Коммит в форке ", node("code", {}, commit.applied_sha)) : null),
    section("Описание", node("p", {}, commit.description || commit.subject)),
  ];
  if (commit.notes) contents.push(section("Заметки Codex", node("p", {}, relevance[commit.relevance]),
    node("p", {}, commit.notes), node("code", {}, commit.analysis_sha)));
  if (detail.jobs.length) contents.push(section("Попытки", detail.jobs.map(jobRow)));
  if (detail.events.length) contents.push(section("Решения оператора", detail.events.map(
    (event) => node("p", {}, date(event.created_at), " · ",
      { skip: "Skip", unskip: "Отмена Skip", applied: "Apply" }[event.action] || event.action))));
  sheet(commit.subject || "Коммит", commit.sha, contents);
}

async function promptEditor(id, action) {
  const { commit } = await api("commits/" + id);
  panel = { type: "prompt", id };
  const adapt = action === "adapt";
  const text = adapt ? "Адаптируй фикс к текущей ветке и сохрани поведение локальных изменений."
    : "Оцени, актуальна ли проблема для этого форка. Обоснуй влияние и тяжесть.";
  const editor = node("textarea", { name: "prompt", maxlength: "6000", rows: "7" }, text);
  const submit = node("button", { type: "submit", class: "button primary" },
    adapt ? "Подготовить diff" : "Запустить анализ");
  const form = node("form", { class: "prompt-form" }, node("label", {}, "Промпт", editor),
    node("div", { class: "dialog-actions" }, submit));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const result = await api("commits/" + id + "/" + action, { prompt: editor.value });
      notice("");
      await openJob(result.job_id);
      refresh();
    } catch (error) {
      notice(error.message, true);
    } finally {
      submit.disabled = false;
    }
  });
  sheet(adapt ? "Подготовить адаптацию" : "Анализ Codex", commit.subject, [form]);
  editor.focus();
}

function diffBlock(diff) {
  return node("pre", { tabindex: "0", "aria-label": "Diff" },
    diff.split("\n").map((line) => node("span", {
      class: "diff-line" + (line.startsWith("+") ? " diff-plus" : line.startsWith("-") ? " diff-minus" : ""),
    }, line || " ")),
  );
}

async function openJob(id) {
  panel = null;
  showJob(await api("jobs/" + id));
}

function showJob(job) {
  const next = JSON.stringify(job);
  if (panel?.type === "job" && panel.id === job.id && panel.signature === next) return;
  panel = { type: "job", id: job.id, signature: next,
    live: ["queued", "running", "confirmed", "committing"].includes(job.status) };
  const result = job.result ? JSON.parse(job.result) : {};
  const controls = [];
  const content = [section("Статус", node("p", {}, jobStates[job.status]),
    job.error ? node("p", { class: "warning-strip" }, job.error) : null,
    job.cancel_requested && job.status === "running" ? node("p", {}, "Запрошена отмена") : null,
    job.expected_sha ? node("p", {}, "HEAD ", node("code", {}, job.expected_sha)) : null,
    job.prepared_sha ? node("p", {}, "Подготовленный SHA ", node("code", {}, job.prepared_sha)) : null)];
  if (job.prompt) content.push(section("Промпт", node("p", {}, job.prompt)));
  if (result.notes) content.push(section("Заметки Codex", node("p", {}, result.notes)));
  if (result.evidence?.length) content.push(section("Код", result.evidence.map(
    ({ path, line }) => node("p", {}, node("code", {}, path + ":" + line)))));
  if (result.new_commits !== undefined) content.push(section("Сканирование",
    node("p", {}, "Новых коммитов " + result.new_commits), node("code", {}, result.head)));
  if (job.diff) content.push(section("Diff", diffBlock(job.diff)));
  if (job.kind === "apply" && result.applicability === "conflict") {
    content.push(section("Конфликт на свежем HEAD", button(
      "Подготовить адаптацию", "adapt-prompt", job.commit_id, "button primary")));
  }
  if (job.status === "awaiting_confirmation") controls.push(button(
    "Подтвердить запись", "confirm", job.id, "button primary", { "data-sha": job.prepared_sha }));
  if (["queued", "running", "awaiting_confirmation", "confirmed"].includes(job.status)) {
    controls.push(button("Отменить", "cancel", job.id, "button",
      { disabled: job.cancel_requested ? "" : null }));
  }
  if (["failed", "canceled", "stale"].includes(job.status) || (job.status === "committing" && job.error)) {
    controls.push(button(job.status === "stale" ? "Подготовить заново" : "Повторить", "retry", job.id));
  }
  if (controls.length) content.push(node("section", { class: "dialog-actions" }, controls));
  sheet(jobNames[job.kind], date(job.created_at), content);
}

async function handleAction(element) {
  const { action, id, sha } = element.dataset;
  if (action === "go-settings") return activate("settings");
  if (action === "commit") return openCommit(id);
  if (action === "job") return openJob(id);
  if (action === "analysis-prompt" || action === "adapt-prompt") {
    return promptEditor(id, action === "adapt-prompt" ? "adapt" : "analysis");
  }
  if (action === "timeline-page" || action === "queue-page") {
    if (action === "timeline-page") timelinePage = Number(id);
    else queuePage = Number(id);
    return refresh();
  }
  let result;
  if (action === "scan" || action === "rescan") {
    result = await api("scans", { rescan: action === "rescan" });
  } else if (action === "pause") {
    await api("pause", { paused: !project?.profile?.paused });
  } else if (["apply", "skip", "unskip"].includes(action)) {
    result = await api("commits/" + id + "/" + action, {});
    if (!result.job_id) notice(action === "skip" ? "Решение Skip сохранено." : "Решение Skip отменено.");
  } else if (["confirm", "cancel", "retry"].includes(action)) {
    result = await api("jobs/" + id + "/" + action, action === "confirm" ? { prepared_sha: sha } : {});
  }
  if (result?.job_id) await openJob(result.job_id);
  refresh();
}

document.addEventListener("click", async (event) => {
  const tab = event.target.closest("[data-tab]");
  if (tab) return activate(tab.dataset.tab);
  const action = event.target.closest("[data-action]");
  if (!action || action.disabled) return;
  const reactivate = !["commit", "job", "adapt-prompt", "analysis-prompt"].includes(action.dataset.action);
  if (reactivate) action.disabled = true;
  try {
    await handleAction(action);
  } catch (error) {
    notice(error.message, true);
  } finally {
    if (reactivate) action.disabled = false;
  }
});

$("profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("[type=submit]");
  submit.disabled = true;
  try {
    const values = Object.fromEntries(new FormData(form).entries());
    values.interval_minutes = Number(values.interval_minutes);
    values.analysis_limit = Number(values.analysis_limit);
    await api("profile", values);
    timelinePage = 0;
    queuePage = 0;
    notice("Настройки сохранены.");
    activate("timeline");
  } catch (error) {
    notice(error.message, true);
  } finally {
    submit.disabled = false;
  }
});

let pendingSearch;
$("search").addEventListener("input", () => {
  clearTimeout(pendingSearch);
  pendingSearch = setTimeout(() => { timelinePage = 0; refresh(); }, 170);
});
$("filter").addEventListener("change", () => { timelinePage = 0; refresh(); });
$("sheet").addEventListener("close", () => { panel = null; notice(""); });
fillSettings();
refresh();
setInterval(() => refresh(true), 2800);

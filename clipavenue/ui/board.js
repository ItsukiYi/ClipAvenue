// ClipAvenue — Metro-map Dashboard
// Renders dashboard state and stays live via SSE.

const app = document.getElementById("app");
const modal = document.getElementById("modal");

let state = null;
let selectedStation = null;
let firstPaint = true;
let logEntries = [];
let loginPollTimer = null;
let loginQrData = null;

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

async function postJSON(url, data = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children.flat()) {
    if (child == null) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

function fmtAgo(epochSeconds) {
  if (!epochSeconds) return "";
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 90) return "刚刚";
  if (diff < 3600) return `${Math.round(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.round(diff / 3600)} 小时前`;
  return `${Math.round(diff / 86400)} 天前`;
}

function subscribe(url, onChange) {
  let timer = null;
  const source = new EventSource(url);
  source.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      if (data.type !== "change") return;
    } catch { return; }
    clearTimeout(timer);
    timer = setTimeout(onChange, 250);
  };
  source.onerror = () => {};
  return source;
}

// Live Log — only auto-scroll if user is near bottom
function subscribeLogs() {
  const source = new EventSource("/api/logs/stream");
  source.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      if (data.type === "log") {
        logEntries.push(data);
        if (logEntries.length > 500) logEntries.shift();
        renderLogPanel();
      }
    } catch { return; }
  };
  return source;
}

function renderLogPanel() {
  const body = document.getElementById("log-body");
  if (!body) return;
  const nearBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 80;
  const visible = logEntries.slice(-80);
  body.innerHTML = "";
  for (const e of visible) {
    body.append(el("div", { class: "le" },
      el("span", { class: "lt" }, (e.ts || "").slice(11, 23)),
      el("span", { class: `lv ${e.level}` }, (e.level === "warn" ? "WARN" : (e.level || "").toUpperCase())),
      el("span", { class: "ls" }, e.source || ""),
      el("span", { class: "lm" }, e.msg || "")));
  }
  if (nearBottom) body.scrollTop = body.scrollHeight;
}

// Bilibili Login
async function startLogin() {
  try {
    const data = await getJSON("/api/login/qrcode");
    if (!data.success) { alert("获取二维码失败: " + (data.error || "")); return; }
    const qrData = typeof data.qrcode === "string" ? JSON.parse(data.qrcode) : data.qrcode;
    const loginUrl = qrData?.data?.url || "";
    if (!loginUrl) { alert("二维码数据解析失败"); return; }
    loginQrData = typeof data.qrcode === "string" ? data.qrcode : JSON.stringify(qrData);

    modal.innerHTML = "";
    const qrImg = `https://api.qrserver.com/v1/create-qr-code/?size=240x240&data=${encodeURIComponent(loginUrl)}`;
    modal.append(
      el("span", { class: "modal-close", onclick: closeLoginModal }, "ESC · 关闭"),
      el("div", { class: "modal-page" },
        el("div", { style: "background:var(--surface);color:var(--text);max-width:400px;padding:32px;border-radius:12px;text-align:center" },
          el("h3", { style: "font-family:var(--mono);font-size:calc(14px * var(--fs-scale));margin-bottom:16px" }, "B站 扫码登录"),
          el("img", { src: qrImg, style: "width:240px;height:240px;border-radius:8px;border:1px solid var(--border);margin-bottom:16px", alt: "" }),
          el("div", { style: "font-size:calc(12px * var(--fs-scale));color:var(--text-2);margin-bottom:8px" }, "请使用 B站 App 扫描二维码"),
          el("div", { id: "login-status", style: "font-family:var(--mono);font-size:calc(11px * var(--fs-scale));color:var(--text-3)" }, "等待扫码..."))));
    modal.classList.add("open");

    if (loginPollTimer) clearInterval(loginPollTimer);
    loginPollTimer = setInterval(async () => {
      try {
        const res = await postJSON("/api/login/check", { ret: loginQrData });
        if (res.success) {
          const el2 = document.getElementById("login-status");
          if (el2) { el2.textContent = "登录成功!"; el2.style.color = "var(--green)"; }
          clearInterval(loginPollTimer);
          loginPollTimer = null;
          setTimeout(closeLoginModal, 1500);
        }
      } catch (e) { /* poll again */ }
    }, 2000);
  } catch (e) { alert("登录失败: " + e.message); }
}

function closeLoginModal() {
  if (loginPollTimer) { clearInterval(loginPollTimer); loginPollTimer = null; }
  modal.classList.remove("open");
}

// Upload helpers
async function startUpload(filePath, projectId, title) {
  try {
    const result = await postJSON("/api/upload/start", { project_id: projectId, file_path: filePath, title: title || filePath.split("/").pop() || filePath });
    if (result.status === "captcha") { showCaptchaDialog(projectId); }
    else if (result.status === "completed") { alert(`投稿成功! BVID: ${result.bvid}`); }
    else if (result.status === "failed") { alert(`投稿失败: ${result.error}`); }
  } catch (e) { alert(`上传出错: ${e.message}`); }
}

async function showCaptchaDialog(projectId) {
  const code = prompt("投稿需要验证码，请输入验证码:");
  if (!code) return;
  try {
    const result = await postJSON("/api/upload/captcha", { project_id: projectId, code });
    if (result.status === "completed") { alert(`验证成功! BVID: ${result.bvid}`); }
    else if (result.status === "captcha") { alert("验证码不正确"); showCaptchaDialog(projectId); }
    else if (result.status === "failed") { alert(`投稿失败: ${result.error}`); }
  } catch (e) { alert(`验证出错: ${e.message}`); }
}

// Archive helpers
async function archiveBackup(projectId) {
  const dest = prompt("备份目标目录:", "../backups");
  if (!dest) return;
  try {
    const r = await postJSON("/api/archive/backup", { project_id: projectId, dest_dir: dest });
    alert(r.success ? `备份完成: ${r.backup_path}` : `备份失败: ${r.error}`);
  } catch (e) { alert(e.message); }
}

async function archiveCleanup(projectId) {
  const level = prompt("清理级别: clips_only / all_except_raw / full / none", "clips_only");
  if (!level) return;
  const dry = confirm("预览模式?") === true;
  try {
    const r = await postJSON("/api/archive/cleanup", { project_id: projectId, level, dry_run: dry });
    alert(dry ? `预览: ${r.deleted_files} 文件 (${r.freed_mb} MB)` : `清理: ${r.deleted_files} 文件 (${r.freed_mb} MB)`);
  } catch (e) { alert(e.message); }
}

// Clip pipeline
async function startClipPipeline(projectId, videoPath) {
  try {
    const r = await postJSON("/api/clip/start", { project_id: projectId, video_path: videoPath });
    if (r.success) alert(`剪辑完成! 生成 ${r.clip_count} 切片`);
    else alert(`剪辑失败: ${r.error || "未知"}`);
  } catch (e) { alert(e.message); }
}

async function showClipAnalysis(projectId) {
  try {
    const a = await getJSON(`/api/clip/analysis/${projectId}`);
    if (a.status === "not_analyzed") { alert("尚未分析"); return; }
    modal.innerHTML = "";
    modal.append(
      el("span", { class: "modal-close", onclick: closeModal }, "ESC · 关闭"),
      el("div", { class: "modal-page" },
        el("div", { style: "background:var(--surface);padding:24px;border-radius:12px;border:1px solid var(--border-soft)" },
          el("div", { style: "font-family:var(--mono);margin-bottom:12px" }, `话题: ${a.topic_count} 切片: ${a.clip_count}`),
          (a.topics || []).map(t => el("div", { style: "margin-bottom:8px;border-left:2px solid var(--amber);padding-left:10px" },
            el("div", { style: "font-size:calc(10px * var(--fs-scale));color:var(--text-3)" }, `#${t.index} ${t.label || ""}`),
            el("div", { style: "font-size:calc(11px * var(--fs-scale));color:var(--text-2)" }, (t.text || "").slice(0, 100)))))));
    modal.classList.add("open");
  } catch (e) { console.error(e); }
}

// Toast
function showToast(msg, type) {
  const old = document.getElementById("toast");
  if (old) old.remove();
  const t = el("div", { id: "toast",
    style: `position:fixed;bottom:24px;right:24px;padding:14px 20px;border-radius:10px;z-index:100;font-family:var(--mono);font-size:calc(12px * var(--fs-scale));max-width:380px;line-height:1.5;background:${type === "error" ? "var(--red-dim)" : "var(--green-dim)"};border:1px solid ${type === "error" ? "rgba(229,84,75,.4)" : "rgba(79,194,131,.4)"};color:${type === "error" ? "var(--red)" : "var(--green)"};white-space:pre-wrap` });
  t.textContent = msg;
  document.body.append(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = "opacity .5s"; }, 4000);
  setTimeout(() => t.remove(), 4500);
}

// Recorder controls
async function startRecording() {
  const platform = document.getElementById("rec-platform").value;
  const url = document.getElementById("rec-url").value.trim();
  const streamer = document.getElementById("rec-streamer").value.trim();
  if (!url || !streamer) { alert("请填写完整信息"); return; }
  try {
    const r = await postJSON("/api/recorder/start", { platform, url, streamer });
    if (r.success) { document.getElementById("rec-url").value = ""; document.getElementById("rec-streamer").value = ""; showToast(`录制已启动: ${r.info || ""}`, "info"); }
    else { showToast(r.error || "启动失败", "error"); }
  } catch (e) { showToast(`请求失败: ${e.message}`, "error"); }
}

async function stopTask(taskId) {
  if (!confirm("停止录制?")) return;
  try { await postJSON(`/api/recorder/stop/${taskId}`); } catch (e) { alert(e.message); }
}

async function promptClip(taskId, task) {
  try {
    const resp = await fetch(`/api/project/${taskId}/files`);
    const data = await resp.json();
    if (data.files && data.files.length > 0) {
      const f = data.files[0];
      const dir = (task.output_dir || "").replace(/\\/g, "/").replace(/\/+$/, "");
      const fullPath = dir + '/' + f.path;
      if (!confirm(`使用录播文件: ${f.name} (${f.size_mb} MB)?`)) return;
      const r = await postJSON("/api/clip/start", { project_id: taskId, video_path: fullPath });
      if (r.success) {
        showToast(`剪辑流水线已后台启动: ${f.name}`, "info");
      } else {
        alert("启动失败: " + (r.error || "未知"));
      }
      return;
    }
  } catch(e) { console.error(e); }
  const p = prompt("视频文件路径:", task.output_dir || "");
  if (!p) return;
  try {
    const r = await postJSON("/api/clip/start", { project_id: taskId, video_path: p });
    if (r.success) showToast("剪辑已启动", "info");
    else alert("失败: " + (r.error || ""));
  } catch(e) { alert(e.message); }
}

async function promptUpload(taskId, task) {
  const p = prompt("文件路径:", task.output_dir || "");
  if (!p) return;
  const t = prompt("标题:", `${task.streamer} 直播切片`);
  if (!t) return;
  await startUpload(p, taskId, t);
}

const STATION_ICONS = { mic: "🎙", disk: "💾", text: "📝", brain: "🧠", scissors: "✂", sub: "🖹", upload: "⬆", archive: "📦" };
const STATUS_LABELS = { pending: "等待", recording: "录制中", completed: "完成", failed: "故障", warning: "警告", verifying: "验证", in_progress: "进行中", critical: "告警", unknown: "未知" };

// Render: Slate
function renderSlate(s) {
  const badge = el("span", { class: `live-badge${(s.active_count||0)+(s.verifying_count||0) > 0 ? " active" : ""}` },
    el("span", { class: "dot" }), (s.active_count||0) + (s.verifying_count||0) > 0 ? `${(s.active_count||0)+(s.verifying_count||0)} 活跃` : "就绪");
  const loggedIn = s.recorder_check && s.recorder_check.bilibili_logged_in;
  const btn = el("span", { class: `btn ${loggedIn ? "" : "primary"}`, style: "font-size:calc(10px * var(--fs-scale));padding:4px 10px", onclick: startLogin }, loggedIn ? "B站已登录" : "登录B站");
  return el("header", { class: "slate" },
    el("span", { class: "logo" }, "C"),
    el("div", {}, el("h1", {}, "ClipAvenue"), el("span", { class: "subtitle" }, "直播流水线")), btn, el("span", { class: "spacer" }), badge);
}

// Render: Summary
function renderSummary(s) {
  return el("div", { class: "summary-bar" },
    el("span", { class: "stat" }, el("span", { class: "num green" }, String(s.completed_count||0)), "完成"),
    el("span", { class: "stat" }, el("span", { class: "num amber" }, String(s.active_count||0)), "活跃"),
    s.failed_count ? el("span", { class: "stat" }, el("span", { class: "num red" }, String(s.failed_count)), "故障") : null,
    el("span", { class: "spacer" }),
    el("span", {}, `${s.project_count} 项目 · ${fmtAgo(s.timestamp)}`));
}

// Render: Storage
function renderStoragePanel(s) {
  const st = s.storage; if (!st) return null;
  const pct = Math.min(100, Math.max(0, st.usage_pct||0));
  const c = pct > 95 ? "var(--red)" : pct > 85 ? "var(--amber)" : "var(--green)";
  return el("div", { class: "storage-panel" },
    el("span", { class: "sp-label" }, "磁盘"),
    el("div", { style: "flex:1;min-width:100px" },
      el("div", { class: "sp-bar" }, el("i", { style: `width:${pct}%;background:${c}` })),
      el("div", { style: "display:flex;justify-content:space-between;font-size:calc(10px * var(--fs-scale));color:var(--text-3)" },
        el("span", {}, `剩余 ${st.free_gb||"?"} GB`), el("span", {}, `总计 ${st.total_gb||"?"} GB`))),
    el("span", { style: `font-size:calc(18px * var(--fs-scale));font-weight:700;color:${c}` }, `${pct}%`),
    el("div", { class: "sp-actions" },
      el("span", { class: "btn", onclick: previewCleanup }, "预览"), el("span", { class: "btn", onclick: runCleanup }, "清理")));
}

async function previewCleanup() {
  try {
    const plan = await getJSON("/api/storage/plan");
    const entries = Object.entries(plan.plan||{});
    modal.innerHTML = "";
    modal.append(el("span", { class: "modal-close", onclick: closeModal }, "ESC · 关闭"),
      el("div", { class: "modal-page" }, el("div", { style: "background:var(--surface);padding:24px;border-radius:12px;border:1px solid var(--border-soft)" },
        el("div", { style: "font-family:var(--mono);margin-bottom:12px" }, `可释放 ${plan.estimated_freed_gb||0} GB`),
        entries.map(([cat, files]) => el("div", { style: "margin-bottom:6px" },
          el("div", { style: "font-family:var(--mono);font-size:calc(10px * var(--fs-scale));color:var(--text-2)" }, `${cat} (${files.length})`))).flat(),
        el("div", { style: "margin-top:12px;display:flex;gap:8px;justify-content:flex-end" },
          el("span", { class: "btn", onclick: closeModal }, "关闭")))));
    modal.classList.add("open");
  } catch (e) { console.error(e); }
}

async function runCleanup() {
  if (!confirm("确认清理?")) return;
  try { const r = await postJSON("/api/storage/cleanup", { dry_run: false }); alert(`清理 ${r.deleted_count} 文件, ${r.deleted_gb} GB`); }
  catch (e) { alert(e.message); }
}

function closeModal() { modal.classList.remove("open"); }

// Render: Recorder panel
function renderRecorderPanel(s) {
  const tasks = s.recorder?.tasks || [];
  return el("div", { class: "control-panel" },
    el("h3", {}, "录制控制"),
    el("div", { class: "ctrl-row" },
      el("div", { class: "ctrl-field" },
        el("label", {}, "平台"),
        el("select", { id: "rec-platform" }, el("option", { value: "bilibili" }, "B站"), el("option", { value: "douyin" }, "抖音"))),
      el("div", { class: "ctrl-field" },
        el("label", {}, "直播间 URL"),
        el("input", { id: "rec-url", type: "text", placeholder: "https://live.bilibili.com/..." })),
      el("div", { class: "ctrl-field" },
        el("label", {}, "主播名"),
        el("input", { id: "rec-streamer", type: "text", placeholder: "主播名" })),
      el("span", { class: "btn primary", onclick: startRecording, style: "flex:none" }, "开始录制")),
    tasks.length ? el("div", { class: "task-list" }, tasks.map(t => renderTaskItem(t))) : null);
}

function renderTaskItem(t) {
  const sl = STATUS_LABELS[t.status] || t.status;
  return el("div", { class: "task-item" },
    el("span", { class: `t-status ${t.status}` }),
    el("span", { class: "t-name" }, `${t.streamer} (@${t.platform})`),
    el("span", { class: "t-meta" }, `${sl}${t.duration_seconds ? ` ${Math.round(t.duration_seconds/60)}m` : ""}`),
    (t.status === "recording" || t.status === "watching") ? el("span", { class: "t-action btn danger", onclick: () => stopTask(t.task_id) }, "停") : null,
    t.status === "completed" ? el("span", { class: "t-action btn primary", onclick: () => promptClip(t.task_id, t) }, "剪辑") : null,
    t.status === "completed" ? el("span", { class: "t-action btn", onclick: () => promptUpload(t.task_id, t) }, "投稿") : null,
    t.status === "completed" ? el("span", { class: "t-action btn", onclick: () => archiveBackup(t.task_id) }, "备份") : null,
    t.status === "completed" ? el("span", { class: "t-action btn", onclick: () => archiveCleanup(t.task_id) }, "清理") : null);
}

// Render: Metro map
function renderMetro(s) {
  const rail = el("div", { class: "metro-rail" });
  for (const st of s.stations) {
    const icon = STATION_ICONS[st.icon] || "●";
    rail.append(el("div", { class: `station ${st.status}${selectedStation === st.id ? " selected" : ""}`, onclick: () => toggleStation(st.id) },
      el("span", { class: "station-line" }),
      el("span", { class: "station-node" }, el("span", { class: "icon" }, icon)),
      el("span", { class: "station-name" }, st.label),
      el("span", { class: "station-sub" }, st.detail || STATUS_LABELS[st.status] || st.status)));
  }
  return rail;
}

// Render: Station drawer
function renderDrawer(stationId) {
  if (!stationId || !state) return null;
  const st = state.stations.find(x => x.id === stationId);
  if (!st) return null;
  const body = el("div", { class: "drawer-body" });
  body.append(el("div", { class: "d-section" }, el("div", { class: "d-label" }, "状态"),
    el("div", { class: "d-value", style: `color:var(--${st.status === "completed" ? "green" : st.status === "failed" || st.status === "critical" ? "red" : "text-3"})` }, STATUS_LABELS[st.status] || st.status)));
  for (const [k, label] of Object.entries({ platform: "平台", streamer: "主播", error: "错误", pid: "PID", recorder_info: "录制工具" })) {
    if (st[k] != null && st[k] !== "") body.append(el("div", { class: "d-section" }, el("div", { class: "d-label" }, label), el("div", { class: "d-value" }, String(st[k]))));
  }
  return el("div", { class: "drawer" },
    el("div", { class: "drawer-head" }, el("h3", {}, `${st.label}`), el("span", { class: "close", onclick: () => toggleStation(st.id) }, "X")), body);
}

function toggleStation(stationId) { selectedStation = selectedStation === stationId ? null : stationId; render(); }

function renderEmpty() {
  return el("div", { class: "empty" },
    el("div", { class: "big" }, "暂无直播项目"), el("div", { class: "sub" }, "添加录制后自动显示流水线状态"));
}

// Page assembly
function render() {
  if (!state) return;
  document.body.classList.toggle("first", firstPaint);
  firstPaint = false;
  document.title = "ClipAvenue";
  app.innerHTML = "";
  app.append(renderSlate(state));
  app.append(renderSummary(state));
  app.append(renderStoragePanel(state));
  app.append(renderRecorderPanel(state));
  app.append(el("div", { class: "control-panel", style: "padding-bottom:16px" },
    el("div", { style: "display:flex;align-items:center;gap:10px;margin-bottom:6px" },
      el("span", { style: "width:6px;height:6px;border-radius:50%;background:var(--green)" }),
      el("h3", { style: "font-family:var(--mono);font-size:calc(11px * var(--fs-scale));letter-spacing:.12em;text-transform:uppercase;color:var(--text-2);margin:0" }, "运行日志"),
      el("span", { style: "font-size:calc(10px * var(--fs-scale));color:var(--text-3);font-family:var(--mono);margin-left:auto" }, String(logEntries.length))),
    el("div", { id: "log-body", style: "font-family:var(--mono);font-size:calc(10.5px * var(--fs-scale));line-height:1.55;height:260px;overflow-y:auto;background:var(--surface-2);border-radius:6px;border:1px solid var(--border-soft);padding:8px 12px" },
      logEntries.length === 0 ? el("div", { style: "color:var(--text-3);padding:8px" }, "暂无日志") : null)));
  app.append(renderMetro(state));
  const drawer = renderDrawer(selectedStation);
  if (drawer) app.append(drawer);
  if (state.project_count === 0) app.append(renderEmpty());
  renderLogPanel();
}

function normalize(s) {
  s.stations = Array.isArray(s.stations) ? s.stations : [];
  s.storage = s.storage || null;
  s.recorder = s.recorder || { tasks: [], active_count: 0 };
  return s;
}

async function refresh() {
  state = normalize(await getJSON("/api/state"));
  render();
}

refresh().catch(err => { app.innerHTML = ""; app.append(el("div", { class: "empty" }, el("div", { class: "big" }, "无法连接"), el("div", { class: "sub" }, String(err)))); });

subscribe("/api/events", () => refresh().catch(console.error));
subscribeLogs();

document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeLoginModal(); if (selectedStation) { selectedStation = null; render(); } } });
modal.addEventListener("click", (e) => { if (e.target === modal) closeLoginModal(); });
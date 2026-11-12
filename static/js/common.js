/* Shared helpers for every Haajiri page */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const initials = (name) => String(name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

async function api(url, opts = {}) {
  const init = { method: opts.method || "GET", headers: {}, credentials: "same-origin" };
  if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
  let res;
  try { res = await fetch(url, init); } catch (e) { throw new Error("Cannot reach the server. Check that the app is running."); }
  let data = {};
  try { data = await res.json(); } catch (e) { /* not JSON */ }
  if (res.status === 401 && !location.pathname.startsWith("/api") && location.pathname !== "/") { location.href = "/"; }
  if (!res.ok) throw new Error(data.error || "Something went wrong (" + res.status + ").");
  return data;
}

function toast(msg, kind = "") {
  let box = $(".toasts");
  if (!box) { box = document.createElement("div"); box.className = "toasts"; box.setAttribute("role", "status"); document.body.appendChild(box); }
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = msg;
  box.appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

/* ---------- modal ---------- */
let _modalCleanup = null;
function openModal(html, { wide = false, onClose } = {}) {
  closeModal();
  const scrim = document.createElement("div");
  scrim.className = "scrim";
  scrim.innerHTML = '<div class="modal ' + (wide ? "wide" : "") + '" role="dialog" aria-modal="true">' + html + "</div>";
  scrim.addEventListener("mousedown", (e) => { if (e.target === scrim) closeModal(); });
  document.body.appendChild(scrim);
  const onKey = (e) => { if (e.key === "Escape") closeModal(); };
  document.addEventListener("keydown", onKey);
  _modalCleanup = () => { document.removeEventListener("keydown", onKey); scrim.remove(); if (onClose) onClose(); };
  const first = $("input, select, button.primary", scrim);
  if (first) first.focus();
  return $(".modal", scrim);
}
function closeModal() { if (_modalCleanup) { const f = _modalCleanup; _modalCleanup = null; f(); } }

/* ---------- icons ---------- */
const ICON = {
  bell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10.3 20a2 2 0 0 0 3.4 0"/></svg>',
  today: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="17" rx="3"/><path d="M8 2v4M16 2v4M3 10h18"/></svg>',
  cam: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>',
  people: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.5-3.5 3-5.5 6.5-5.5s6 2 6.5 5.5M16 4.8a3.5 3.5 0 0 1 0 6.4M18 14.8c2 .6 3.3 2.4 3.5 5.2"/></svg>',
  sheet: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h8l5 5v13H6z"/><path d="M14 3v5h5M9 13h7M9 17h7"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/></svg>',
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5h0a1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
};

/* ---------- notification bell ---------- */
function mountBell(host) {
  host.classList.add("bell-wrap");
  host.innerHTML = '<button class="bell" aria-label="Notifications" aria-haspopup="true">' + ICON.bell + '<span class="dot hide">0</span></button><div class="bell-panel hide"></div>';
  const btn = $(".bell", host), dot = $(".dot", host), panel = $(".bell-panel", host);
  let known = null;

  async function refresh(announce) {
    try {
      const d = await api("/api/notifications");
      dot.textContent = d.unread > 99 ? "99+" : d.unread;
      dot.classList.toggle("hide", !d.unread);
      if (announce && known !== null && d.unread > known) toast(d.notifications[0].title);
      known = d.unread;
      panel.innerHTML = '<header><h3>Notifications</h3><button class="btn sm" data-all>Mark all read</button></header>' +
        (d.notifications.length ? d.notifications.map((n) =>
          '<div class="note ' + (n.is_read ? "" : "unread") + '"><b>' + esc(n.title) + "</b><span>" + esc(n.body) + "</span><small>" + esc(n.created_at.slice(5, 16)) + "</small></div>").join("")
          : '<div class="empty">Nothing yet. Class reminders and attendance results will appear here.</div>');
      const all = $("[data-all]", panel);
      if (all) all.onclick = async () => { await api("/api/notifications/read", { method: "POST", body: {} }); refresh(false); };
    } catch (e) { /* signed out */ }
  }
  btn.onclick = (e) => { e.stopPropagation(); panel.classList.toggle("hide"); if (!panel.classList.contains("hide")) refresh(false); };
  document.addEventListener("click", (e) => { if (!host.contains(e.target)) panel.classList.add("hide"); });
  refresh(false);
  setInterval(() => refresh(true), 20000);
  return refresh;
}

/* ---------- camera helpers ---------- */
async function openCamera(video) {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    throw new Error("This browser cannot use the camera here. Open the app at http://localhost:5000 or over HTTPS.");
  }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false }); }
  catch (e) { throw new Error("Camera blocked. Allow camera access in the browser address bar and try again."); }
  video.srcObject = stream;
  await video.play();
  return stream;
}
function stopCamera(stream) { if (stream) stream.getTracks().forEach((t) => t.stop()); }
function grabFrame(video, maxW = 640, quality = 0.82) {
  const w = video.videoWidth, h = video.videoHeight;
  if (!w) return null;
  const s = Math.min(1, maxW / w);
  const c = document.createElement("canvas");
  c.width = Math.round(w * s); c.height = Math.round(h * s);
  c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", quality);
}

/* ---------- face enrolment (used by students and teachers) ---------- */
function openFaceCapture(studentId, studentName, onDone) {
  const POSES = ["Look straight at the camera", "Turn slightly to your left", "Turn slightly to your right", "Tilt your chin up a little", "Tilt your chin down a little", "Smile", "Look straight again"];
  const SHOTS = 14;
  let stream = null;
  const m = openModal(
    '<div class="row between"><h2>Face setup' + (studentName ? " - " + esc(studentName) : "") + '</h2><button class="btn sm" data-x>Close</button></div>' +
    '<p class="muted">Sit in good light, face the camera and take off a cap or mask. We take ' + SHOTS + ' photos in about 8 seconds and follow your head movements.</p>' +
    '<div class="capture-box"><video playsinline muted></video><div class="oval"></div><div class="say" data-say>Starting the camera...</div></div>' +
    '<div class="bar"><i data-bar style="width:0"></i></div>' +
    '<div class="error-text" data-err></div>' +
    '<div class="row"><button class="btn primary grow" data-go disabled>Take photos</button></div>',
    { onClose: () => stopCamera(stream) });
  const video = $("video", m), say = $("[data-say]", m), bar = $("[data-bar]", m), go = $("[data-go]", m), errBox = $("[data-err]", m);
  $("[data-x]", m).onclick = closeModal;
  openCamera(video).then((s) => { stream = s; say.textContent = "Ready when you are"; go.disabled = false; })
    .catch((e) => { say.textContent = ""; errBox.textContent = e.message; });
  go.onclick = async () => {
    go.disabled = true; errBox.textContent = "";
    const shots = [];
    for (let i = 0; i < SHOTS; i++) {
      say.textContent = POSES[Math.floor(i / 2) % POSES.length];
      await new Promise((r) => setTimeout(r, 550));
      const f = grabFrame(video, 640, 0.9);
      if (f) shots.push(f);
      bar.style.width = Math.round(((i + 1) / SHOTS) * 80) + "%";
    }
    say.textContent = "Saving and learning your face...";
    try {
      const r = await api("/api/students/" + studentId + "/faces", { method: "POST", body: { images: shots } });
      bar.style.width = "100%";
      if (!r.saved) { errBox.textContent = "No face was found in any photo. Move closer, face the light and try again."; go.disabled = false; say.textContent = ""; return; }
      toast(r.saved + " photos saved" + (r.rejected ? " (" + r.rejected + " had no clear face)" : ""), "good");
      closeModal();
      if (onDone) onDone(r);
    } catch (e) { errBox.textContent = e.message; go.disabled = false; }
  };
}

/* ---------- timetable grid (read-only or clickable) ---------- */
function renderTimetable(host, tt, { editable = false, onCell, highlightToday = true } = {}) {
  const days = tt.days, slots = tt.slots;
  const cols = "92px repeat(" + days.length + ", minmax(110px, 1fr))";
  const nowD = new Date(), todayIdx = (nowD.getDay() + 6) % 7;
  const hhmm = ("0" + nowD.getHours()).slice(-2) + ":" + ("0" + nowD.getMinutes()).slice(-2);
  let html = '<div class="tt" style="grid-template-columns:' + cols + '"><div class="hd"></div>' +
    days.map((d, i) => '<div class="hd">' + esc(d) + (highlightToday && i === todayIdx ? ' <span class="chip">today</span>' : "") + "</div>").join("");
  slots.forEach((s) => {
    html += '<div class="tm">' + esc(s.label || "Period " + s.period_no) + "<small>" + esc(s.start_time) + " - " + esc(s.end_time) + "</small></div>";
    if (s.is_break) { html += '<div class="brk">' + esc(s.label || "Break") + "</div>"; return; }
    days.forEach((d, di) => {
      const c = tt.cells[di + "-" + s.period_no];
      const live = highlightToday && di === todayIdx && hhmm >= s.start_time && hhmm < s.end_time;
      const body = c && c.subject_id ? "<b>" + esc(c.subject) + "</b><small>" + esc(c.teacher || "") + (c.room ? " &middot; " + esc(c.room) : "") + "</small>" : '<span class="free">' + (editable ? "Tap to assign" : "Free") + "</span>";
      html += '<div class="cell ' + (editable ? "edit" : "") + (live ? " now" : "") + (c && c.subject_id ? "" : " free") + '" data-day="' + di + '" data-p="' + s.period_no + '"' + (editable ? ' tabindex="0" role="button"' : "") + ">" + body + "</div>";
    });
  });
  host.innerHTML = '<div class="scroll-x">' + html + "</div></div>";
  if (editable && onCell) $$(".cell.edit", host).forEach((el) => {
    const fire = () => onCell(+el.dataset.day, +el.dataset.p, tt.cells[el.dataset.day + "-" + el.dataset.p]);
    el.onclick = fire; el.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fire(); } };
  });
}

async function doLogout() { await api("/api/logout", { method: "POST" }); location.href = "/"; }

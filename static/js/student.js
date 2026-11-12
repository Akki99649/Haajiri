/* Student portal */
(function () {
  const ME = window.ME;
  let overview = null;
  const fmtDate = (d) => new Date(String(d).slice(0, 10) + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
  const tone = (p) => (p === null ? "" : p >= 75 ? "ok" : p >= 65 ? "mid" : "low");
  const barColor = { ok: "var(--mint)", mid: "var(--amber)", low: "var(--rose)" };

  function show(name) {
    $$("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.v === name));
    $$(".view").forEach((v) => v.classList.toggle("on", v.id === "v-" + name));
    history.replaceState(null, "", "#" + name);
    ({ home, timetable, face })[name]().catch((e) => toast(e.message, "bad"));
  }
  $$("#nav button").forEach((b) => b.onclick = () => show(b.dataset.v));

  async function load() { overview = await api("/api/student/overview"); return overview; }

  async function home() {
    const o = await load(), host = $("#v-home");
    const upcoming = o.today.find((p) => !p.is_break && p.subject && p.end > o.now);
    const current = upcoming && upcoming.start <= o.now;
    let html = "";
    html += '<div class="next-card"><span class="muted">' + (current ? "Happening now" : upcoming ? "Next up" : esc(o.day)) + "</span>" +
      (upcoming ? '<div class="big">' + esc(upcoming.subject) + '</div><div class="muted">' + esc(upcoming.start) + " - " + esc(upcoming.end) + (upcoming.room ? " &middot; " + esc(upcoming.room) : "") + (upcoming.teacher ? " &middot; " + esc(upcoming.teacher) : "") + "</div>"
        : '<div class="big">' + (o.today.length ? "No more classes today" : "No classes today") + '</div><div class="muted">Hello ' + esc(ME.name.split(" ")[0]) + ". Your timetable is under the Timetable tab.</div>") + "</div>";
    if (o.face_samples < 8) {
      html += '<div class="card row between wrap" style="margin-top:16px;border-color:#CFCBFF;background:var(--blue-soft)"><div><h3>Set up your face</h3><p class="muted">The class camera cannot mark you present until it has learned your face. It takes about 10 seconds.</p></div><button class="btn primary" id="h-face">Set up now</button></div>';
    }
    html += '<h2 style="margin:28px 0 14px">Your attendance</h2><div class="grid-2">' + (o.subjects.map((s) => {
      const t = tone(s.percent);
      return '<div class="card subj-card"><div class="row between"><div><h3>' + esc(s.name) + '</h3><p class="muted small">' + esc(s.teacher) + '</p></div><div class="pct ' + t + '">' + (s.percent === null ? "-" : Math.round(s.percent) + "%") + '</div></div><div class="meter" aria-hidden="true"><i style="width:' + (s.percent || 0) + "%;background:" + (barColor[t] || "var(--line)") + '"></i></div><p class="small muted">' + (s.total ? "Attended " + s.attended + " of " + s.total + " classes" : "No classes recorded yet") + "</p>" +
        (s.need_more ? '<p class="small" style="color:var(--rose);font-weight:600">Attend the next ' + (s.need_more === 1 ? "class" : s.need_more + " classes in a row") + " to reach 75%.</p>" : "") + "</div>";
    }).join("") || '<div class="card empty">Your subjects appear here once teachers add them for section ' + esc(ME.section) + ".</div>") + "</div>";

    html += '<div class="grid-2" style="margin-top:28px;align-items:start"><div class="card"><h3 style="margin-bottom:6px">Today, ' + esc(o.day) + '</h3><div class="timeline">' +
      (o.today.map((p) => {
        const now = o.now >= p.start && o.now < p.end;
        return '<div class="tl ' + (p.is_break ? "brk " : "") + (now ? "now" : "") + '"><div class="t">' + esc(p.start) + "<small>" + esc(p.end) + "</small></div><div>" + (p.is_break ? esc(p.label) : p.subject ? "<b>" + esc(p.subject) + '</b><div class="small muted">' + esc(p.teacher || "") + (p.room ? " &middot; " + esc(p.room) : "") + "</div>" : '<span class="muted">Free period</span>') + "</div></div>";
      }).join("") || '<div class="empty">No classes today.</div>') + '</div></div><div class="card"><h3 style="margin-bottom:6px">Recent classes</h3><div class="timeline">' +
      (o.recent.map((r) => '<div class="tl"><div class="t">' + esc(fmtDate(r.date)) + "<small>" + esc(r.period_label || (r.period_no ? "Period " + r.period_no : "")) + '</small></div><div class="row between"><b>' + esc(r.subject) + '</b><span class="chip ' + r.status + '">' + esc(r.status) + "</span></div></div>").join("") || '<div class="empty">Your attendance for each class shows up here.</div>') + "</div></div></div>";
    host.innerHTML = html;
    const hf = $("#h-face"); if (hf) hf.onclick = () => show("face");
  }

  async function timetable() {
    const tt = await api("/api/timetable");
    $("#v-timetable").innerHTML = '<h2 style="margin-bottom:6px">Section ' + esc(tt.section) + ' timetable</h2><p class="muted" style="margin-bottom:16px">You get a reminder a few minutes before each period. If a teacher changes a time, you are told.</p><div class="card flush" id="tt-grid"></div>';
    renderTimetable($("#tt-grid"), tt, {});
  }

  async function face() {
    const o = await load();
    const n = o.face_samples, ok = n >= 8;
    $("#v-face").innerHTML = '<div class="card stack" style="max-width:620px"><h2>Face setup</h2><p class="muted">Haajiri learns your face from a few photos taken with this device. Photos stay on your college server and are used only to mark attendance.</p>' +
      '<div class="row wrap"><span class="chip ' + (ok ? "present" : n ? "late" : "absent") + '">' + (ok ? "Ready" : n ? "Add a few more photos" : "Not set up") + "</span><span class=\"small muted\">" + n + " photos saved</span></div>" +
      '<div class="bar"><i style="width:' + Math.min(100, Math.round(n / 14 * 100)) + '%"></i></div>' +
      '<div class="row wrap"><button class="btn primary" id="f-go">' + (n ? "Add more photos" : "Set up my face") + '</button>' + (n ? '<button class="btn danger" id="f-clear">Remove my photos</button>' : "") + "</div>" +
      '<p class="hint">Tip: take photos in the same kind of light as your classroom, with and without glasses if you wear them.</p></div>';
    $("#f-go").onclick = () => openFaceCapture(ME.id, "", face);
    const c = $("#f-clear");
    if (c) c.onclick = async () => { await api("/api/students/" + ME.id + "/faces", { method: "DELETE" }); toast("Photos removed"); face(); };
  }

  mountBell($("#bell"));
  const start = location.hash.slice(1);
  show(["home", "timetable", "face"].includes(start) ? start : "home");
})();

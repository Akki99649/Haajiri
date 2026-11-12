/* Teacher dashboard */
(function () {
  const ME = window.ME;
  const NAV = [
    ["today", "Today", ICON.today, "Your classes for today"],
    ["live", "Take attendance", ICON.cam, "Roll call with the camera"],
    ["timetable", "Timetable", ICON.grid, "Suggested for each section. Tap any period to edit it."],
    ["students", "Students", ICON.people, "Face setup for every student"],
    ["reports", "Reports", ICON.sheet, "Excel sheets for every class"],
    ["subjects", "Subjects", ICON.book, "The subjects you teach"],
    ["settings", "Settings", ICON.gear, "Camera, reminders and recognition"],
  ];
  const S = { view: "today", sessionId: null, timers: [], stream: null, subjects: [], ttSection: null, stuSection: "" };
  let refreshBell;

  function download(url) { const a = document.createElement("a"); a.href = url; a.download = ""; document.body.appendChild(a); a.click(); a.remove(); }
  function clearTimers() { S.timers.forEach(clearInterval); S.timers = []; if (S.stream) { stopCamera(S.stream); S.stream = null; } }
  const fmtDate = (d) => new Date(d + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

  async function loadSubjects() { S.subjects = (await api("/api/subjects")).subjects; return S.subjects; }
  async function allSections() {
    const set = new Set((await api("/api/sections")).sections);
    S.subjects.forEach((s) => set.add(s.section));
    return Array.from(set).sort();
  }

  /* ------------------------------------------------------------ nav */
  function buildNav() {
    $("#nav").innerHTML = NAV.map((n) => '<button class="nav-btn" data-v="' + n[0] + '">' + n[2] + "<span>" + n[1] + "</span></button>").join("");
    $$(".nav-btn").forEach((b) => b.onclick = () => show(b.dataset.v));
  }
  function show(name) {
    clearTimers();
    S.view = name;
    const n = NAV.find((x) => x[0] === name);
    $("#page-title").textContent = n[1]; $("#page-sub").textContent = n[3];
    $$(".nav-btn").forEach((b) => b.classList.toggle("on", b.dataset.v === name));
    $$(".view").forEach((v) => v.classList.toggle("on", v.id === "v-" + name));
    history.replaceState(null, "", "#" + name);
    VIEWS[name]().catch((e) => toast(e.message, "bad"));
  }

  /* ---------------------------------------------------------- today */
  async function viewToday() {
    const host = $("#v-today");
    host.innerHTML = '<div class="empty">Loading...</div>';
    await loadSubjects();
    const d = await api("/api/today");
    $("#page-sub").textContent = d.day + ", " + new Date(d.date + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "long" });
    let html = "";
    if (d.active.length) {
      html += '<div class="card row between wrap" style="margin-bottom:16px;background:var(--blue-soft);border-color:#CFCBFF"><div><h3>A class is being recorded</h3><p class="muted">' + esc(d.active[0].subject) + " &middot; Section " + esc(d.active[0].section) + '</p></div><button class="btn primary" data-resume="' + d.active[0].id + '">Open roll call</button></div>';
    }
    if (!S.subjects.length) {
      html += '<div class="card empty"><h3>Add your first subject</h3><p style="margin:6px 0 14px">Add the subject you teach and its section, and Haajiri suggests a timetable for you.</p><button class="btn primary" data-go="subjects">Add a subject</button></div>';
    } else if (!d.classes.length) {
      html += '<div class="card empty"><h3>No classes in the timetable today</h3><p style="margin:6px 0 14px">You can still start a class by hand, or assign periods in the timetable.</p><div class="row wrap" style="justify-content:center"><button class="btn primary" data-go="live">Take attendance now</button><button class="btn" data-go="timetable">Open timetable</button></div></div>';
    } else {
      html += '<div class="class-list">' + d.classes.map((c) => {
        const btn = c.session_status === "active" ? '<button class="btn primary" data-resume="' + c.session_id + '">Resume</button>'
          : c.session_status === "ended" ? '<button class="btn" data-sheet="' + c.session_id + '">Download Excel</button>'
          : '<button class="btn primary" data-start="' + c.subject_id + '" data-p="' + c.period_no + '">Take attendance</button>';
        return '<div class="card class-card"><div class="time-block">' + esc(c.start_time) + "<small>to " + esc(c.end_time) + "</small></div><div><h3>" + esc(c.subject) + '</h3><p class="muted">Section ' + esc(c.section) + " &middot; " + esc(c.label || "Period " + c.period_no) + (c.room ? " &middot; " + esc(c.room) : "") + "</p></div>" + btn + "</div>";
      }).join("") + "</div>";
    }
    host.innerHTML = html;
    $$("[data-go]", host).forEach((b) => b.onclick = () => show(b.dataset.go));
    $$("[data-resume]", host).forEach((b) => b.onclick = () => { S.sessionId = +b.dataset.resume; show("live"); });
    $$("[data-sheet]", host).forEach((b) => b.onclick = () => download("/api/sessions/" + b.dataset.sheet + "/export"));
    $$("[data-start]", host).forEach((b) => b.onclick = () => beginSession({ subject_id: +b.dataset.start, period_no: +b.dataset.p, mode: "browser" }));
  }
  async function beginSession(payload) {
    try { const r = await api("/api/sessions/start", { method: "POST", body: payload }); S.sessionId = r.id; show("live"); }
    catch (e) { toast(e.message, "bad"); }
  }

  /* ----------------------------------------------------------- live */
  async function viewLive() {
    const host = $("#v-live");
    if (!S.sessionId) {
      const t = await api("/api/today");
      if (t.active.length) S.sessionId = t.active[0].id;
    }
    if (S.sessionId) return liveRoom(host);
    return livePicker(host);
  }

  async function livePicker(host) {
    await loadSubjects();
    if (!S.subjects.length) { host.innerHTML = '<div class="card empty"><h3>Add a subject first</h3><p style="margin:6px 0 14px">Attendance is taken per subject and section.</p><button class="btn primary" id="go-sub">Add a subject</button></div>'; $("#go-sub").onclick = () => show("subjects"); return; }
    const settings = await api("/api/settings");
    host.innerHTML =
      '<div class="card stack" style="max-width:640px"><h2>Start a class</h2>' +
      '<label class="field"><span>Subject</span><select class="input" id="p-sub">' + S.subjects.map((s) => '<option value="' + s.id + '" data-sec="' + esc(s.section) + '">' + esc(s.name) + " (" + esc(s.code) + ") - Section " + esc(s.section) + "</option>").join("") + "</select></label>" +
      '<label class="field"><span>Period</span><select class="input" id="p-per"></select></label>' +
      '<div class="field"><span>Camera</span><div class="seg" id="p-mode"><button class="on" data-m="browser">This device</button><button data-m="camera">Classroom camera</button></div></div>' +
      '<div id="p-cam" class="hide stack"><label class="field"><span>Camera address</span><input class="input" id="p-src" value="' + esc(settings.camera_source) + '" placeholder="rtsp://user:password@192.168.1.64:554/stream1"><em class="hint">Use 0 for a USB webcam on the server, or an RTSP / HTTP address for a CCTV or IP camera.</em></label><div class="row"><button class="btn sm" id="p-test">Test camera</button><span class="small muted" id="p-test-out"></span></div></div>' +
      '<div class="error-text" id="p-err"></div><button class="btn primary" id="p-go">Start attendance</button></div>';
    let mode = "browser";
    const fillPeriods = async () => {
      const sec = $("#p-sub").selectedOptions[0].dataset.sec;
      const tt = await api("/api/timetable?section=" + encodeURIComponent(sec));
      const day = (new Date().getDay() + 6) % 7, now = new Date().toTimeString().slice(0, 5);
      const subId = $("#p-sub").value;
      let pick = "";
      const opts = tt.slots.filter((s) => !s.is_break).map((s) => {
        const c = tt.cells[day + "-" + s.period_no];
        const here = c && String(c.subject_id) === String(subId);
        if (here && !pick && now < s.end_time) pick = s.period_no;
        return '<option value="' + s.period_no + '">' + esc(s.label) + " (" + s.start_time + "-" + s.end_time + ")" + (here ? " - your class" : "") + "</option>";
      });
      $("#p-per").innerHTML = opts.join("") + '<option value="">Outside the timetable</option>';
      if (pick) $("#p-per").value = pick;
    };
    $("#p-sub").onchange = fillPeriods; fillPeriods();
    $$("#p-mode button").forEach((b) => b.onclick = () => { mode = b.dataset.m; $$("#p-mode button").forEach((x) => x.classList.toggle("on", x === b)); $("#p-cam").classList.toggle("hide", mode !== "camera"); });
    $("#p-test").onclick = async () => {
      const out = $("#p-test-out"); out.textContent = "Testing...";
      try { const r = await api("/api/camera/test", { method: "POST", body: { source: $("#p-src").value } }); out.textContent = r.message; out.style.color = r.ok ? "var(--mint)" : "var(--rose)"; }
      catch (e) { out.textContent = e.message; out.style.color = "var(--rose)"; }
    };
    $("#p-go").onclick = async () => {
      $("#p-err").textContent = "";
      try {
        const r = await api("/api/sessions/start", { method: "POST", body: { subject_id: +$("#p-sub").value, period_no: $("#p-per").value ? +$("#p-per").value : null, mode, camera_source: $("#p-src") ? $("#p-src").value : "" } });
        S.sessionId = r.id; show("live");
      } catch (e) { $("#p-err").textContent = e.message; }
    };
  }

  async function liveRoom(host) {
    const id = S.sessionId;
    let d = await api("/api/sessions/" + id);
    if (d.session.status !== "active") { S.sessionId = null; return livePicker(host); }
    const browser = d.session.camera_source === "browser";
    const prev = {};
    host.innerHTML =
      '<div class="row between wrap" style="margin-bottom:16px"><div><h2>' + esc(d.session.subject_name) + '</h2><p class="muted">Section ' + esc(d.session.section) + " &middot; " + fmtDate(d.session.date) + (d.session.period_no ? " &middot; " + esc(d.session.period_label || "Period " + d.session.period_no) : "") + '</p></div><button class="btn dark" id="l-end">End class and get Excel</button></div>' +
      '<div class="live"><div class="stack"><div class="stage"><span class="badge"><i class="pulse" id="l-dot"></i><span id="l-state">Starting camera...</span></span>' +
      (browser ? '<video id="l-video" class="mirror" playsinline muted></video><canvas id="l-canvas"></canvas>' : '<img id="l-img" alt="Classroom camera" src="/api/sessions/' + id + '/stream">') +
      '</div><p class="hint">' + (browser ? "Point this device at the class. Students are marked present after the camera sees them a few times." : "Reading the classroom camera on the server. Students are marked present after the camera sees them a few times.") + '</p><div class="error-text" id="l-err"></div></div>' +
      '<div class="stack"><div class="tally" id="l-tally"></div><div class="board" id="l-board"></div><p class="hint">Tap a student to change their status by hand. Your change always wins over the camera.</p></div></div>';

    function paint(data) {
      const c = data.counts;
      $("#l-tally").innerHTML = '<div class="p"><b>' + c.present + "</b><span>Present</span></div><div class=\"l\"><b>" + c.late + "</b><span>Late</span></div><div class=\"a\"><b>" + c.absent + "</b><span>Absent</span></div><div><b>" + c.total + "</b><span>In class list</span></div>";
      if (!data.roster) return;
      $("#l-board").innerHTML = data.roster.map((r) => {
        const just = prev[r.id] && prev[r.id] === "absent" && r.status === "present";
        prev[r.id] = r.status;
        return '<div class="tile ' + r.status + (just ? " just" : "") + '" tabindex="0" role="button" data-id="' + r.id + '" aria-label="' + esc(r.name) + ", " + r.status + '"><span class="stamp">' + (r.status === "present" ? "P" : r.status === "late" ? "L" : "") + '</span><div class="ini">' + esc(initials(r.name)) + '</div><div class="nm">' + esc(r.name) + '</div><div class="rn">' + esc(r.roll_no) + "</div></div>";
      }).join("") || '<div class="empty">No students in this section yet.</div>';
      $$(".tile", $("#l-board")).forEach((t) => { t.onclick = (e) => tileMenu(t, +t.dataset.id, id, e); });
    }
    d.roster.forEach((r) => prev[r.id] = r.status);
    S.paint = paint;
    paint(d);

    const camState = (cam) => {
      $("#l-state").textContent = cam.state === "live" ? "Camera live" : cam.state === "error" ? "Camera problem" : "Connecting...";
      $("#l-dot").classList.toggle("err", cam.state === "error");
      $("#l-err").textContent = cam.message || "";
    };
    camState(d.camera);
    if (d.engine.error) $("#l-err").textContent = d.engine.error;
    S.timers.push(setInterval(async () => {
      try { const x = await api("/api/sessions/" + id); paint(x); if (!browser) camState(x.camera); } catch (e) { /* keep trying */ }
    }, 2000));

    if (browser) {
      const video = $("#l-video"), canvas = $("#l-canvas");
      try { S.stream = await openCamera(video); camState({ state: "live" }); }
      catch (e) { $("#l-err").textContent = e.message; camState({ state: "error" }); }
      let busy = false;
      S.timers.push(setInterval(async () => {
        if (busy || !S.stream) return;
        const frame = grabFrame(video, 640, 0.75);
        if (!frame) return;
        busy = true;
        try { const r = await api("/api/sessions/" + id + "/frame", { method: "POST", body: { image: frame } }); drawFaces(canvas, video, r); }
        catch (e) { $("#l-err").textContent = e.message; }
        busy = false;
      }, 700));
    }
    $("#l-end").onclick = () => endClass(id);
  }

  function drawFaces(canvas, video, r) {
    const rect = video.getBoundingClientRect();
    canvas.width = rect.width; canvas.height = rect.height;
    const ctx = canvas.getContext("2d"); ctx.clearRect(0, 0, canvas.width, canvas.height);
    const vw = video.videoWidth, vh = video.videoHeight, k = Math.min(rect.width / vw, rect.height / vh);
    const ox = (rect.width - vw * k) / 2, oy = (rect.height - vh * k) / 2, sx = r.width ? vw / r.width : 1;
    r.faces.forEach((f) => {
      let [x, y, w, h] = f.box;
      x = x * sx * k; y = y * sx * k; w = w * sx * k; h = h * sx * k;
      x = canvas.width - (x + ox) - w;       // the preview is mirrored
      y += oy;
      ctx.lineWidth = 3; ctx.strokeStyle = f.known ? "#3DDC97" : "#FF6B81"; ctx.strokeRect(x, y, w, h);
      const label = f.known ? f.name + "  " + Math.round(f.confidence) + "%" : "Not recognised";
      ctx.font = "600 14px Figtree, sans-serif";
      const tw = ctx.measureText(label).width + 14;
      ctx.fillStyle = f.known ? "#0F9D78" : "#D93B52"; ctx.fillRect(x, Math.max(0, y - 24), tw, 24);
      ctx.fillStyle = "#fff"; ctx.fillText(label, x + 7, Math.max(16, y - 7));
    });
  }

  function tileMenu(tile, studentId, sessionId, ev) {
    $$(".menu").forEach((m) => m.remove());
    const m = document.createElement("div"); m.className = "menu";
    m.innerHTML = '<button data-s="present">Mark present</button><button data-s="late">Mark late</button><button data-s="absent">Mark absent</button>';
    tile.appendChild(m);
    m.style.left = "50%"; m.style.top = "100%"; m.style.transform = "translateX(-50%)";
    m.onclick = async (e) => {
      e.stopPropagation();
      const b = e.target.closest("button"); if (!b) return;
      m.remove();
      try { await api("/api/sessions/" + sessionId + "/mark", { method: "POST", body: { student_id: studentId, status: b.dataset.s } }); const x = await api("/api/sessions/" + sessionId); if (S.paint) S.paint(x); } catch (er) { toast(er.message, "bad"); }
    };
    setTimeout(() => document.addEventListener("click", function off() { m.remove(); }, { once: true }), 0);
  }

  async function endClass(id) {
    const m = openModal('<h2>End this class?</h2><p class="muted">Anyone still absent is recorded as absent, students are notified, and your Excel sheet is created.</p><div class="row"><button class="btn grow" data-x>Keep recording</button><button class="btn dark grow" data-ok>End class</button></div>');
    $("[data-x]", m).onclick = closeModal;
    $("[data-ok]", m).onclick = async () => {
      try {
        const r = await api("/api/sessions/" + id + "/end", { method: "POST" });
        closeModal(); clearTimers(); S.sessionId = null;
        $("#v-live").innerHTML = '<div class="card stack" style="max-width:560px"><h2>Class saved</h2><div class="tally"><div class="p"><b>' + r.counts.present + '</b><span>Present</span></div><div class="l"><b>' + r.counts.late + '</b><span>Late</span></div><div class="a"><b>' + r.counts.absent + '</b><span>Absent</span></div></div><p class="muted">Your Excel sheet is ready. It is also kept under Reports.</p><div class="row wrap"><button class="btn primary" id="dl">Download Excel</button><button class="btn" id="back">Back to today</button></div></div>';
        $("#dl").onclick = () => download(r.export_url); $("#back").onclick = () => show("today");
        download(r.export_url);
      } catch (e) { toast(e.message, "bad"); }
    };
  }

  /* ------------------------------------------------------ timetable */
  async function viewTimetable() {
    const host = $("#v-timetable");
    await loadSubjects();
    const secs = await allSections();
    if (!secs.length) { host.innerHTML = '<div class="card empty"><h3>No sections yet</h3><p style="margin:6px 0 14px">Add a subject to create a section.</p><button class="btn primary" id="g">Add a subject</button></div>'; $("#g").onclick = () => show("subjects"); return; }
    if (!S.ttSection || !secs.includes(S.ttSection)) S.ttSection = (S.subjects[0] && S.subjects[0].section) || secs[0];
    host.innerHTML = '<div class="row between wrap" style="margin-bottom:16px"><div class="row wrap"><label class="field"><span>Section</span><select class="input" id="t-sec" style="width:130px">' + secs.map((s) => "<option" + (s === S.ttSection ? " selected" : "") + ">" + esc(s) + "</option>").join("") + '</select></label></div><div class="row wrap"><button class="btn" id="t-suggest">Suggest timetable</button><button class="btn" id="t-times">Edit period times</button><button class="btn danger" id="t-reset">Reset times</button></div></div><div class="card flush" id="t-grid"></div><p class="hint" style="margin-top:10px">Students in this section see this timetable, and everyone gets a reminder a few minutes before each period.</p>';
    $("#t-sec").onchange = (e) => { S.ttSection = e.target.value; paintTT(); };
    $("#t-suggest").onclick = async () => {
      const r = await api("/api/timetable/suggest", { method: "POST", body: { section: S.ttSection } });
      toast(r.filled ? r.filled + " empty periods filled. Tap any period to change it." : "Nothing to fill. Add subjects for this section first.", r.filled ? "good" : "");
      paintTT();
    };
    $("#t-reset").onclick = async () => { await api("/api/timetable/suggest", { method: "POST", body: { section: S.ttSection, reset_times: true } }); toast("Period times reset to the standard day", "good"); paintTT(); };
    $("#t-times").onclick = () => editTimes();
    paintTT();
  }
  async function paintTT() {
    const tt = await api("/api/timetable?section=" + encodeURIComponent(S.ttSection));
    renderTimetable($("#t-grid"), tt, { editable: true, onCell: (day, p, cell) => editCell(tt, day, p, cell) });
  }
  async function editCell(tt, day, p, cell) {
    const subs = (await api("/api/subjects?section=" + encodeURIComponent(S.ttSection))).subjects;
    const slot = tt.slots.find((s) => s.period_no === p);
    const m = openModal('<h2>' + esc(tt.days[day]) + ", " + esc(slot.label) + '</h2><p class="muted">' + esc(slot.start_time) + " - " + esc(slot.end_time) + '</p><label class="field"><span>Subject</span><select class="input" id="c-sub"><option value="">Free period</option>' + subs.map((s) => '<option value="' + s.id + '"' + (cell && cell.subject_id === s.id ? " selected" : "") + ">" + esc(s.name) + " - " + esc(s.teacher_name) + "</option>").join("") + '</select></label><label class="field"><span>Room</span><input class="input" id="c-room" value="' + esc(cell && cell.room || "") + '" placeholder="Room 204"></label><div class="row"><button class="btn grow" data-x>Cancel</button><button class="btn primary grow" data-ok>Save</button></div>');
    $("[data-x]", m).onclick = closeModal;
    $("[data-ok]", m).onclick = async () => {
      try { await api("/api/timetable/cell", { method: "PUT", body: { section: S.ttSection, day, period_no: p, subject_id: +$("#c-sub").value || null, room: $("#c-room").value } }); closeModal(); paintTT(); } catch (e) { toast(e.message, "bad"); }
    };
  }
  async function editTimes() {
    const tt = await api("/api/timetable?section=" + encodeURIComponent(S.ttSection));
    let rows = tt.slots.map((s) => ({ ...s }));
    const m = openModal('<h2>Period times for section ' + esc(S.ttSection) + '</h2><p class="muted">Set when each period starts and ends. Tick Break for tea or lunch, which are shown in the timetable but are not classes.</p><div id="e-rows" class="stack" style="gap:8px"></div><button class="btn sm" id="e-add">Add a row</button><div class="error-text" id="e-err"></div><div class="row"><button class="btn grow" data-x>Cancel</button><button class="btn primary grow" data-ok>Save times</button></div>', { wide: true });
    const paint = () => {
      $("#e-rows", m).innerHTML = rows.map((r, i) => '<div class="row slot-row"><input class="input" data-k="label" data-i="' + i + '" value="' + esc(r.label) + '" aria-label="Name"><input class="input" type="time" data-k="start_time" data-i="' + i + '" value="' + r.start_time + '" aria-label="Start"><input class="input" type="time" data-k="end_time" data-i="' + i + '" value="' + r.end_time + '" aria-label="End"><label class="row small" style="white-space:nowrap"><input type="checkbox" data-k="is_break" data-i="' + i + '"' + (r.is_break ? " checked" : "") + '> Break</label><button class="btn sm danger" data-del="' + i + '" aria-label="Remove row">&times;</button></div>').join("");
      $$("[data-k]", m).forEach((el) => el.onchange = () => { rows[+el.dataset.i][el.dataset.k] = el.type === "checkbox" ? (el.checked ? 1 : 0) : el.value; });
      $$("[data-del]", m).forEach((b) => b.onclick = () => { rows.splice(+b.dataset.del, 1); paint(); });
    };
    paint();
    $("#e-add", m).onclick = () => { const last = rows[rows.length - 1]; rows.push({ period_no: rows.length + 1, label: "Period " + (rows.length + 1), start_time: last ? last.end_time : "09:00", end_time: "", is_break: 0 }); paint(); };
    $("[data-x]", m).onclick = closeModal;
    $("[data-ok]", m).onclick = async () => {
      rows.forEach((r, i) => r.period_no = i + 1);
      try { await api("/api/timetable/slots", { method: "PUT", body: { section: S.ttSection, slots: rows } }); closeModal(); toast("Period times saved. Students were told.", "good"); paintTT(); }
      catch (e) { $("#e-err", m).textContent = e.message; }
    };
  }

  /* ------------------------------------------------------- students */
  async function viewStudents() {
    const host = $("#v-students");
    await loadSubjects();
    const secs = await allSections();
    const d = await api("/api/students" + (S.stuSection ? "?section=" + encodeURIComponent(S.stuSection) : ""));
    const eng = (await api("/api/engine")).engine;
    host.innerHTML = '<div class="row between wrap" style="margin-bottom:16px"><label class="field"><span>Section</span><select class="input" id="s-sec" style="width:150px"><option value="">All sections</option>' + secs.map((s) => "<option" + (s === S.stuSection ? " selected" : "") + ">" + esc(s) + "</option>").join("") + '</select></label><div class="row wrap"><span class="chip grey">' + esc(eng.backend_label) + " &middot; " + eng.trained_students + ' faces learned</span><button class="btn" id="s-train">Retrain</button></div></div>' +
      (eng.error ? '<div class="card" style="margin-bottom:14px;border-color:var(--rose)"><b>Face detector needs attention</b><p class="muted">' + esc(eng.error) + "</p></div>" : "") +
      '<div class="card flush"><div class="scroll-x"><table class="tbl"><thead><tr><th>Roll no</th><th>Name</th><th>Section</th><th>Face photos</th><th></th></tr></thead><tbody>' +
      (d.students.map((s) => "<tr><td>" + esc(s.roll_no) + "</td><td>" + esc(s.name) + "</td><td>" + esc(s.section) + '</td><td><span class="chip ' + (s.samples >= 8 ? "present" : s.samples ? "late" : "absent") + '">' + (s.samples ? s.samples + " photos" : "Not set up") + '</span></td><td style="text-align:right"><button class="btn sm" data-add="' + s.id + '" data-n="' + esc(s.name) + '">Add photos</button> <button class="btn sm danger" data-clear="' + s.id + '"' + (s.samples ? "" : " disabled") + ">Clear</button></td></tr>").join("") || '<tr><td colspan="5" class="empty">No students have registered yet. Students create their own accounts, then set up their face.</td></tr>') + "</tbody></table></div></div>";
    $("#s-sec").onchange = (e) => { S.stuSection = e.target.value; viewStudents(); };
    $("#s-train").onclick = async () => { await api("/api/train", { method: "POST" }); toast("Recognition retrained", "good"); viewStudents(); };
    $$("[data-add]", host).forEach((b) => b.onclick = () => openFaceCapture(+b.dataset.add, b.dataset.n, viewStudents));
    $$("[data-clear]", host).forEach((b) => b.onclick = async () => { await api("/api/students/" + b.dataset.clear + "/faces", { method: "DELETE" }); toast("Photos removed"); viewStudents(); });
  }

  /* -------------------------------------------------------- reports */
  async function viewReports() {
    const host = $("#v-reports");
    await loadSubjects();
    const d = await api("/api/sessions");
    host.innerHTML = '<div class="grid-2" style="margin-bottom:18px">' + (S.subjects.map((s) => '<div class="card row between"><div><h3>' + esc(s.name) + '</h3><p class="muted">Section ' + esc(s.section) + ' &middot; whole semester</p></div><button class="btn sm" data-rep="' + s.id + '">Download Excel</button></div>').join("") || "") + "</div>" +
      '<div class="card flush"><div class="scroll-x"><table class="tbl"><thead><tr><th>Date</th><th>Subject</th><th>Section</th><th>Period</th><th>Present</th><th>Status</th><th></th></tr></thead><tbody>' +
      (d.sessions.map((s) => "<tr><td>" + fmtDate(s.date) + "</td><td>" + esc(s.subject) + "</td><td>" + esc(s.section) + "</td><td>" + esc(s.period_label || s.period_no || "-") + "</td><td><b>" + s.present + "</b> / " + s.total + '</td><td><span class="chip ' + (s.status === "active" ? "late" : "present") + '">' + (s.status === "active" ? "Recording" : "Saved") + '</span></td><td style="text-align:right">' + (s.status === "active" ? '<button class="btn sm primary" data-open="' + s.id + '">Open</button>' : '<button class="btn sm" data-sheet="' + s.id + '">Excel</button>') + "</td></tr>").join("") || '<tr><td colspan="7" class="empty">No classes recorded yet. Finish a class and its Excel sheet appears here.</td></tr>') + "</tbody></table></div></div>";
    $$("[data-rep]", host).forEach((b) => b.onclick = () => download("/api/subjects/" + b.dataset.rep + "/report"));
    $$("[data-sheet]", host).forEach((b) => b.onclick = () => download("/api/sessions/" + b.dataset.sheet + "/export"));
    $$("[data-open]", host).forEach((b) => b.onclick = () => { S.sessionId = +b.dataset.open; show("live"); });
  }

  /* ------------------------------------------------------- subjects */
  async function viewSubjects() {
    const host = $("#v-subjects");
    await loadSubjects();
    host.innerHTML = '<div class="grid-2"><form class="card stack" id="sub-form"><h3>Add a subject</h3><label class="field"><span>Subject name</span><input class="input" name="name" placeholder="Operating Systems" required></label><div class="row"><label class="field grow"><span>Subject code</span><input class="input" name="code" placeholder="CS501" required></label><label class="field" style="width:110px"><span>Section</span><input class="input" name="section" placeholder="5A" required></label></div><div class="error-text" id="sub-err"></div><button class="btn primary" type="submit">Add subject</button></form>' +
      '<div class="stack">' + (S.subjects.map((s) => '<div class="card row between"><div><h3>' + esc(s.name) + '</h3><p class="muted">' + esc(s.code) + " &middot; Section " + esc(s.section) + '</p></div><button class="btn sm danger" data-del="' + s.id + '">Delete</button></div>').join("") || '<div class="card empty">Subjects you add appear here.</div>') + "</div></div>";
    $("#sub-form").onsubmit = async (e) => {
      e.preventDefault(); const f = e.target.elements;
      try { await api("/api/subjects", { method: "POST", body: { name: f.name.value, code: f.code.value, section: f.section.value } }); toast("Subject added. Open the timetable to suggest periods.", "good"); viewSubjects(); }
      catch (er) { $("#sub-err").textContent = er.message; }
    };
    $$("[data-del]", host).forEach((b) => b.onclick = async () => { try { await api("/api/subjects/" + b.dataset.del, { method: "DELETE" }); viewSubjects(); } catch (e) { toast(e.message, "bad"); } });
  }

  /* ------------------------------------------------------- settings */
  async function viewSettings() {
    const host = $("#v-settings");
    const s = await api("/api/settings");
    host.innerHTML = '<div class="grid-2"><div class="card stack"><h3>Reminders</h3><label class="field"><span>Remind teachers and students before each period (minutes)</span><input class="input" type="number" min="1" max="60" id="st-rem" value="' + s.reminder_minutes + '"></label><button class="btn primary" id="st-save-rem">Save reminder time</button></div>' +
      '<div class="card stack"><h3>Classroom camera</h3><label class="field"><span>Default camera address</span><input class="input" id="st-cam" value="' + esc(s.camera_source) + '" placeholder="rtsp://user:password@192.168.1.64:554/stream1"><em class="hint">Examples: 0 (USB webcam), rtsp://... (CCTV), http://192.168.1.5:8080/video (phone camera app).</em></label><div class="row wrap"><button class="btn" id="st-test">Test camera</button><button class="btn primary" id="st-save-cam">Save camera</button></div><span class="small muted" id="st-out"></span></div>' +
      '<div class="card stack"><h3>Recognition engine</h3><p><span class="chip">' + esc(s.engine.backend_label) + '</span></p><p class="muted">' + (s.engine.backend === "sface" ? "Using the deep-learning engine. This is the most accurate option." : "Using the built-in engine. For higher accuracy run <b>python download_models.py</b> once, then restart the app.") + "</p>" + (s.engine.error ? '<p style="color:var(--rose)">' + esc(s.engine.error) + "</p>" : "") + "</div></div>";
    $("#st-save-rem").onclick = async () => { try { await api("/api/settings", { method: "PUT", body: { reminder_minutes: $("#st-rem").value } }); toast("Reminder time saved", "good"); } catch (e) { toast(e.message, "bad"); } };
    $("#st-save-cam").onclick = async () => { await api("/api/settings", { method: "PUT", body: { camera_source: $("#st-cam").value } }); toast("Camera saved", "good"); };
    $("#st-test").onclick = async () => { const o = $("#st-out"); o.textContent = "Testing..."; try { const r = await api("/api/camera/test", { method: "POST", body: { source: $("#st-cam").value } }); o.textContent = r.message; o.style.color = r.ok ? "var(--mint)" : "var(--rose)"; } catch (e) { o.textContent = e.message; o.style.color = "var(--rose)"; } };
  }

  const VIEWS = { today: viewToday, live: viewLive, timetable: viewTimetable, students: viewStudents, reports: viewReports, subjects: viewSubjects, settings: viewSettings };
  buildNav();
  refreshBell = mountBell($("#bell"));
  const start = location.hash.slice(1);
  show(VIEWS[start] ? start : "today");
})();

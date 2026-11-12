(function () {
  const loginForm = $("#login-form"), regForm = $("#register-form");
  let role = "student";

  $$("[data-tab]").forEach((b) => b.onclick = () => {
    $$("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
    loginForm.classList.toggle("hide", b.dataset.tab !== "login");
    regForm.classList.toggle("hide", b.dataset.tab !== "register");
  });
  $$("[data-role]").forEach((b) => b.onclick = () => {
    role = b.dataset.role;
    $$("[data-role]").forEach((x) => x.classList.toggle("on", x === b));
    $$("[data-for]", regForm).forEach((el) => el.classList.toggle("hide", el.dataset.for !== role));
  });

  async function submit(form, url, payload) {
    const out = $("[data-err]", form), btn = $("button[type=submit]", form);
    out.textContent = ""; btn.disabled = true;
    try {
      const r = await api(url, { method: "POST", body: payload });
      location.href = r.user.role === "teacher" ? "/teacher" : "/student";
    } catch (e) { out.textContent = e.message; btn.disabled = false; }
  }
  const val = (form, n) => (form.elements[n] ? form.elements[n].value : "");

  loginForm.onsubmit = (e) => { e.preventDefault(); submit(loginForm, "/api/login", { email: val(loginForm, "email"), password: val(loginForm, "password") }); };
  regForm.onsubmit = (e) => {
    e.preventDefault();
    submit(regForm, "/api/register", {
      role, name: val(regForm, "name"), email: val(regForm, "email"), password: val(regForm, "password"),
      roll_no: val(regForm, "roll_no"), section: val(regForm, "section"), code: val(regForm, "code"),
    });
  };
})();

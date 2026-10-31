import { api, session, DEMO } from "./api.js";
import { t } from "./i18n.js";
import { setupChrome, busy, errorText } from "./ui.js";

setupChrome();

// Pages that need a specific account send people here with ?next=ops
const next = new URLSearchParams(location.search).get("next") === "ops" ? "ops.html" : "app.html";
if (session.token) location.replace(next);
if (DEMO) document.getElementById("api-link").remove();

const form = document.getElementById("auth-form");
const error = form.querySelector(".form-error");
const submit = form.querySelector("[type=submit]");
let mode = "in";

for (const tab of document.querySelectorAll("[role=tab]")) {
  tab.addEventListener("click", () => {
    mode = tab.dataset.mode;
    for (const other of document.querySelectorAll("[role=tab]")) {
      other.setAttribute("aria-selected", String(other === tab));
    }
    form.setAttribute("aria-labelledby", tab.id);
    submit.dataset.i18n = mode === "in" ? "auth.submitIn" : "auth.submitUp";
    submit.textContent = t(submit.dataset.i18n);
    form.password.autocomplete = mode === "in" ? "current-password" : "new-password";
    error.textContent = "";
  });
}

function fillDemo(email) {
  form.email.value = email;
  form.password.value = "demo-password";
}

for (const button of document.querySelectorAll("[data-as]")) {
  button.addEventListener("click", () => {
    fillDemo(button.dataset.as);
    submit.focus();
  });
}

if (next === "ops.html") {
  fillDemo("ops@monetka.demo");
  document.getElementById("ops-hint").hidden = false;
} else if (DEMO) {
  fillDemo("olena@monetka.demo");
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  error.textContent = "";
  const credentials = { email: form.email.value.trim(), password: form.password.value };
  busy(form, async () => {
    try {
      if (mode === "up") await api("/auth/register", { method: "POST", body: credentials, auth: false });
      const { access_token } = await api("/auth/login", { method: "POST", body: credentials, auth: false });
      session.save(access_token);
      location.href = next;
    } catch (failure) {
      error.textContent = errorText(failure);
    }
  });
});

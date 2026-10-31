import { lang, t, toggleLang, applyTranslations } from "./i18n.js";
import { session } from "./api.js";

export function money(minor, { sign = false } = {}) {
  const value = Math.abs(minor) / 100;
  const text = value.toLocaleString(lang === "uk" ? "uk-UA" : "en-GB", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const prefix = sign ? (minor > 0 ? "+" : minor < 0 ? "−" : "") : minor < 0 ? "−" : "";
  return `${prefix}${text} ₴`;
}

/** "86.10" or "86,10" from a form field into kopiyky, without float rounding. */
export function parseAmount(text) {
  const match = String(text).trim().replace(",", ".").match(/^(\d{1,7})(?:\.(\d{1,2}))?$/);
  if (!match) return null;
  return Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
}

export function shortDate(iso) {
  return new Date(iso).toLocaleDateString(lang === "uk" ? "uk-UA" : "en-GB", {
    day: "2-digit",
    month: "short",
  });
}

export function dateTime(iso) {
  return new Date(iso).toLocaleString(lang === "uk" ? "uk-UA" : "en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function errorText(error) {
  const key = `error.${error.code}`;
  const text = t(key);
  return text === key ? error.message || t("error.unknown") : text;
}

export function toast(message, kind = "") {
  let box = document.querySelector(".toasts");
  if (!box) {
    box = document.createElement("div");
    box.className = "toasts";
    box.setAttribute("role", "status");
    box.setAttribute("aria-live", "polite");
    document.body.append(box);
  }
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  item.textContent = message;
  box.append(item);
  setTimeout(() => item.remove(), 4500);
}

function applyTheme(theme) {
  if (theme) document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

export function setupChrome() {
  try {
    applyTheme(localStorage.getItem("monetka.theme"));
  } catch {
    // stays on the system theme
  }
  applyTranslations();
  document.querySelector("[data-action=lang]")?.addEventListener("click", toggleLang);
  document.querySelector("[data-action=theme]")?.addEventListener("click", () => {
    const dark =
      document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    const next = dark ? "light" : "dark";
    applyTheme(next);
    try {
      localStorage.setItem("monetka.theme", next);
    } catch {
      // not remembered, still applied
    }
  });
  document.querySelector("[data-action=signout]")?.addEventListener("click", () => {
    session.clear();
    location.href = "index.html";
  });
}

/** Disable the submit button while a request runs, so a double click sends one request. */
export async function busy(form, work) {
  const button = form.querySelector("[type=submit]");
  button.disabled = true;
  try {
    return await work();
  } finally {
    button.disabled = false;
  }
}

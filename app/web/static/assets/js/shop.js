import { api, DEMO } from "./api.js";
import { t } from "./i18n.js";
import { setupChrome, money, parseAmount, dateTime, escapeHtml, errorText, toast, busy } from "./ui.js";

setupChrome();

const form = document.getElementById("request");
const list = document.getElementById("payments");
const error = form.querySelector(".form-error");
const KEY = "monetka.shop-key";

form.key.value = sessionStorage.getItem(KEY) ?? (DEMO ? "mk_demo" : "");

const merchant = (path, options = {}) =>
  api(`/merchant/payments${path}`, { ...options, auth: false, headers: { "X-API-Key": form.key.value.trim() } });

async function refresh() {
  if (!form.key.value.trim()) return;
  const payments = await merchant("");
  list.innerHTML = payments.length
    ? payments
        .map((p) => {
          const actions =
            p.status === "authorized"
              ? `<button class="btn good small" data-capture="${p.id}">${t("shop.capture")}</button>
                 <button class="btn small" data-void="${p.id}">${t("shop.void")}</button>`
              : p.status === "pending"
                ? `<button class="btn small" data-void="${p.id}">${t("shop.void")}</button>`
                : "";
          return `<li>
            <time>${dateTime(p.created_at)}</time>
            <div class="what"><strong>${escapeHtml(p.description)}</strong>
              <span>${t(`status.${p.status}`)}</span>
              <div class="row" style="display:flex;gap:8px;margin-top:6px">${actions}</div></div>
            <div class="amount">${money(p.amount)}</div>
          </li>`;
        })
        .join("")
    : `<li class="empty">${t("shop.none")}</li>`;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  error.textContent = "";
  sessionStorage.setItem(KEY, form.key.value.trim());
  busy(form, async () => {
    try {
      const amount = parseAmount(form.amount.value);
      if (!amount) throw new Error(t("error.validation_error"));
      await merchant("", {
        method: "POST",
        idempotent: true,
        body: { customer_email: form.customer.value.trim(), amount, description: form.description.value.trim() },
      });
      await refresh();
    } catch (failure) {
      error.textContent = failure.code ? errorText(failure) : failure.message;
    }
  });
});

list.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const id = button.dataset.capture ?? button.dataset.void;
  button.disabled = true;
  try {
    await merchant(`/${id}/${button.dataset.capture ? "capture" : "void"}`, { method: "POST" });
    await refresh();
  } catch (failure) {
    toast(errorText(failure), "bad");
  }
});

window.addEventListener("langchange", () => refresh().catch(() => {}));
refresh().catch((failure) => (error.textContent = errorText(failure)));
setInterval(() => refresh().catch(() => {}), 3000);

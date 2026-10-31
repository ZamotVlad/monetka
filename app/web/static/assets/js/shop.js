import { api, DEMO } from "./api.js";
import { t } from "./i18n.js";
import { setupChrome, money, dateTime, escapeHtml, errorText, toast, busy } from "./ui.js";

setupChrome();

const form = document.getElementById("request");
const list = document.getElementById("payments");
const error = form.querySelector(".form-error");
const KEY = "monetka.shop-key";

const MENU = [
  { id: "latte", price: 8600 },
  { id: "cappuccino", price: 7800 },
  { id: "croissant", price: 6500 },
  { id: "cheesecake", price: 9500 },
  { id: "beans", price: 32000 },
  { id: "mug", price: 35000 },
];
const cart = { latte: 1, croissant: 1 };

function cartTotal() {
  return MENU.reduce((sum, item) => sum + item.price * (cart[item.id] ?? 0), 0);
}

function cartDescription() {
  return MENU.filter((item) => cart[item.id])
    .map((item) => (cart[item.id] > 1 ? `${t(`item.${item.id}`)} ×${cart[item.id]}` : t(`item.${item.id}`)))
    .join(", ")
    .slice(0, 140);
}

function renderMenu() {
  document.getElementById("menu").innerHTML = MENU.map(
    (item) => `<li>
      <span>${t(`item.${item.id}`)}</span>
      <span class="price">${money(item.price)}</span>
      <span class="stepper">
        <button class="btn small" type="button" data-minus="${item.id}" aria-label="− ${t(`item.${item.id}`)}">−</button>
        <output aria-live="polite">${cart[item.id] ?? 0}</output>
        <button class="btn small" type="button" data-plus="${item.id}" aria-label="+ ${t(`item.${item.id}`)}">+</button>
      </span>
    </li>`,
  ).join("");
  document.getElementById("cart-total").textContent = money(cartTotal());
}

document.getElementById("menu").addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const id = button.dataset.plus ?? button.dataset.minus;
  cart[id] = Math.max(0, Math.min(9, (cart[id] ?? 0) + (button.dataset.plus ? 1 : -1)));
  renderMenu();
  document.querySelector(`[data-${button.dataset.plus ? "plus" : "minus"}="${id}"]`).focus();
});

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
      const amount = cartTotal();
      if (!amount) throw new Error(t("shop.empty"));
      await merchant("", {
        method: "POST",
        idempotent: true,
        body: { customer_email: form.customer.value.trim(), amount, description: cartDescription() },
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

window.addEventListener("langchange", () => {
  renderMenu();
  refresh().catch(() => {});
});
renderMenu();
refresh().catch((failure) => (error.textContent = errorText(failure)));
setInterval(() => refresh().catch(() => {}), 3000);

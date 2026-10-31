import { api, session, ApiError } from "./api.js";
import { t } from "./i18n.js";
import { connectLive } from "./live.js";
import {
  setupChrome, money, parseAmount, shortDate, dateTime, escapeHtml, errorText, toast, busy,
} from "./ui.js";

if (!session.token) location.replace("index.html");
setupChrome();

const $ = (id) => document.getElementById(id);
const state = { me: null, history: [], nextBefore: null, pending: [], reserved: [], statements: [] };

/**
 * The books store signed postings; people want sentences. Each operation kind becomes one
 * line in plain words, and the amount shows what happened to the money they can spend.
 */
function describe(item) {
  const d = item.details;
  switch (item.kind) {
    case "deposit":
      return {
        title: d.source === "test" ? t("kind.testMoney") : t("kind.deposit", { card: d.card }),
        amount: item.wallet_delta,
      };
    case "withdrawal":
      return { title: t("kind.withdrawal", { card: d.card }), amount: item.wallet_delta };
    case "transfer": {
      const outgoing = item.wallet_delta < 0;
      return {
        title: outgoing ? t("kind.transferOut", { to: d.to }) : t("kind.transferIn", { from: d.from }),
        note: d.note,
        amount: item.wallet_delta,
      };
    }
    case "hold":
      return { title: t("kind.hold", { merchant: d.merchant }), note: d.description, amount: item.wallet_delta, tag: t("tag.reserved"), held: true };
    case "capture":
      return { title: t("kind.capture", { merchant: d.merchant }), note: d.description, amount: item.held_delta, tag: t("tag.paid") };
    case "release":
      return { title: t("kind.release", { merchant: d.merchant }), note: d.description, amount: item.wallet_delta };
    default:
      return { title: item.kind, amount: item.wallet_delta + item.held_delta };
  }
}

function renderBalance(balance) {
  $("available").textContent = money(balance.available);
  $("held").textContent = money(balance.held);
  $("total").textContent = money(balance.total);
}

function renderHistory() {
  const list = $("history");
  if (!state.history.length) {
    list.innerHTML = `<li class="empty">${t("wallet.noHistory")}</li>`;
  } else {
    list.innerHTML = state.history
      .map((item) => {
        const line = describe(item);
        const direction = line.held ? "held" : line.amount > 0 ? "in" : "out";
        return `<li>
          <time datetime="${item.created_at}">${shortDate(item.created_at)}</time>
          <div class="what"><strong>${escapeHtml(line.title)}</strong>${line.note ? `<span>${escapeHtml(line.note)}</span>` : ""}</div>
          <div class="amount ${direction}">${money(line.amount, { sign: true })}${line.tag ? `<small>${line.tag}</small>` : ""}</div>
        </li>`;
      })
      .join("");
  }
  $("more").hidden = state.nextBefore === null;
}

function renderRequests() {
  const box = $("requests");
  if (!state.pending.length) {
    box.innerHTML = `<p class="empty">${t("wallet.noRequests")}</p>`;
    return;
  }
  box.innerHTML = state.pending
    .map(
      (p) => `<article class="request" aria-label="${escapeHtml(p.merchant_name)}">
        <div class="head"><span class="shop">${escapeHtml(p.merchant_name)}</span><span class="sum">${money(p.amount)}</span></div>
        <p><strong>${escapeHtml(p.description)}</strong></p>
        <p>${t("request.explain")}</p>
        <p class="muted">${t("request.until", { date: dateTime(p.expires_at) })}</p>
        <div class="row">
          <button class="btn good small" type="button" data-confirm="${p.id}">${t("request.confirm")}</button>
          <button class="btn small" type="button" data-decline="${p.id}">${t("request.decline")}</button>
        </div>
      </article>`,
    )
    .join("");
}

function renderReserved() {
  const box = $("reserved");
  if (!state.reserved.length) {
    box.innerHTML = `<p class="empty">${t("wallet.noReserved")}</p>`;
    return;
  }
  box.innerHTML = state.reserved
    .map(
      (p) => `<div class="reserve">
        <div class="top"><strong>${escapeHtml(p.merchant_name)}</strong><span class="amount held">${money(p.amount)}</span></div>
        <span class="muted">${escapeHtml(p.description)}</span>
        <span class="muted">${t("reserve.returns", { date: shortDate(p.expires_at) })}</span>
      </div>`,
    )
    .join("");
}

function renderStatements() {
  const list = $("statements");
  list.innerHTML = state.statements.length
    ? state.statements
        .map(
          (s) => `<li><span>${s.period} · ${t("wallet.ops", { n: s.rows })}</span>
          <a href="${escapeHtml(s.download_url)}" download="monetka-${s.period}.csv">${t("wallet.download")}</a></li>`,
        )
        .join("")
    : `<li class="empty">${t("wallet.noStatements")}</li>`;
}

async function loadHistory(reset = true) {
  const before = reset ? "" : `&before=${state.nextBefore}`;
  const page = await api(`/wallet/history?limit=20${before}`);
  state.history = reset ? page.items : [...state.history, ...page.items];
  state.nextBefore = page.next_before;
  renderHistory();
}

async function refresh() {
  const [balance, pending, reserved, statements] = await Promise.all([
    api("/wallet"),
    api("/payments?status=pending"),
    api("/payments?status=authorized"),
    api("/statements"),
  ]);
  renderBalance(balance);
  state.pending = pending;
  state.reserved = reserved;
  state.statements = statements;
  renderRequests();
  renderReserved();
  renderStatements();
  await loadHistory();
}

let refreshQueued = false;
function scheduleRefresh() {
  // A burst of events (one transfer touches two accounts) becomes one reload
  if (refreshQueued) return;
  refreshQueued = true;
  setTimeout(() => {
    refreshQueued = false;
    refresh().catch(() => {});
  }, 150);
}

function setupDialog(id, submit) {
  const dialog = $(id);
  const form = dialog.querySelector("form");
  const error = form.querySelector(".form-error");
  dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    error.textContent = "";
    busy(form, async () => {
      try {
        await submit(form);
        dialog.close();
        form.reset();
      } catch (failure) {
        error.textContent = failure instanceof ApiError ? errorText(failure) : failure.message;
      }
    });
  });
}

function amountOf(form) {
  const amount = parseAmount(form.amount.value);
  if (!amount) throw new Error(t("error.validation_error"));
  return amount;
}

setupDialog("topup", async (form) => {
  const deposit = await api("/deposits", { method: "POST", body: { amount: amountOf(form) }, idempotent: true });
  location.href = deposit.checkout_url;
});

setupDialog("send", async (form) => {
  const amount = amountOf(form);
  await api("/transfers", {
    method: "POST",
    body: { to_email: form.to.value.trim(), amount, note: form.note.value.trim() || null },
    idempotent: true,
  });
  toast(t("toast.sent", { amount: money(amount) }), "good");
  scheduleRefresh();
});

setupDialog("withdraw", async (form) => {
  const amount = amountOf(form);
  await api("/withdrawals", { method: "POST", body: { amount, card_last4: form.card.value }, idempotent: true });
  toast(t("toast.withdrawn", { amount: money(amount) }), "good");
  scheduleRefresh();
});

for (const button of document.querySelectorAll("[data-open]")) {
  button.addEventListener("click", () => $(button.dataset.open).showModal());
}

$("requests").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const id = button.dataset.confirm ?? button.dataset.decline;
  const action = button.dataset.confirm ? "confirm" : "decline";
  button.disabled = true;
  try {
    const payment = await api(`/payments/${id}/${action}`, { method: "POST" });
    toast(
      action === "confirm"
        ? t("request.confirmed", { amount: money(payment.amount), shop: payment.merchant_name })
        : t("request.declined"),
      action === "confirm" ? "good" : "",
    );
    scheduleRefresh();
  } catch (failure) {
    toast(errorText(failure), "bad");
    button.disabled = false;
  }
});

$("more").addEventListener("click", () => loadHistory(false));

$("test-money").addEventListener("click", async (event) => {
  event.target.disabled = true;
  try {
    await api("/test-money", { method: "POST", idempotent: true });
    toast(t("toast.testMoney"), "good");
    scheduleRefresh();
  } catch (failure) {
    toast(errorText(failure), "bad");
  } finally {
    event.target.disabled = false;
  }
});

$("make-statement").addEventListener("click", async (event) => {
  event.target.disabled = true;
  try {
    const period = new Date().toISOString().slice(0, 7);
    await api("/statements", { method: "POST", body: { period } });
    toast(t("toast.statement"), "good");
    scheduleRefresh();
  } catch (failure) {
    toast(errorText(failure), "bad");
  } finally {
    event.target.disabled = false;
  }
});

/** Back from the provider's page: the webhook may land a second later, so we wait for it. */
async function followDeposit(id) {
  history.replaceState(null, "", "app.html");
  const banner = $("banner");
  banner.innerHTML = `<div class="banner warn">${t("deposit.waiting")}</div>`;
  for (let i = 0; i < 30; i++) {
    const deposit = await api(`/deposits/${id}`);
    if (deposit.status !== "pending") {
      const ok = deposit.status === "succeeded";
      banner.innerHTML = `<div class="banner ${ok ? "" : "warn"}">${
        ok ? t("deposit.succeeded", { amount: money(deposit.amount) }) : t("deposit.failed")
      }</div>`;
      scheduleRefresh();
      setTimeout(() => (banner.innerHTML = ""), 8000);
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

async function start() {
  const [me, config] = await Promise.all([api("/auth/me"), api("/config", { auth: false })]);
  state.me = me;
  $("test-money").hidden = !config.test_money;
  $("who").textContent = state.me.email;
  $("ops-link").hidden = !state.me.is_operator;
  await refresh();
  const deposit = new URLSearchParams(location.search).get("deposit");
  if (deposit) followDeposit(deposit);
  connectLive(scheduleRefresh, (on) => {
    const live = $("live");
    live.dataset.state = on ? "on" : "off";
    live.dataset.i18n = on ? "live.on" : "live.off";
    live.textContent = t(live.dataset.i18n);
  });
}

window.addEventListener("langchange", () => {
  renderHistory();
  renderRequests();
  renderReserved();
  renderStatements();
  refresh().catch(() => {});
});

start().catch((failure) => toast(errorText(failure), "bad"));

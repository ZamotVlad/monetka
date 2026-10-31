import { api, session } from "./api.js";
import { t } from "./i18n.js";
import { setupChrome, money, dateTime, escapeHtml, errorText, toast } from "./ui.js";

if (!session.token) location.replace("index.html?next=ops");
setupChrome();

const $ = (id) => document.getElementById(id);

const KIND_LABELS = { wallet: "wallet", hold: "hold", merchant: "merchant", system: "provider" };

function tile(label, value, kind = "") {
  return `<div class="tile ${kind}"><div class="label">${label}</div><div class="value">${value}</div></div>`;
}

function renderOverview(o) {
  const b = o.balances;
  $("tiles").innerHTML = [
    tile(t("ops.users"), o.users),
    tile(t("ops.wallets"), money(b.wallet ?? 0)),
    tile(t("ops.held"), money(b.hold ?? 0)),
    tile(t("ops.merchants"), money(b.merchant ?? 0)),
    tile(t("ops.provider"), money(b.system ?? 0)),
    tile(t("ops.books"), money(o.books_total), o.books_total === 0 ? "ok" : "bad"),
    tile(t("ops.backlog"), o.outbox_backlog),
    tile(t("ops.online"), o.online),
  ].join("");
  const run = o.last_run;
  $("reconciliation").innerHTML = run
    ? tile(run.ok ? t("ops.balanced") : t("ops.unbalanced"), run.ok ? "✓" : "✗", run.ok ? "ok" : "bad") +
      tile(t("ops.reconciliation"), t("ops.checked", { n: run.accounts_checked, date: dateTime(run.created_at) }))
    : tile(t("ops.reconciliation"), t("ops.never"));
}

/** The technical view people never see in the wallet: each posting as debit or credit. */
function renderJournal(entries) {
  $("journal").innerHTML = entries
    .map((entry) => {
      const head = `<tr class="txn"><td colspan="4">#${entry.id} · ${escapeHtml(entry.kind)} · ${dateTime(entry.created_at)}</td></tr>`;
      const lines = entry.lines
        .map(
          (line) => `<tr>
            <td>${KIND_LABELS[line.account_kind] ?? line.account_kind}:${line.account_id.slice(0, 8)}</td>
            <td>${escapeHtml(line.owner)}</td>
            <td class="num">${line.amount < 0 ? money(-line.amount) : ""}</td>
            <td class="num">${line.amount > 0 ? money(line.amount) : ""}</td>
          </tr>`,
        )
        .join("");
      const sum = entry.lines.reduce((total, line) => total + line.amount, 0);
      const check = `<tr class="sum"><td colspan="4">${sum === 0 ? t("ops.balancedRow") : `Σ = ${sum}`}</td></tr>`;
      return head + lines + check;
    })
    .join("");
}

async function refresh() {
  const [overview, journal] = await Promise.all([api("/ops/overview"), api("/ops/journal?limit=30")]);
  renderOverview(overview);
  renderJournal(journal);
}

$("switch").addEventListener("click", () => {
  session.clear();
  location.href = "index.html?next=ops";
});

$("run").addEventListener("click", async (event) => {
  event.target.disabled = true;
  try {
    await api("/ops/reconciliation", { method: "POST" });
    await refresh();
  } catch (failure) {
    toast(errorText(failure), "bad");
  } finally {
    event.target.disabled = false;
  }
});

window.addEventListener("langchange", () => refresh().catch(() => {}));

refresh()
  .then(() => setInterval(() => refresh().catch(() => {}), 5000))
  .catch((failure) => {
    if (failure.status === 403) {
      $("denied").hidden = false;
      $("switch").hidden = false;
      for (const section of document.querySelectorAll("main > section")) section.hidden = true;
    }
    else toast(errorText(failure), "bad");
  });

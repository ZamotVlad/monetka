// A pretend backend for the GitHub Pages demo, where no server runs. It keeps the same
// rules as the real one in miniature: postings sum to zero, wallets never go negative,
// a payment moves through the same states. State lives in sessionStorage.

const STORE = "monetka.demo-state";
const DAY = 86_400_000;

function iso(offset = 0) {
  return new Date(Date.now() + offset).toISOString();
}

function uid() {
  return crypto.randomUUID();
}

function seed() {
  const s = { users: {}, accounts: { psp: 0 }, txns: [], payments: [], deposits: {}, statements: [], runs: [], seq: 1 };
  for (const email of ["olena@monetka.demo", "taras@monetka.demo", "ops@monetka.demo"]) {
    s.users[email] = { id: uid(), email, password: "demo-password", is_operator: email.startsWith("ops") };
    s.accounts[`wallet:${email}`] = 0;
    s.accounts[`hold:${email}`] = 0;
  }
  s.accounts["merchant:Кав'ярня «Зерно»"] = 0;
  post(s, "deposit", [["psp", -250000], ["wallet:olena@monetka.demo", 250000]], { card: "4242" }, -3 * DAY);
  post(s, "deposit", [["psp", -50000], ["wallet:taras@monetka.demo", 50000]], { card: "1881" }, -2 * DAY);
  post(s, "transfer", [["wallet:taras@monetka.demo", -15000], ["wallet:olena@monetka.demo", 15000]],
    { from: "taras@monetka.demo", to: "olena@monetka.demo", note: "За квитки" }, -DAY);
  s.payments.push({
    id: uid(), merchant_name: "Кав'ярня «Зерно»", customer: "olena@monetka.demo", amount: 8600,
    description: "Лате і круасан", status: "pending", expires_at: iso(DAY), created_at: iso(-3600_000),
  });
  return s;
}

function load() {
  try {
    const saved = sessionStorage.getItem(STORE);
    if (saved) return JSON.parse(saved);
  } catch {
    // corrupted or blocked storage: start over
  }
  return seed();
}

let db = load();

function save() {
  try {
    sessionStorage.setItem(STORE, JSON.stringify(db));
  } catch {
    // the demo still works for this page
  }
}

class Refusal extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function post(s, kind, lines, details, offset = 0) {
  if (lines.reduce((sum, [, amount]) => sum + amount, 0) !== 0) throw new Error("unbalanced");
  for (const [account, amount] of lines) {
    const next = s.accounts[account] + amount;
    if (next < 0 && account !== "psp") throw new Refusal(422, "insufficient_funds", "Not enough money");
  }
  for (const [account, amount] of lines) s.accounts[account] += amount;
  const txn = { id: s.seq++, kind, details, created_at: iso(offset), lines };
  s.txns.push(txn);
  return txn;
}

function emit(type) {
  setTimeout(() => window.dispatchEvent(new CustomEvent("demo:event", { detail: { type } })), 50);
}

function owner(account) {
  return account === "psp" ? "card provider" : account.split(":").slice(1).join(":");
}

function paymentOut(p) {
  const { customer, ...rest } = p;
  return { ...rest, customer_id: db.users[customer]?.id };
}

function close(p, status) {
  if (p.status === "authorized") {
    post(db, "release", [[`hold:${p.customer}`, -p.amount], [`wallet:${p.customer}`, p.amount]],
      { merchant: p.merchant_name, description: p.description, payment_id: p.id });
  } else if (p.status !== "pending") {
    throw new Refusal(409, "invalid_transition", `Payment is ${p.status}`);
  }
  p.status = status;
}

function history(email, before, limit) {
  const mine = [`wallet:${email}`, `hold:${email}`];
  const rows = db.txns
    .filter((txn) => txn.lines.some(([account]) => mine.includes(account)))
    .filter((txn) => !before || txn.id < before)
    .sort((a, b) => b.id - a.id)
    .slice(0, limit)
    .map((txn) => ({
      id: txn.id, kind: txn.kind, details: txn.details, created_at: txn.created_at,
      wallet_delta: txn.lines.filter(([a]) => a === mine[0]).reduce((s, [, v]) => s + v, 0),
      held_delta: txn.lines.filter(([a]) => a === mine[1]).reduce((s, [, v]) => s + v, 0),
    }));
  return { items: rows, next_before: rows.length === limit ? rows.at(-1).id : null };
}

function route(method, path, body, headers) {
  const [pathname, query = ""] = path.split("?");
  const q = new URLSearchParams(query);
  const token = headers.Authorization?.replace("Bearer demo:", "");
  const me = token ? db.users[token] : null;
  const need = () => {
    if (!me) throw new Refusal(401, "invalid_credentials", "Sign in first");
    return me;
  };
  const parts = pathname.split("/").filter(Boolean);

  if (method === "POST" && pathname === "/auth/register") {
    if (db.users[body.email]) throw new Refusal(409, "email_taken", "Taken");
    if (body.password.length < 8) throw new Refusal(422, "validation_error", "Short password");
    db.users[body.email] = { id: uid(), email: body.email, password: body.password, is_operator: false };
    db.accounts[`wallet:${body.email}`] = 0;
    db.accounts[`hold:${body.email}`] = 0;
    return [201, { id: db.users[body.email].id, email: body.email, is_operator: false }];
  }
  if (method === "POST" && pathname === "/auth/login") {
    const user = db.users[body.email?.toLowerCase()];
    if (!user || user.password !== body.password) throw new Refusal(401, "invalid_credentials", "Wrong");
    return [200, { access_token: `demo:${user.email}`, token_type: "bearer" }];
  }
  if (pathname === "/auth/me") {
    const u = need();
    return [200, { id: u.id, email: u.email, is_operator: u.is_operator }];
  }
  if (pathname === "/wallet") {
    const u = need();
    const available = db.accounts[`wallet:${u.email}`];
    const held = db.accounts[`hold:${u.email}`];
    return [200, { available, held, total: available + held, currency: "UAH" }];
  }
  if (pathname === "/wallet/history") {
    return [200, history(need().email, Number(q.get("before")) || null, Number(q.get("limit")) || 20)];
  }
  if (method === "POST" && pathname === "/transfers") {
    const u = need();
    if (!db.users[body.to_email]) throw new Refusal(404, "not_found", "No such user");
    if (body.to_email === u.email) throw new Refusal(422, "self_transfer", "Self");
    const txn = post(db, "transfer", [[`wallet:${u.email}`, -body.amount], [`wallet:${body.to_email}`, body.amount]],
      { from: u.email, to: body.to_email, note: body.note });
    emit("wallet.changed");
    return [201, txn];
  }
  if (method === "POST" && pathname === "/withdrawals") {
    const u = need();
    const txn = post(db, "withdrawal", [[`wallet:${u.email}`, -body.amount], ["psp", body.amount]], { card: body.card_last4 });
    emit("wallet.changed");
    return [201, txn];
  }
  if (method === "POST" && pathname === "/deposits") {
    const u = need();
    const id = uid();
    db.deposits[id] = { id, amount: body.amount, status: "pending", created_at: iso(), email: u.email };
    return [201, { ...db.deposits[id], checkout_url: `app.html?deposit=${id}` }];
  }
  if (parts[0] === "deposits") {
    need();
    return [200, db.deposits[parts[1]]];
  }
  if (pathname === "/payments") {
    const u = need();
    return [200, db.payments.filter((p) => p.customer === u.email && (!q.get("status") || p.status === q.get("status"))).reverse().map(paymentOut)];
  }
  if (parts[0] === "payments") {
    const u = need();
    const p = db.payments.find((x) => x.id === parts[1] && x.customer === u.email);
    if (!p) throw new Refusal(404, "not_found", "Payment not found");
    if (p.status !== "pending") throw new Refusal(409, "invalid_transition", `Payment is ${p.status}`);
    if (parts[2] === "confirm") {
      post(db, "hold", [[`wallet:${u.email}`, -p.amount], [`hold:${u.email}`, p.amount]],
        { merchant: p.merchant_name, description: p.description, payment_id: p.id });
      p.status = "authorized";
      p.expires_at = iso(7 * DAY);
    } else {
      p.status = "declined";
    }
    emit("payment.updated");
    return [200, paymentOut(p)];
  }
  if (parts[0] === "merchant") {
    if (!headers["X-API-Key"]) throw new Refusal(401, "invalid_credentials", "Unknown API key");
    const merchant = "Кав'ярня «Зерно»";
    if (method === "GET" && parts.length === 2) {
      return [200, db.payments.filter((p) => p.merchant_name === merchant).reverse().map(paymentOut)];
    }
    if (method === "POST" && parts.length === 2) {
      if (!db.users[body.customer_email]) throw new Refusal(404, "not_found", "No such user");
      const p = {
        id: uid(), merchant_name: merchant, customer: body.customer_email, amount: body.amount,
        description: body.description, status: "pending", expires_at: iso(DAY), created_at: iso(),
      };
      db.payments.push(p);
      emit("payment.updated");
      return [201, paymentOut(p)];
    }
    const p = db.payments.find((x) => x.id === parts[2]);
    if (!p) throw new Refusal(404, "not_found", "Payment not found");
    if (method === "GET") return [200, paymentOut(p)];
    if (parts[3] === "capture") {
      if (p.status !== "authorized") throw new Refusal(409, "invalid_transition", `Payment is ${p.status}`);
      post(db, "capture", [[`hold:${p.customer}`, -p.amount], [`merchant:${merchant}`, p.amount]],
        { merchant, description: p.description, payment_id: p.id });
      p.status = "captured";
    } else {
      close(p, "voided");
    }
    emit("payment.updated");
    return [200, paymentOut(p)];
  }
  if (pathname === "/statements") {
    const u = need();
    if (method === "POST") {
      const rows = history(u.email, null, 1000).items.filter((r) => r.created_at.startsWith(body.period));
      const csv = ["date,operation,available_change,reserved_change",
        ...rows.reverse().map((r) => `${r.created_at},${r.kind},${r.wallet_delta / 100},${r.held_delta / 100}`)].join("\n");
      const statement = { period: body.period, rows: rows.length, created_at: iso(), email: u.email,
        download_url: `data:text/csv;charset=utf-8,${encodeURIComponent("﻿" + csv)}` };
      db.statements = db.statements.filter((s) => !(s.email === u.email && s.period === body.period));
      db.statements.push(statement);
      return [201, statement];
    }
    return [200, db.statements.filter((s) => s.email === u.email)];
  }
  if (parts[0] === "ops") {
    if (!need().is_operator) throw new Refusal(403, "forbidden", "Operators only");
    const totals = { wallet: 0, hold: 0, merchant: 0, system: db.accounts.psp };
    for (const [account, balance] of Object.entries(db.accounts)) {
      const kind = account.split(":")[0];
      if (kind in totals && account !== "psp") totals[kind] += balance;
    }
    const books = Object.values(db.accounts).reduce((sum, value) => sum + value, 0);
    if (parts[1] === "reconciliation" && method === "POST") {
      const run = { id: db.runs.length + 1, ok: books === 0, accounts_checked: Object.keys(db.accounts).length,
        books_total: books, problems: {}, created_at: iso() };
      db.runs.push(run);
      return [200, run];
    }
    if (parts[1] === "overview") {
      return [200, { users: Object.keys(db.users).length, balances: totals, books_total: books,
        outbox_backlog: 0, online: 1, last_run: db.runs.at(-1) ?? null }];
    }
    if (parts[1] === "journal") {
      return [200, [...db.txns].reverse().slice(0, 30).map((txn) => ({
        ...txn,
        lines: txn.lines.map(([account, amount]) => ({
          account_id: `${account.split(":")[0]}-demo-account`, account_kind: account === "psp" ? "system" : account.split(":")[0],
          owner: owner(account), amount,
        })),
      }))];
    }
  }
  throw new Refusal(404, "not_found", `No demo route for ${method} ${pathname}`);
}

// No bank here: the "provider" approves a top-up on its own a moment after it starts.
// Checked on every call, because the page navigates away right after creating it.
function settleDeposits() {
  for (const deposit of Object.values(db.deposits)) {
    if (deposit.status === "pending" && Date.now() - Date.parse(deposit.created_at) > 1000) {
      post(db, "deposit", [["psp", -deposit.amount], [`wallet:${deposit.email}`, deposit.amount]], { card: "4242" });
      deposit.status = "succeeded";
      emit("wallet.changed");
    }
  }
}

export async function demoFetch(path, { method = "GET", body, headers = {} }) {
  db = load();
  settleDeposits();
  await new Promise((resolve) => setTimeout(resolve, 120));
  try {
    const [status, data] = route(method, path, body ? JSON.parse(body) : undefined, headers);
    save();
    return { status, data: structuredClone(data) };
  } catch (error) {
    if (!(error instanceof Refusal)) throw error;
    return { status: error.status, data: { error: { code: error.code, message: error.message } } };
  }
}

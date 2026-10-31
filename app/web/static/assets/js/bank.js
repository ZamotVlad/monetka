// The demo's bank page. On the real stack the bank is psp_mock on port 8001; on GitHub
// Pages there is no server, so this page plays its part inside the browser.

import { api } from "./api.js";
import { completeDemoDeposit } from "./demo.js";
import { setupChrome, money } from "./ui.js";

setupChrome();

const id = new URLSearchParams(location.search).get("deposit");
const DECLINED_CARD = "4000000000000002";

api(`/deposits/${id}`).then((deposit) => {
  document.getElementById("amount").textContent = money(deposit.amount);
});

function finish(succeeded) {
  completeDemoDeposit(id, succeeded);
  location.href = `app.html?deposit=${id}`;
}

document.getElementById("bank").addEventListener("submit", (event) => {
  event.preventDefault();
  finish(document.getElementById("card").value.replace(/\s/g, "") !== DECLINED_CARD);
});
document.getElementById("cancel").addEventListener("click", () => finish(false));

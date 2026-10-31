// Live updates. The server pushes events from Kafka over a WebSocket; we only use them as a
// signal to reload, so a missed or duplicated event cannot show a wrong balance.

import { DEMO, session } from "./api.js";

export function connectLive(onEvent, onState) {
  if (DEMO) {
    window.addEventListener("demo:event", (event) => onEvent(event.detail));
    onState(true);
    return;
  }
  let delay = 1000;
  const open = () => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/api/v1/ws`);
    socket.addEventListener("open", () => socket.send(JSON.stringify({ token: session.token })));
    socket.addEventListener("message", (message) => {
      const event = JSON.parse(message.data);
      if (event.type === "ready") {
        delay = 1000;
        onState(true);
      } else {
        onEvent(event);
      }
    });
    socket.addEventListener("close", (closed) => {
      onState(false);
      if (closed.code === 4401) return;
      setTimeout(open, delay);
      delay = Math.min(delay * 2, 30000);
    });
  };
  open();
}

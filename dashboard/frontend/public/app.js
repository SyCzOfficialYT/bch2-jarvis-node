(() => {
  const $ = (s) => document.querySelector(s);

  function log(m) {
    const f = $("#log-feed");
    if (!f) return;
    const d = document.createElement("div");
    d.textContent = "[" + new Date().toLocaleTimeString("de-DE") + "] " + m;
    f.prepend(d);
  }

  function fmtH(h) {
    if (!h || h <= 0) return "\u2014";
    const u = ["H/s", "KH/s", "MH/s", "GH/s", "TH/s", "PH/s"];
    let i = 0, v = +h;
    while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
    return v.toFixed(2) + " " + u[i];
  }

  function update(d) {
    if (!d) return;
    const st = d.status || "?";
    const stEl = $("#status-text");
    if (stEl) stEl.textContent = String(st).toUpperCase();
    const pulse = document.querySelector(".pulse");
    if (pulse) pulse.className = "pulse " + (st === "online" ? "online" : "");

    const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
    set("#blocks", d.blocks != null ? d.blocks : "\u2014");
    set("#difficulty", d.difficulty ? Number(d.difficulty).toExponential(2) : "\u2014");
    set("#net-hash", fmtH(d.network_hashps));

    const m = (d.stratum && d.stratum.mining) || {};
    const r = (d.stratum && d.stratum.round) || {};
    const j = (d.stratum && d.stratum.job) || {};

    set("#my-hash", fmtH(m.hashrate_5m));
    set("#best-share", r.best_share ? Number(r.best_share).toFixed(1) : "\u2014");
    set("#shares-acc", m.shares_accepted != null ? m.shares_accepted : 0);

    const el = r.elapsed_sec || 0;
    const mm = String(Math.floor(el / 60)).padStart(2, "0");
    const ss = String(Math.floor(el % 60)).padStart(2, "0");
    set("#round-timer", mm + ":" + ss);

    const bar = $("#round-bar");
    if (bar) bar.style.width = Math.min(100, r.progress_pct || 0) + "%";

    const bal = d.balance || {};
    set("#bal-total", (bal.total != null ? bal.total : 0).toFixed(8));

    const holding = d.holding_address || (d.stratum && d.stratum.holding_address) || "generating\u2026";
    set("#holding-addr", holding);

    const parts = j.parts || [];
    const bp = $("#block-parts");
    if (bp) {
      bp.innerHTML = parts.length
        ? parts.map(function (p) {
            return '<div class="part' + (p.active ? " active" : "") + '">' + (p.label || "") + "</div>";
          }).join("")
        : "WAITING\u2026";
    }

    set("#last-update", d.last_update
      ? new Date(d.last_update * 1000).toLocaleTimeString("de-DE")
      : "\u2014");
  }

  async function tick() {
    try {
      const r = await fetch("/api/overview");
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();
      update(data);
    } catch (e) {
      log("API: " + e.message);
      const st = $("#status-text");
      if (st) st.textContent = "OFFLINE";
    }
  }

  function clock() {
    const c = $("#clock");
    if (c) c.textContent = new Date().toLocaleTimeString("de-DE", { hour12: false });
  }

  document.addEventListener("DOMContentLoaded", function () {
    log("JARVIS online");
    clock();
    setInterval(clock, 1000);
    tick();
    setInterval(tick, 4000);
    try {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(proto + "//" + location.host + "/ws");
      ws.onmessage = function (e) {
        try {
          const m = JSON.parse(e.data);
          if (m.payload) update(m.payload);
        } catch (_) {}
      };
      ws.onerror = function () { log("WS offline \u2013 polling only"); };
    } catch (_) {}
  });
})();

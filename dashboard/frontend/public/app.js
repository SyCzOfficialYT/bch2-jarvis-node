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

  function fmtShare(d) {
    if (d == null || d <= 0 || isNaN(d)) return "\u2014";
    const n = Number(d);
    const units = ["", "K", "M", "G", "T", "P"];
    let i = 0, v = n;
    while (v >= 1000 && i < units.length - 1) { v /= 1000; i++; }
    const digits = v >= 100 ? 0 : v >= 10 ? 1 : 2;
    return v.toFixed(digits) + (units[i] ? units[i] : "");
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
    const best = r.best_share || r.best_share_ever || 0;
    const bestEver = r.best_share_ever || best;
    set("#best-share", fmtShare(best));
    set("#best-share-ever", fmtShare(bestEver));
    set("#shares-acc", m.shares_accepted != null ? m.shares_accepted : 0);

    const el = r.elapsed_sec || 0;
    const mm = String(Math.floor(el / 60)).padStart(2, "0");
    const ss = String(Math.floor(el % 60)).padStart(2, "0");
    set("#round-timer", mm + ":" + ss);

    const bar = $("#round-bar");
    if (bar) bar.style.width = Math.min(100, r.progress_pct || 0) + "%";

    const netDiff = Number(j.network_diff || d.difficulty || 0);
    const nearEl = $("#near-block-pct");
    const nearBar = $("#near-block-bar");
    if (netDiff > 0 && best > 0) {
      const poolFloor = 1024;
      const logBest = Math.log10(Math.max(best, poolFloor));
      const logNet = Math.log10(Math.max(netDiff, poolFloor));
      const logFloor = Math.log10(poolFloor);
      let pct = ((logBest - logFloor) / (logNet - logFloor)) * 100;
      pct = Math.max(0, Math.min(100, pct));
      const linearPct = (best / netDiff) * 100;
      if (nearBar) nearBar.style.width = pct + "%";
      if (nearEl) {
        nearEl.textContent =
          fmtShare(best) + " / " + fmtShare(netDiff) +
          "  (" + (linearPct >= 0.01 ? linearPct.toFixed(2) : linearPct.toExponential(1)) + "% linear)";
      }
    } else {
      if (nearBar) nearBar.style.width = "0%";
      if (nearEl) nearEl.textContent = "noch kein Share diese Runde";
    }

    const bal = d.balance || {};
    set("#bal-total", (bal.total != null ? bal.total : 0).toFixed(8));

    const holding = d.holding_address || (d.stratum && d.stratum.holding_address) || "generating\u2026";
    set("#holding-addr", holding);

    const partsList = j.parts || [];
    const bp = $("#block-parts");
    if (bp) {
      bp.innerHTML = partsList.length
        ? partsList.map(function (p) {
            return '<div class="part' + (p.active ? " active" : "") + '">' + (p.label || "") + "</div>";
          }).join("")
        : "WAITING\u2026";
    }

    set("#last-update", d.last_update
      ? new Date(d.last_update * 1000).toLocaleTimeString("de-DE")
      : "\u2014");

    const slog = (d.stratum && d.stratum.log) || [];
    const f = $("#log-feed");
    if (f && slog.length) {
      const newest = slog[0];
      const key = newest && (newest.ts + ":" + newest.msg);
      if (key && key !== f.dataset.lastTs) {
        f.dataset.lastTs = key;
        const frag = document.createDocumentFragment();
        slog.slice(0, 50).reverse().forEach(function (e) {
          const div = document.createElement("div");
          const t = e.ts ? new Date(e.ts * 1000).toLocaleTimeString("de-DE") : "";
          div.textContent = "[" + t + "][" + (e.level || "info") + "] " + (e.msg || "");
          if (e.level === "ok") div.style.color = "#00ff9d";
          if (e.level === "warn") div.style.color = "#ffcc00";
          frag.appendChild(div);
        });
        f.innerHTML = "";
        f.appendChild(frag);
      }
    }
  }

  async function tick() {
    try {
      const r = await fetch("/api/overview");
      if (!r.ok) throw new Error("HTTP " + r.status);
      update(await r.json());
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
    setInterval(tick, 3000);
    try {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(proto + "//" + location.host + "/ws");
      ws.onmessage = function (e) {
        try {
          const m = JSON.parse(e.data);
          if (m.payload) update(m.payload);
        } catch (_) {}
      };
    } catch (_) {}
  });
})();

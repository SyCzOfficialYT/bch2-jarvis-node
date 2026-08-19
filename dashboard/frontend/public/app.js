(() => {
  const $ = (s) => document.querySelector(s);

  function fmtH(h) {
    if (!h || h <= 0 || Number.isNaN(Number(h))) return "—";
    const u = ["H/s", "KH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s"];
    let i = 0, v = Number(h);
    while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
    return v.toFixed(2) + " " + u[i];
  }

  function fmtShare(d) {
    if (d == null || d <= 0 || Number.isNaN(Number(d))) return "—";
    const units = ["", "K", "M", "G", "T", "P", "E"];
    let i = 0, v = Number(d);
    while (v >= 1000 && i < units.length - 1) { v /= 1000; i++; }
    const digits = v >= 100 ? 0 : v >= 10 ? 1 : 2;
    return v.toFixed(digits) + units[i];
  }

  function esc(value) {
    const d = document.createElement("div");
    d.textContent = value == null ? "" : String(value);
    return d.innerHTML;
  }

  function update(d) {
    if (!d) return;
    const st = d.status || "?";
    const stEl = $("#status-text");
    if (stEl) stEl.textContent = String(st).toUpperCase();
    const pulse = document.querySelector(".pulse");
    if (pulse) pulse.className = "pulse " + (st === "online" ? "online" : "");

    const set = (id, val) => { const el = $(id); if (el) el.textContent = val; };
    set("#blocks", d.blocks != null ? d.blocks : "—");
    set("#difficulty", d.difficulty ? Number(d.difficulty).toExponential(2) : "—");
    set("#net-hash", fmtH(d.network_hashps));

    const m = (d.stratum && d.stratum.mining) || {};
    const r = (d.stratum && d.stratum.round) || {};
    const j = (d.stratum && d.stratum.job) || {};

    set("#pool-diff", m.share_difficulty ? Number(m.share_difficulty).toLocaleString("de-DE") : "—");
    set("#my-hash", fmtH(m.hashrate_5m));
    set("#shares-accepted", m.shares_accepted ?? 0);
    set("#shares-rejected", m.shares_rejected ?? 0);
    const total = Number(m.shares_accepted || 0) + Number(m.shares_rejected || 0);
    set("#reject-rate", total ? ((Number(m.shares_rejected || 0) / total) * 100).toFixed(2) + "%" : "0%");

    const best = r.best_share || 0;
    const bestEver = r.best_share_ever || best;
    set("#best-share", fmtShare(best));
    set("#best-share-ever", fmtShare(bestEver));

    const el = Number(r.elapsed_sec || 0);
    const mm = String(Math.floor(el / 60)).padStart(2, "0");
    const ss = String(Math.floor(el % 60)).padStart(2, "0");
    set("#round-timer", mm + ":" + ss);
    const bar = $("#round-bar");
    if (bar) bar.style.width = Math.min(100, Number(r.progress_pct || 0)) + "%";

    const netDiff = Number(j.network_diff || d.difficulty || 0);
    const nearEl = $("#near-block-pct");
    const nearBar = $("#near-block-bar");
    if (netDiff > 0 && best > 0) {
      const poolFloor = 1024;
      const logBest = Math.log10(Math.max(best, poolFloor));
      const logNet = Math.log10(Math.max(netDiff, poolFloor));
      const logFloor = Math.log10(poolFloor);
      let pct = logNet > logFloor ? ((logBest - logFloor) / (logNet - logFloor)) * 100 : 0;
      pct = Math.max(0, Math.min(100, pct));
      const linearPct = (best / netDiff) * 100;
      if (nearBar) nearBar.style.width = pct + "%";
      if (nearEl) nearEl.textContent = fmtShare(best) + " / " + fmtShare(netDiff) + " (" + (linearPct >= 0.01 ? linearPct.toFixed(2) : linearPct.toExponential(1)) + "% linear)";
    } else {
      if (nearBar) nearBar.style.width = "0%";
      if (nearEl) nearEl.textContent = "noch kein Share diese Runde";
    }

    const bal = d.balance || {};
    set("#bal-total", (Number(bal.total || 0)).toFixed(8));
    set("#holding-addr", d.holding_address || "—");

    const workers = m.workers || {};
    const workersEl = $("#workers-list");
    if (workersEl) {
      const entries = Object.entries(workers);
      workersEl.innerHTML = entries.length ? entries.map(([name, w]) =>
        `<div><strong>${esc(name)}</strong> — shares ${Number(w.shares || 0)} — best ${esc(fmtShare(w.best_share))}</div>`
      ).join("") : "No workers connected.";
    }

    const blocks = d.stratum && Array.isArray(d.stratum.blocks_found) ? d.stratum.blocks_found : [];
    const blocksEl = $("#blocks-found");
    if (blocksEl) {
      blocksEl.innerHTML = blocks.length ? blocks.slice(0, 20).map(b =>
        `<div>height=${esc(b.height)} worker=${esc(b.worker)} diff=${esc(fmtShare(b.share_diff))} status=${esc(b.status)}</div>`
      ).join("") : "No blocks found.";
    }

    const slog = (d.stratum && d.stratum.log) || [];
    const f = $("#log-feed");
    if (f) {
      f.innerHTML = slog.slice(0, 80).map(e => {
        const t = e.ts ? new Date(e.ts * 1000).toLocaleTimeString("de-DE") : "";
        return `<div>[${esc(t)}][${esc(e.level || "info")}] ${esc(e.msg || "")}</div>`;
      }).join("");
    }

    set("#last-update", d.last_update ? new Date(d.last_update * 1000).toLocaleTimeString("de-DE") : "—");
  }

  async function tick() {
    try {
      const r = await fetch("/api/overview", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      update(await r.json());
    } catch (e) {
      const st = $("#status-text");
      if (st) st.textContent = "OFFLINE";
      const pulse = document.querySelector(".pulse");
      if (pulse) pulse.className = "pulse";
    }
  }

  function clock() {
    const c = $("#clock");
    if (c) c.textContent = new Date().toLocaleTimeString("de-DE", { hour12: false });
  }

  document.addEventListener("DOMContentLoaded", function () {
    clock();
    setInterval(clock, 1000);
    tick();
    setInterval(tick, 3000);
    try {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(proto + "//" + location.host + "/ws");
      ws.onmessage = function (e) {
        try {
          const msg = JSON.parse(e.data);
          if (msg.payload) update(msg.payload);
        } catch (_) {}
      };
      ws.onclose = () => setTimeout(() => location.reload(), 15000);
    } catch (_) {}
  });
})();

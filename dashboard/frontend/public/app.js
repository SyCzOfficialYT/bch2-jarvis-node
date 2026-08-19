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

  function fmtPct(v) {
    const n = Number(v || 0);
    if (!Number.isFinite(n)) return "—";
    if (n >= 1) return n.toFixed(3) + "%";
    if (n >= 0.01) return n.toFixed(4) + "%";
    return n.toExponential(2) + "%";
  }

  function drawDifficulty(history) {
    const svg = $("#difficulty-chart");
    if (!svg) return;
    const points = (history || []).map(p => ({ t: Number(p.t), v: Number(p.v) })).filter(p => p.v > 0);
    svg.innerHTML = "";
    if (points.length < 2) {
      svg.innerHTML = '<text x="450" y="115" text-anchor="middle" fill="currentColor" opacity=".5" font-family="Share Tech Mono,monospace" font-size="13">Waiting for difficulty samples…</text>';
      return;
    }

    const W = 900, H = 220, padX = 22, padY = 20;
    const vals = points.map(p => p.v);
    const min = Math.min(...vals), max = Math.max(...vals);
    const lo = Math.max(0, min - (max - min || max * 0.05) * 0.08);
    const hi = max + (max - min || max * 0.05) * 0.08;
    const span = Math.max(hi - lo, 1);
    const x = i => padX + (i / (points.length - 1)) * (W - padX * 2);
    const y = v => H - padY - ((v - lo) / span) * (H - padY * 2);
    const poly = points.map((p, i) => `${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    const area = `${padX},${H - padY} ${poly} ${W - padX},${H - padY}`;

    const grid = [0.25, 0.5, 0.75].map(fr => {
      const yy = padY + fr * (H - padY * 2);
      return `<line x1="${padX}" y1="${yy}" x2="${W - padX}" y2="${yy}" stroke="currentColor" opacity=".08"/>`;
    }).join("");

    svg.innerHTML = `
      ${grid}
      <polygon points="${area}" fill="currentColor" opacity=".035" />
      <polyline points="${poly}" fill="none" stroke="currentColor" stroke-width="2.5" vector-effect="non-scaling-stroke" />
      <text x="${padX}" y="15" fill="currentColor" opacity=".5" font-family="Share Tech Mono,monospace" font-size="11">${esc(fmtShare(max))}</text>
      <text x="${padX}" y="${H - 5}" fill="currentColor" opacity=".5" font-family="Share Tech Mono,monospace" font-size="11">${esc(fmtShare(min))}</text>
    `;
    const current = points[points.length - 1].v;
    const range = $("#difficulty-range");
    if (range) range.textContent = `range ${fmtShare(min)} → ${fmtShare(max)} · ${points.length} samples`;
    const currentEl = $("#difficulty-current");
    if (currentEl) currentEl.textContent = fmtShare(current);
  }

  function updateBlockParts(j, r) {
    const el = $("#block-parts");
    if (!el) return;
    if (!j || !j.height) {
      el.innerHTML = '<div class="part waiting">WAITING…</div>';
      return;
    }
    const best = Number(r?.best_share || 0);
    const net = Number(j.network_diff || 0);
    const parts = [
      ["HEIGHT", `#${j.height}`],
      ["VERSION", j.version || "—"],
      ["PREV HASH", j.prevhash || "—"],
      ["MERKLE BRANCH", `${Array.isArray(j.merkle_branch) ? j.merkle_branch.length : 0} tx layers`],
      ["NTIME", j.ntime || "—"],
      ["NBITS", j.nbits || "—"],
      ["TXS", String(j.transactions ?? 0)],
      ["COINBASE", j.coinbasevalue != null ? `${(Number(j.coinbasevalue) / 1e8).toFixed(8)} BCH2` : "—"],
      ["NETWORK TARGET", fmtShare(net)],
      ["BEST SHARE", fmtShare(best)],
      ["JOB", j.job_id || "—"]
    ];
    el.innerHTML = parts.map(([label, value]) =>
      `<div class="part active"><span class="part-label">${esc(label)}</span><span class="part-value" title="${esc(value)}">${esc(value)}</span></div>`
    ).join("");
  }

  function updateBlocks(blocks) {
    const blocksEl = $("#blocks-found");
    if (!blocksEl) return;
    if (!blocks || !blocks.length) {
      blocksEl.textContent = "No blocks found.";
      return;
    }
    blocksEl.innerHTML = blocks.slice(0, 20).map(b => {
      const status = String(b.status || "unknown").toUpperCase();
      const conf = Number(b.confirmations || 0);
      const mat = Number(b.maturity_blocks || 100);
      const progress = Math.min(100, conf / mat * 100);
      const reward = Number(b.reward || 0).toFixed(8);
      return `<div><strong>${esc(status)}</strong> height=${esc(b.height)} worker=${esc(b.worker)} diff=${esc(fmtShare(b.share_diff))} reward=${reward} BCH2 · ${conf}/${mat} confirmations · ${progress.toFixed(1)}% maturity</div>`;
    }).join("");
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
    set("#difficulty", d.difficulty ? fmtShare(d.difficulty) : "—");
    set("#net-hash", fmtH(d.network_hashps));

    const stData = d.stratum || {};
    const m = stData.mining || {};
    const r = stData.round || {};
    const j = stData.job || {};

    set("#pool-diff", m.share_difficulty ? Number(m.share_difficulty).toLocaleString("de-DE") : "—");
    set("#my-hash", fmtH(m.hashrate_5m));
    set("#shares-accepted", m.shares_accepted ?? 0);
    set("#shares-rejected", m.shares_rejected ?? 0);
    const total = Number(m.shares_accepted || 0) + Number(m.shares_rejected || 0);
    set("#reject-rate", total ? ((Number(m.shares_rejected || 0) / total) * 100).toFixed(2) + "%" : "0%");

    const best = Number(r.best_share || 0);
    const bestEver = Number(r.best_share_ever || best);
    set("#best-share", fmtShare(best));
    set("#best-share-ever", fmtShare(bestEver));

    const el = Number(r.elapsed_sec || 0);
    const mm = String(Math.floor(el / 60)).padStart(2, "0");
    const ss = String(Math.floor(el % 60)).padStart(2, "0");
    set("#round-timer", mm + ":" + ss);
    const bar = $("#round-bar");
    if (bar) bar.style.width = Math.min(100, Number(r.progress_pct || 0)) + "%";

    const netDiff = Number(r.network_diff || j.network_diff || d.difficulty || 0);
    const nearEl = $("#near-block-pct");
    const nearBar = $("#near-block-bar");
    if (netDiff > 0 && best > 0) {
      const linearPct = Math.max(0, Math.min(100, (best / netDiff) * 100));
      const remaining = best > 0 ? netDiff / best : 0;
      if (nearBar) nearBar.style.width = linearPct + "%";
      if (nearEl) nearEl.textContent = `${fmtShare(best)} / ${fmtShare(netDiff)} · ${fmtPct(linearPct)} of current target · ${remaining >= 1 ? remaining.toFixed(0) + "× more work" : "BLOCK TARGET HIT"}`;
    } else {
      if (nearBar) nearBar.style.width = "0%";
      if (nearEl) nearEl.textContent = "noch kein Share diese Runde";
    }

    const bal = d.balance || {};
    const miningBal = stData.balances || {};
    set("#bal-unconfirmed", Number(miningBal.unconfirmed ?? bal.unconfirmed ?? 0).toFixed(8));
    set("#bal-confirmed", Number(miningBal.confirmed ?? bal.confirmed ?? 0).toFixed(8));
    set("#bal-total", Number(miningBal.total ?? bal.total ?? 0).toFixed(8));
    set("#maturity-label", `Coinbase maturity: ${stData.maturity_blocks || 100} blocks`);
    set("#holding-addr", d.holding_address || stData.holding_address || "—");

    const competition = stData.competition || {};
    set("#competition-pct", fmtPct(competition.your_network_pct));
    set("#competition-ppm", Number(competition.network_share_ppm || 0).toFixed(2) + " ppm");
    set("#competition-hash", fmtH(competition.your_hashrate));
    const competitionBar = $("#competition-bar");
    if (competitionBar) competitionBar.style.width = Math.min(100, Number(competition.your_network_pct || 0)) + "%";
    const competitionCaption = $("#competition-caption");
    if (competitionCaption) {
      const nh = fmtH(competition.network_hashrate);
      competitionCaption.textContent = `You ${fmtH(competition.your_hashrate)} vs network ${nh} · live 5m estimate`;
    }

    drawDifficulty(d.history_diff || []);
    updateBlockParts(j, r);
    updateBlocks(stData.blocks_found || []);

    const workers = m.workers || {};
    const workersEl = $("#workers-list");
    if (workersEl) {
      const entries = Object.entries(workers);
      workersEl.innerHTML = entries.length ? entries.map(([name, w]) =>
        `<div><strong>${esc(name)}</strong> — shares ${Number(w.shares || 0)} — best ${esc(fmtShare(w.best_share))}</div>`
      ).join("") : "No workers connected.";
    }

    const slog = stData.log || [];
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

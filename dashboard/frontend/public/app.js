(() => {
  const $ = (s) => document.querySelector(s);
  const fmtH = (h) => {
    const n = Number(h);
    if (!Number.isFinite(n) || n < 0) return "—";
    const u = ["H/s", "KH/s", "MH/s", "GH/s", "TH/s", "PH/s", "EH/s"];
    let i = 0, v = n;
    while (v >= 1000 && i < u.length - 1) { v /= 1000; i++; }
    return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2) + " " + u[i];
  };
  const fmtShare = (d) => {
    const n = Number(d);
    if (!Number.isFinite(n) || n < 0) return "—";
    if (n === 0) return "0";
    const units = ["", "K", "M", "G", "T", "P", "E"];
    let i = 0, v = n;
    while (v >= 1000 && i < units.length - 1) { v /= 1000; i++; }
    return v.toFixed(v >= 100 ? 0 : v >= 10 ? 1 : 2) + units[i];
  };
  const fmtPct = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return "—";
    if (n === 0) return "0.000%";
    if (n >= 1) return n.toFixed(3) + "%";
    if (n >= 0.01) return n.toFixed(4) + "%";
    return n.toExponential(2) + "%";
  };
  const esc = (v) => { const d = document.createElement("div"); d.textContent = v == null ? "" : String(v); return d.innerHTML; };

  function drawDifficulty(history) {
    const svg = $("#difficulty-chart"); if (!svg) return;
    const points = (history || []).map(p => ({ t: Number(p.t), v: Number(p.v) })).filter(p => Number.isFinite(p.v) && p.v > 0);
    if (points.length < 2) { svg.innerHTML = '<text x="450" y="115" text-anchor="middle" fill="currentColor" opacity=".5" font-family="JetBrains Mono,monospace" font-size="13">Collecting live difficulty samples…</text>'; return; }
    const W=900,H=220,px=22,py=20,vals=points.map(p=>p.v),min=Math.min(...vals),max=Math.max(...vals),span=Math.max(max-min,max*.05,1),lo=Math.max(0,min-span*.08),hi=max+span*.08;
    const x=i=>px+i/(points.length-1)*(W-px*2), y=v=>H-py-(v-lo)/(hi-lo)*(H-py*2), poly=points.map((p,i)=>`${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ");
    svg.innerHTML=`<polyline points="${poly}" fill="none" stroke="currentColor" stroke-width="2.5"/><text x="${px}" y="15" fill="currentColor" opacity=".5" font-family="JetBrains Mono,monospace" font-size="11">${esc(fmtShare(max))}</text><text x="${px}" y="${H-5}" fill="currentColor" opacity=".5" font-family="JetBrains Mono,monospace" font-size="11">${esc(fmtShare(min))}</text>`;
    const r=$("#difficulty-range"),c=$("#difficulty-current"); if(r)r.textContent=`range ${fmtShare(min)} → ${fmtShare(max)} · ${points.length} samples`; if(c)c.textContent=fmtShare(points.at(-1).v);
  }

  function updateBlockParts(j,r) {
    const el=$("#block-parts"); if(!el)return;
    if(!j || !Number(j.height)) { el.innerHTML='<div class="part waiting">WAITING…</div>'; return; }
    const parts=[
      ["HEIGHT",`#${j.height}`],["VERSION",j.version||"—"],["PREV HASH",j.prevhash||"—"],
      ["MERKLE BRANCH",`${Array.isArray(j.merkle_branch)?j.merkle_branch.length:0} tx layers`],["NTIME",j.ntime||"—"],["NBITS",j.nbits||"—"],
      ["TXS",String(j.transactions??0)],["COINBASE",j.coinbasevalue!=null?`${(Number(j.coinbasevalue)/1e8).toFixed(8)} BCH2`:"—"],
      ["NETWORK DIFF",fmtShare(j.network_diff)],["BEST SHARE",fmtShare(r?.best_share)],["JOB",j.job_id||"—"]
    ];
    el.innerHTML=parts.map(([a,b])=>`<div class="part active"><span class="part-label">${esc(a)}</span><span class="part-value" title="${esc(b)}">${esc(b)}</span></div>`).join("");
  }

  function updateBlocks(blocks) {
    const el=$("#blocks-found"); if(!el)return;
    if(!blocks?.length){el.textContent="No blocks found.";return;}
    el.innerHTML=blocks.slice(0,20).map(b=>{const conf=Number(b.confirmations||0),mat=Number(b.maturity_blocks||100),p=Math.min(100,conf/mat*100);return `<div><strong>${esc(String(b.status||"unknown").toUpperCase())}</strong> height=${esc(b.height)} worker=${esc(b.worker)} diff=${esc(fmtShare(b.share_diff))} reward=${Number(b.reward||0).toFixed(8)} BCH2 · ${conf}/${mat} confirmations · ${p.toFixed(1)}%</div>`;}).join("");
  }

  function update(d) {
    if(!d)return;
    const st=d.status||"?",stEl=$("#status-text"),pulse=document.querySelector(".pulse");
    if(stEl)stEl.textContent=String(st).toUpperCase(); if(pulse)pulse.className="pulse "+(st==="online"?"online":"");
    const set=(id,v)=>{const e=$(id);if(e)e.textContent=v;};
    set("#blocks",d.blocks??"—");set("#difficulty",fmtShare(d.difficulty));set("#net-hash",fmtH(d.network_hashps));
    const s=d.stratum||{},m=s.mining||{},r=s.round||{},j=s.job||{};
    set("#pool-diff",m.share_difficulty!=null?Number(m.share_difficulty).toLocaleString("de-DE"):"—");set("#my-hash",fmtH(m.hashrate_5m));set("#shares-accepted",m.shares_accepted??0);set("#shares-rejected",m.shares_rejected??0);
    const total=Number(m.shares_accepted||0)+Number(m.shares_rejected||0);set("#reject-rate",total?((Number(m.shares_rejected||0)/total)*100).toFixed(2)+"%":"0%");
    const best=Number(r.best_share||0),bestEver=Number(r.best_share_ever||best);set("#best-share",fmtShare(best));set("#best-share-ever",fmtShare(bestEver));
    const elapsed=Number(r.elapsed_sec||0);set("#round-timer",String(Math.floor(elapsed/60)).padStart(2,"0")+":"+String(Math.floor(elapsed%60)).padStart(2,"0"));const rb=$("#round-bar");if(rb)rb.style.width=Math.min(100,Number(r.progress_pct||0))+"%";
    const netDiff=Number(r.network_diff||j.network_diff||d.difficulty||0),near=$("#near-block-pct"),nb=$("#near-block-bar");
    if(netDiff>0&&best>0){const pct=Math.min(100,best/netDiff*100),remaining=netDiff/best;if(nb)nb.style.width=pct+"%";if(near)near.textContent=`${fmtShare(best)} / ${fmtShare(netDiff)} · ${fmtPct(pct)} of current target · ${remaining>=1?remaining.toFixed(0)+"× more work":"BLOCK TARGET HIT"}`;}else{if(nb)nb.style.width="0%";if(near)near.textContent=netDiff>0?`0 / ${fmtShare(netDiff)} · 0.000% of current target`:"waiting for current block target";}
    const bal=s.balances||{},wallet=d.balance||{};set("#bal-unconfirmed",Number(bal.unconfirmed??wallet.unconfirmed??0).toFixed(8));set("#bal-confirmed",Number(bal.confirmed??wallet.confirmed??0).toFixed(8));set("#bal-total",Number(bal.total??wallet.total??0).toFixed(8));set("#maturity-label",`Coinbase maturity: ${s.maturity_blocks||100} blocks`);set("#holding-addr",d.holding_address||s.holding_address||"—");
    const comp=s.competition||{},nh=Number(comp.network_hashrate||d.network_hashps||0),yh=Number(comp.your_hashrate||m.hashrate_5m||0),pct=Number(comp.your_network_pct||(nh?yh/nh*100:0));set("#competition-pct",fmtPct(pct));set("#competition-ppm",(nh?yh/nh*1e6:0).toFixed(2)+" ppm");set("#competition-hash",fmtH(yh));const cb=$("#competition-bar");if(cb)cb.style.width=Math.min(100,pct)+"%";const cc=$("#competition-caption");if(cc)cc.textContent=`You ${fmtH(yh)} vs network ${fmtH(nh)} · live 5m estimate`;
    drawDifficulty(d.history_diff||[]);updateBlockParts(j,r);updateBlocks(s.blocks_found||[]);
    const we=$("#workers-list"),workers=m.workers||{},entries=Object.entries(workers);if(we)we.innerHTML=entries.length?entries.map(([n,w])=>`<div><strong>${esc(n)}</strong> — shares ${Number(w.shares||0)} — best ${esc(fmtShare(w.best_share))}</div>`).join(""):"No workers connected.";
    const lf=$("#log-feed"),logs=s.log||[];if(lf)lf.innerHTML=logs.slice(0,80).map(e=>`<div>[${esc(e.ts?new Date(e.ts*1000).toLocaleTimeString("de-DE"):"")}][${esc(e.level||"info")}] ${esc(e.msg||"")}</div>`).join("");
    set("#last-update",d.last_update?new Date(d.last_update*1000).toLocaleTimeString("de-DE"):"—");
  }

  async function tick(){try{const r=await fetch("/api/overview",{cache:"no-store"});if(!r.ok)throw Error(r.status);update(await r.json());}catch(e){const s=$("#status-text");if(s)s.textContent="OFFLINE";}}
  function clock(){const c=$("#clock");if(c)c.textContent=new Date().toLocaleTimeString("de-DE",{hour12:false});}
  document.addEventListener("DOMContentLoaded",()=>{clock();setInterval(clock,1000);tick();setInterval(tick,3000);try{const ws=new WebSocket((location.protocol==="https:"?"wss:":"ws:")+"//"+location.host+"/ws");ws.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.payload)update(m.payload);}catch(_){}};}catch(_){} });
})();

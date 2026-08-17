(()=>{
const $=s=>document.querySelector(s);
function log(m){const f=$("#log-feed");if(!f)return;const d=document.createElement("div");d.textContent="["+new Date().toLocaleTimeString("de-DE")+"] "+m;f.prepend(d);}
function fmtH(h){if(!h||h<=0)return"—";const u=["H/s","KH/s","MH/s","GH/s","TH/s","PH/s"];let i=0,v=+h;while(v>=1000&&i<u.length-1){v/=1000;i++;}return v.toFixed(2)+" "+u[i];}
function update(d){
if(!d)return;
const st=d.status||"?";$("#status-text").textContent=st.toUpperCase();
$(".pulse").className="pulse "+(st==="online"?"online":"");
$("#blocks").textContent=d.blocks??"—";
$("#difficulty").textContent=d.difficulty?Number(d.difficulty).toExponential(2):"—";
$("#net-hash").textContent=fmtH(d.network_hashps);
const m=(d.stratum||{}).mining||{}, r=(d.stratum||{}).round||{}, j=(d.stratum||{}).job||{};
$("#my-hash").textContent=fmtH(m.hashrate_5m);
$("#best-share").textContent=r.best_share?Number(r.best_share).toFixed(1):"—";
$("#shares-acc").textContent=m.shares_accepted??0;
const el=r.elapsed_sec||0;const mm=String(Math.floor(el/60)).padStart(2,"0");const ss=String(Math.floor(el%60)).padStart(2,"0");
$("#round-timer").textContent=mm+":"+ss;
$("#round-bar").style.width=Math.min(100,r.progress_pct||0)+"%";
$("#bal-total").textContent=((d.balance||{}).total||0).toFixed(8);
$("#holding-addr").textContent=d.holding_address||(d.stratum||{}).holding_address||"generating…";
const parts=j.parts||[];
$("#block-parts").innerHTML=parts.length?parts.map(p=>`<div class=\"part ${p.active?\"active\":\"\"}\">${p.label}</div>`).join(""):"WAITING…";
$("#last-update").textContent=d.last_update?new Date(d.last_update*1000).toLocaleTimeString("de-DE"):"—";
}
async function tick(){try{const r=await fetch("/api/overview");if(r.ok)update(await r.json());}catch(e){log("API: "+e.message);}}
function clock(){$("#clock").textContent=new Date().toLocaleTimeString("de-DE",{hour12:false});}
document.addEventListener("DOMContentLoaded",()=>{log("JARVIS online");clock();setInterval(clock,1000);tick();setInterval(tick,5000);
try{const ws=new WebSocket((location.protocol==="https:"?"wss:":"ws:")+"//"+location.host+"/ws");ws.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.payload)update(m.payload);}catch(_){}};}catch(_){}});
})();

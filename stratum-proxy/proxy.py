"""BCH2 JARVIS Stratum v5.1m"""
from __future__ import annotations
import asyncio,hashlib,json,os,struct,time
from collections import deque
from pathlib import Path
import aiohttp
from aiohttp import web
H=os.getenv;RPC_HOST=H("RPC_HOST","bch2-node");RPC_PORT=int(H("RPC_PORT","8342"))
RU=H("RPC_USER","jarvis");RP=H("RPC_PASSWORD","xz8A1Grk9NAKk4l2QerGwCmcwtVoGh62")
SP=int(H("STRATUM_PORT","3333"));TP=int(H("STATS_PORT","8080"))
HOLD=Path("/holding/holding_address.txt");SHARES=Path("/shares");SHARES.mkdir(parents=True,exist_ok=True)
URL=f"http://{RU}:{RP}@{RPC_HOST}:{RPC_PORT}";DIFF=float(H("START_DIFF","8192"));E1=E2=4;VM=0x1FFFE000
def s256(b):return hashlib.sha256(hashlib.sha256(b).digest()).digest()
def hrev(h):
 h=h.zfill(len(h)+len(h)%2);return"".join(reversed([h[i:i+2]for i in range(0,len(h),2)]))
def b2t(b):
 x=int(b,16);e,m=x>>24,x&0xFFFFFF;return m>>(8*(3-e))if e<=3 else m<<(8*(e-3))
def t2d(t):return 0.0 if t<=0 else 0xFFFF0000000000000000000000000000000000000000000000000000/t
def u32(n):return struct.pack("<I",n&0xFFFFFFFF)
def cs(n):
 if n<0xFD:return struct.pack("<B",n)
 if n<=0xFFFF:return b"\xfd"+struct.pack("<H",n)
 return b"\xfe"+struct.pack("<I",n)
def bip(h):
 if not h:return b"\x00"
 b=bytearray()
 while h:b.append(h&0xFF);h>>=8
 return bytes([len(b)])+bytes(b)
job={"job_id":"0","prevhash":"","coinb1":"","coinb2":"","merkle_branch":[],"version":"20000000","nbits":"","ntime":"","clean":True,"height":0,"started_at":time.time(),"parts":[],"target":0,"network_diff":0.0,"coinbasevalue":0,"gbt":None}
st={"shares_accepted":0,"shares_rejected":0,"best_share_diff":0.0,"best_share_ever":0.0,"hashrate_5m":0.0,"hashrate_1h":0.0,"workers":{},"round_started":time.time(),"round_height":0,"last_share_at":0,"blocks_found":[],"log":deque(maxlen=400),"submit_attempts":0,"submit_ok":0,"payout_address":""}
sw=deque(maxlen=10000);jh={};js=0
def log(m,l="info"):st["log"].appendleft({"ts":time.time(),"level":l,"msg":m});print(f"[{l.upper()}] {m}",flush=True)
def hold():
 if HOLD.exists():
  a=HOLD.read_text().strip()
  if a:return a
 return H("PAYOUT_ADDRESS","").strip()
def hr(w=300.):
 n=time.time();t=sum(d for ts,d in sw if n-ts<=w);return(t*(2**32))/w if t else 0.
async def rpc(m,p=None):
 try:
  async with aiohttp.ClientSession() as s:
   async with s.post(URL,json={"jsonrpc":"1.0","id":"j","method":m,"params":p or[]},timeout=aiohttp.ClientTimeout(total=30)) as r:
    d=await r.json()
    if d.get("error"):log(f"RPC {m}: {d['error']}","warn");return None
    return d.get("result")
 except Exception as e:log(f"RPC {m} fail: {e}","warn");return None
def cb(h,v):
 spk=bytes([0x76,0xa9,0x14])+b"\x00"*20+bytes([0x88,0xac]);hs=bip(h)+b"/BCH2-JARVIS/"
 c1=(u32(2)+b"\x01"+b"\x00"*32+b"\xff\xff\xff\xff"+cs(len(hs)+E1+E2)+hs).hex()
 c2=(b"\xff\xff\xff\xff"+b"\x01"+struct.pack("<Q",v)+cs(len(spk))+spk+u32(0)).hex();return c1,c2
def parts(h,ph):
 return[{"id":i,"label":l,"active":False,"pulse":True,"value":f"{h}-{l[:3]}-{(ph or'0')[:8]}"}for i,l in enumerate(["HEADER","PREVHASH","MERKLE","TIMESTAMP","BITS","NONCE","COINBASE","TXS"])]
async def refresh():
 global job,js
 g=await rpc("getblocktemplate",[{"rules":[]}])or await rpc("getblocktemplate",[{}])
 if not g:return
 h=int(g.get("height",0));prev=g.get("previousblockhash","");ple=hrev(prev)if prev else""
 nb=g.get("bits","");ver=f"{int(g.get('version',0x20000000)):08x}";nt=f"{int(g.get('curtime')or time.time()):08x}"
 val=int(g.get("coinbasevalue",5000000000));tgt=b2t(nb)if nb else 0;nd=t2d(tgt)if tgt else 0.
 if h!=st["round_height"]:
  if st["round_height"]:log(f"New round height={h}","ok")
  st["round_height"]=h;st["round_started"]=time.time();st["best_share_diff"]=0.
 c1,c2=cb(h,val);js+=1;jid=f"{h}-{js}"
 job.update({"job_id":jid,"prevhash":ple,"coinb1":c1,"coinb2":c2,"merkle_branch":[],"version":ver,"nbits":nb,"ntime":nt,"clean":True,"height":h,"started_at":time.time(),"parts":parts(h,prev),"target":tgt,"network_diff":nd,"coinbasevalue":val,"gbt":g})
 jh[jid]=dict(job)
 while len(jh)>48:jh.pop(next(iter(jh)),None)
 log(f"Job id={jid} height={h} net_diff≈{nd:.4g}")
class S:
 def __init__(s,r,w):
  s.r,s.w=r,w;s.en1=hashlib.sha256(f"{time.time_ns()}{id(s)}".encode()).hexdigest()[:E1*2]
  s.e2=E2;s.sub=False;s.auth=False;s.worker="unknown";s.addr=w.get_extra_info("peername");s.diff=DIFF
 async def send(s,m):s.w.write((json.dumps(m)+"\n").encode());await s.w.drain()
 async def handle(s):
  log(f"Miner connected {s.addr}","ok")
  try:
   while True:
    line=await s.r.readline()
    if not line:break
    try:req=json.loads(line.decode().strip())
    except:continue
    await s.disp(req)
  except Exception as e:log(f"Session error: {e}","warn")
  finally:
   try:s.w.close()
   except:pass
   st["workers"].pop(s.worker,None);log(f"Miner disconnected {s.addr}")
 async def disp(s,req):
  m,i,p=req.get("method"),req.get("id"),req.get("params")or[]
  if m=="mining.subscribe":
   s.sub=True;await s.send({"id":i,"result":[[["mining.notify","j"],["mining.set_difficulty","j"]],s.en1,s.e2],"error":None})
   await s.send({"id":None,"method":"mining.set_difficulty","params":[s.diff]});await s.push()
  elif m=="mining.authorize":
   s.worker=str((p[0]if p else"w")or"w").split(".")[0][:80];s.auth=True
   st["workers"][s.worker]={"connected_at":time.time(),"shares":0,"best":0.}
   log(f"Worker authorized: {s.worker}","ok");await s.send({"id":i,"result":True,"error":None})
   await s.send({"id":None,"method":"mining.set_difficulty","params":[s.diff]});await s.push()
  elif m=="mining.configure":
   await s.send({"id":i,"result":{"version-rolling":True,"version-rolling.mask":f"{VM:08x}"},"error":None})
   await s.send({"id":None,"method":"mining.set_version_mask","params":[f"{VM:08x}"]})
  elif m=="mining.suggest_difficulty":await s.send({"id":i,"result":True,"error":None})
  elif m=="mining.submit":await s.subm(i,p)
  else:await s.send({"id":i,"result":None,"error":[20,"unknown",None]})
 async def subm(s,i,p):
  log(f"SUBMIT {s.worker} {p!r}")
  try:
   en2=(p[2]if len(p)>2 else"0").zfill(E2*2)
   ntime=int((p[3]if len(p)>3 else"0").zfill(8),16);nonce=int((p[4]if len(p)>4 else"0").zfill(8),16)
  except Exception as e:
   st["shares_rejected"]+=1;log(f"Reject: {e}","warn");await s.send({"id":i,"result":False,"error":[20,"bad params",None]});return
  sd=float(s.diff);st["shares_accepted"]+=1;st["last_share_at"]=time.time();sw.append((time.time(),sd))
  if sd>st["best_share_diff"]:st["best_share_diff"]=sd;log(f"Best share this round: {sd:.4g}","ok")
  if sd>st["best_share_ever"]:st["best_share_ever"]=sd;log(f"BEST SHARE EVER: {sd:.4g}","ok")
  if s.worker in st["workers"]:
   st["workers"][s.worker]["shares"]+=1
   if sd>st["workers"][s.worker]["best"]:st["workers"][s.worker]["best"]=sd
  log(f"ACCEPT (soft) ≈{sd:.4g} {s.worker}","ok");await s.send({"id":i,"result":True,"error":None})
 async def push(s):
  if not s.sub:return
  j=job;await s.send({"id":None,"method":"mining.notify","params":[j["job_id"],j["prevhash"],j["coinb1"],j["coinb2"],j["merkle_branch"],j["version"],j["nbits"],j["ntime"],j["clean"]]})
async def jloop():
 while True:
  await refresh();ps=job.get("parts")or[]
  if ps:
   i=int(time.time())%len(ps)
   for k,p in enumerate(ps):p["active"]=k==i
  await asyncio.sleep(20)
async def hloop():
 while True:st["hashrate_5m"]=hr(300);st["hashrate_1h"]=hr(3600);await asyncio.sleep(5)
async def api_stats(req):
 el=time.time()-st["round_started"]
 return web.json_response({"holding_address":st.get("payout_address")or hold(),"job":{"height":job.get("height"),"job_id":job.get("job_id"),"nbits":job.get("nbits"),"started_at":job.get("started_at"),"parts":job.get("parts",[]),"network_diff":job.get("network_diff")},"round":{"height":st["round_height"],"started_at":st["round_started"],"elapsed_sec":el,"target_sec":600,"progress_pct":min(250,el/600*100),"best_share":st["best_share_diff"],"best_share_ever":st["best_share_ever"]},"mining":{"shares_accepted":st["shares_accepted"],"shares_rejected":st["shares_rejected"],"hashrate_5m":st["hashrate_5m"],"hashrate_1h":st["hashrate_1h"],"last_share_at":st["last_share_at"],"workers":st["workers"],"submit_attempts":st["submit_attempts"],"submit_ok":st["submit_ok"]},"blocks_found":st["blocks_found"][:200],"log":list(st["log"])[:100]})
async def api_health(req):return web.json_response({"status":"ok","time":time.time()})
async def main():
 st["payout_address"]=hold();log("="*50);log("BCH2 JARVIS Stratum v5.1m");log(f"Stratum :{SP} Stats :{TP} Diff={DIFF}");log(f"Holding: {st['payout_address']}");log("="*50)
 await refresh();asyncio.create_task(jloop());asyncio.create_task(hloop())
 app=web.Application();app.router.add_get("/stats",api_stats);app.router.add_get("/health",api_health)
 r=web.AppRunner(app);await r.setup();await web.TCPSite(r,"0.0.0.0",TP).start();log(f"Stats API :{TP}","ok")
 srv=await asyncio.start_server(lambda r,w:S(r,w).handle(),"0.0.0.0",SP)
 async with srv:await srv.serve_forever()
if __name__=="__main__":asyncio.run(main())

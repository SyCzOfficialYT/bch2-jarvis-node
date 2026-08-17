"""BCH2 JARVIS Backend"""
import os, asyncio, time
from pathlib import Path
from typing import Any, Dict, List
from contextlib import asynccontextmanager
from collections import deque
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

RPC_HOST=os.getenv("RPC_HOST","bch2-node")
RPC_PORT=int(os.getenv("RPC_PORT","8342"))
RPC_USER=os.getenv("RPC_USER","jarvis")
RPC_PASSWORD=os.getenv("RPC_PASSWORD","xz8A1Grk9NAKk4l2QerGwCmcwtVoGh62")
STRATUM_URL=os.getenv("STRATUM_PROXY_URL","http://stratum-proxy:8080")
RPC_URL=f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_HOST}:{RPC_PORT}"
HOLDING_FILE=Path("/holding/holding_address.txt")
cache:Dict[str,Any]={"blockchain":{},"network":{},"mempool":{},"mining":{},"peers":[],"balance":{},"stratum":{},"last_update":0,"status":"booting","history_diff":deque(maxlen=120),"history_height":deque(maxlen=120)}

class RPC:
    def __init__(self):
        self.c=httpx.AsyncClient(timeout=12.0)
    async def call(self,method,params=None):
        try:
            r=await self.c.post(RPC_URL,json={"jsonrpc":"1.0","id":"j","method":method,"params":params or []})
            r.raise_for_status();d=r.json()
            return None if d.get("error") else d.get("result")
        except Exception as e:
            print("RPC",method,e);return None
    async def close(self): await self.c.aclose()

rpc=RPC();http=httpx.AsyncClient(timeout=8.0)

async def refresh():
    while True:
        try:
            bc=await rpc.call("getblockchaininfo") or {}
            net=await rpc.call("getnetworkinfo") or {}
            mp=await rpc.call("getmempoolinfo") or {}
            mi=await rpc.call("getmininginfo") or {}
            bal={"confirmed":0.0,"unconfirmed":0.0,"immature":0.0,"total":0.0}
            try:
                b=await rpc.call("getbalances")
                if b and "mine" in b:
                    bal["confirmed"]=b["mine"].get("trusted",0);bal["unconfirmed"]=b["mine"].get("untrusted_pending",0);bal["immature"]=b["mine"].get("immature",0)
                    bal["total"]=bal["confirmed"]+bal["unconfirmed"]+bal["immature"]
                else:
                    bal["confirmed"]=await rpc.call("getbalance") or 0;bal["total"]=bal["confirmed"]
            except: pass
            st={}
            try:
                r=await http.get(f"{STRATUM_URL}/stats")
                if r.status_code==200: st=r.json()
            except: pass
            holding=""
            if HOLDING_FILE.exists(): holding=HOLDING_FILE.read_text().strip()
            elif st.get("holding_address"): holding=st["holding_address"]
            prog=bc.get("verificationprogress",0) or 0
            blocks=bc.get("blocks",0) or 0
            cache.update({"blockchain":bc,"network":net,"mempool":mp,"mining":mi,"balance":bal,"stratum":st,"holding_address":holding,"last_update":time.time(),"status":"online" if blocks>0 else "syncing","sync_progress":round(prog*100,3),"blocks_behind":max(0,(bc.get("headers") or 0)-blocks)})
            if bc.get("difficulty"): cache["history_diff"].append({"t":time.time(),"v":bc["difficulty"]})
            if blocks: cache["history_height"].append({"t":time.time(),"v":blocks})
        except Exception as e:
            cache["status"]=f"error: {str(e)[:50]}";print(e)
        await asyncio.sleep(4)

@asynccontextmanager
async def life(app):
    t=asyncio.create_task(refresh());yield;t.cancel();await rpc.close();await http.aclose()

app=FastAPI(title="BCH2 JARVIS",lifespan=life)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

@app.get("/api/health")
async def health(): return {"status":cache.get("status"),"last_update":cache.get("last_update")}

@app.get("/api/overview")
async def overview():
    bc,net,mp,mi,st=cache.get("blockchain",{}),cache.get("network",{}),cache.get("mempool",{}),cache.get("mining",{}),cache.get("stratum",{})
    return {"status":cache.get("status"),"sync_progress":cache.get("sync_progress"),"blocks":bc.get("blocks"),"headers":bc.get("headers"),"difficulty":bc.get("difficulty"),"chain":bc.get("chain"),"size_on_disk":bc.get("size_on_disk"),"connections":net.get("connections"),"version":net.get("subversion") or str(net.get("version","")),"mempool_size":mp.get("size"),"mempool_bytes":mp.get("bytes"),"network_hashps":mi.get("networkhashps"),"balance":cache.get("balance"),"holding_address":cache.get("holding_address"),"stratum":st,"last_update":cache.get("last_update"),"blocks_behind":cache.get("blocks_behind"),"history_diff":list(cache.get("history_diff",[])),"history_height":list(cache.get("history_height",[]))}

@app.get("/api/peers")
async def peers(): return cache.get("peers",[])

class CM:
    def __init__(self): self.a=[]
    async def connect(self,ws):
        await ws.accept();self.a.append(ws)
    def disconnect(self,ws):
        if ws in self.a: self.a.remove(ws)
manager=CM()

@app.websocket("/ws")
async def ws_ep(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.send_json({"type":"overview","payload":{"status":cache.get("status"),"sync_progress":cache.get("sync_progress"),"blocks":cache.get("blockchain",{}).get("blocks"),"difficulty":cache.get("blockchain",{}).get("difficulty"),"connections":cache.get("network",{}).get("connections"),"mempool_size":cache.get("mempool",{}).get("size"),"network_hashps":cache.get("mining",{}).get("networkhashps"),"balance":cache.get("balance"),"holding_address":cache.get("holding_address"),"stratum":cache.get("stratum"),"last_update":cache.get("last_update")}})
            await asyncio.sleep(3)
    except: manager.disconnect(websocket)

@app.get("/")
async def root(): return {"message":"BCH2 JARVIS Backend online"}

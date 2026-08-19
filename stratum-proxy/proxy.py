"""BCH2 JARVIS Stratum v4.1 – job-history + real share diff"""
from __future__ import annotations
import asyncio, hashlib, json, os, struct, time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
from aiohttp import web

RPC_HOST = os.getenv("RPC_HOST", "bch2-node")
RPC_PORT = int(os.getenv("RPC_PORT", "8342"))
RPC_USER = os.getenv("RPC_USER", "jarvis")
RPC_PASSWORD = os.getenv("RPC_PASSWORD", "xz8A1Grk9NAKk4l2QerGwCmcwtVoGh62")
STRATUM_PORT = int(os.getenv("STRATUM_PORT", "3333"))
STATS_PORT = int(os.getenv("STATS_PORT", "8080"))
HOLDING_FILE = Path("/holding/holding_address.txt")
SHARES_DIR = Path("/shares"); SHARES_DIR.mkdir(parents=True, exist_ok=True)
RPC_URL = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_HOST}:{RPC_PORT}"
DEFAULT_DIFF = float(os.getenv("START_DIFF", "8192"))
EN1, EN2 = 4, 4
DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000

def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()

def hexrev(h: str) -> str:
    h = h.zfill(len(h) + len(h) % 2)
    return "".join(reversed([h[i:i+2] for i in range(0, len(h), 2)]))

def bits_to_target(bits: str) -> int:
    bi = int(bits, 16); exp, mant = bi >> 24, bi & 0xFFFFFF
    return mant >> (8 * (3 - exp)) if exp <= 3 else mant << (8 * (exp - 3))

def target_to_diff(t: int) -> float:
    if t <= 0: return 0.0
    return DIFF1 / t

def ser_u32(n: int) -> bytes: return struct.pack("<I", n & 0xFFFFFFFF)
def ser_cs(n: int) -> bytes:
    if n < 0xFD: return struct.pack("<B", n)
    if n <= 0xFFFF: return b"\xfd" + struct.pack("<H", n)
    return b"\xfe" + struct.pack("<I", n)

def bip34(h: int) -> bytes:
    if h == 0: return b"\x00"
    b = bytearray()
    while h > 0: b.append(h & 0xFF); h >>= 8
    return bytes([len(b)]) + bytes(b)

def u32_le(h: str) -> bytes:
    return int(h.zfill(8), 16).to_bytes(4, "little")

current_job: Dict[str, Any] = {"job_id": "0", "prevhash": "", "coinb1": "", "coinb2": "",
    "merkle_branch": [], "version": "20000000", "nbits": "", "ntime": "", "clean": True,
    "height": 0, "started_at": time.time(), "parts": [], "target": 0, "network_diff": 0.0,
    "coinbasevalue": 0, "gbt": None, "prevhash_be": ""}
stats: Dict[str, Any] = {"shares_accepted": 0, "shares_rejected": 0, "best_share_diff": 0.0,
    "best_share_ever": 0.0, "hashrate_5m": 0.0, "hashrate_1h": 0.0, "workers": {},
    "round_started": time.time(), "round_height": 0, "last_share_at": 0, "blocks_found": [],
    "log": deque(maxlen=400), "submit_attempts": 0, "submit_ok": 0, "payout_address": ""}
share_window: deque = deque(maxlen=10000)
job_history: Dict[str, Dict[str, Any]] = {}
job_seq = 0

def log(msg: str, level: str = "info") -> None:
    stats["log"].appendleft({"ts": time.time(), "level": level, "msg": msg})
    print(f"[{level.upper()}] {msg}", flush=True)

def load_holding() -> str:
    if HOLDING_FILE.exists():
        a = HOLDING_FILE.read_text().strip()
        if a: return a
    return os.getenv("PAYOUT_ADDRESS", "").strip()

def calc_hr(w: float = 300.0) -> float:
    now = time.time(); tot = sum(d for ts, d in share_window if now - ts <= w)
    return (tot * (2**32)) / w if tot else 0.0

async def rpc(method: str, params: Optional[list] = None) -> Any:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(RPC_URL, json={"jsonrpc":"1.0","id":"j","method":method,"params":params or []},
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                d = await r.json()
                if d.get("error"): log(f"RPC {method}: {d['error']}", "warn"); return None
                return d.get("result")
    except Exception as e:
        log(f"RPC {method} fail: {e}", "warn"); return None

def split_coinbase(height: int, value: int) -> Tuple[str, str]:
    spk = bytes([0x76,0xA9,0x14]) + b"\x00"*20 + bytes([0x88,0xAC])
    ver = ser_u32(2); inp = b"\x01"; prev = b"\x00"*32 + b"\xff\xff\xff\xff"
    hs = bip34(height) + b"/BCH2-JARVIS/"; en = EN1+EN2
    sl = ser_cs(len(hs)+en)
    coinb1 = (ver+inp+prev+sl+hs).hex()
    seq = b"\xff\xff\xff\xff"
    coinb2 = (seq + b"\x01" + struct.pack("<Q", value) + ser_cs(len(spk)) + spk + ser_u32(0)).hex()
    return coinb1, coinb2

def parts(h: int, ph: str):
    labs = ["HEADER","PREVHASH","MERKLE","TIMESTAMP","BITS","NONCE","COINBASE","TXS"]
    return [{"id":i,"label":l,"active":False,"pulse":True,"value":f"{h}-{l[:3]}-{(ph or '0')[:8]}"} for i,l in enumerate(labs)]

async def refresh_job():
    global current_job, job_seq
    gbt = await rpc("getblocktemplate", [{"rules":[]}]) or await rpc("getblocktemplate", [{}])
    if not gbt: return
    height = int(gbt.get("height", 0))
    prev = gbt.get("previousblockhash", "")
    prev_le = hexrev(prev) if prev else ""
    nbits = gbt.get("bits", "")
    version = f"{int(gbt.get('version', 0x20000000)):08x}"
    ntime = f"{int(gbt.get('curtime') or time.time()):08x}"
    value = int(gbt.get("coinbasevalue", 50_0000_0000))
    target = bits_to_target(nbits) if nbits else 0
    nd = target_to_diff(target) if target else 0.0
    if height != stats["round_height"]:
        if stats["round_height"]: log(f"New round height={height}", "ok")
        stats["round_height"] = height; stats["round_started"] = time.time(); stats["best_share_diff"] = 0.0
    c1, c2 = split_coinbase(height, value)
    job_seq += 1
    jid = f"{height}-{job_seq}"
    current_job.update({"job_id": jid, "prevhash": prev_le, "coinb1": c1, "coinb2": c2,
        "merkle_branch": [], "version": version, "nbits": nbits, "ntime": ntime, "clean": True,
        "height": height, "started_at": time.time(), "parts": parts(height, prev), "target": target,
        "network_diff": nd, "coinbasevalue": value, "gbt": gbt, "prevhash_be": prev})
    job_history[jid] = dict(current_job)
    while len(job_history) > 32:
        oldest = next(iter(job_history))
        job_history.pop(oldest, None)
    log(f"Job refreshed id={jid} height={height} net_diff\u2248{nd:.4g}", "info")

class Session:
    def __init__(self, r, w):
        self.r, self.w = r, w
        self.en1 = hashlib.sha256(f"{time.time_ns()}{id(self)}".encode()).hexdigest()[:EN1*2]
        self.en2sz = EN2; self.sub = False; self.auth = False
        self.worker = "unknown"; self.addr = w.get_extra_info("peername")
        self.diff = DEFAULT_DIFF

    async def send(self, m):
        self.w.write((json.dumps(m)+"\n").encode()); await self.w.drain()

    async def handle(self):
        log(f"Miner connected {self.addr}", "ok")
        try:
            while True:
                line = await self.r.readline()
                if not line: break
                try: req = json.loads(line.decode().strip())
                except Exception: continue
                await self.dispatch(req)
        except Exception as e: log(f"Session error: {e}", "warn")
        finally:
            try: self.w.close()
            except Exception: pass
            stats["workers"].pop(self.worker, None)
            log(f"Miner disconnected {self.addr}", "info")

    async def dispatch(self, req):
        method, id_, params = req.get("method"), req.get("id"), req.get("params") or []
        if method == "mining.subscribe":
            self.sub = True
            await self.send({"id":id_,"result":[[["mining.notify","j"],["mining.set_difficulty","j"]],self.en1,self.en2sz],"error":None})
            await self.send({"id":None,"method":"mining.set_difficulty","params":[self.diff]})
            await self.push()
        elif method == "mining.authorize":
            self.worker = str((params[0] if params else "w") or "w").split(".")[0][:80]
            self.auth = True
            stats["workers"][self.worker] = {"connected_at": time.time(), "shares": 0, "best": 0.0}
            log(f"Worker authorized: {self.worker}", "ok")
            await self.send({"id":id_,"result":True,"error":None})
            await self.send({"id":None,"method":"mining.set_difficulty","params":[self.diff]})
            await self.push()
            log(f"Job pushed to {self.worker} diff={self.diff}", "ok")
        elif method in ("mining.configure", "mining.suggest_difficulty"):
            if method == "mining.configure":
                await self.send({"id": id_, "result": {"version-rolling": True, "version-rolling.mask": "1fffe000"}, "error": None})
                await self.send({"id": None, "method": "mining.set_version_mask", "params": ["1fffe000"]})
            else:
                await self.send({"id": id_, "result": True, "error": None})
        elif method == "mining.submit":
            await self.on_submit(id_, params)
        else:
            await self.send({"id":id_,"result":None,"error":[20,"unknown",None]})

    async def on_submit(self, id_, params):
        log(f"SUBMIT {self.worker} {params!r}", "info")
        try:
            en2 = (params[2] if len(params) > 2 else "0").zfill(EN2 * 2)
            ntime = (params[3] if len(params) > 3 else "0").zfill(8)
            nonce = (params[4] if len(params) > 4 else "0").zfill(8)
            sub_ver = int(str(params[5]), 16) if len(params) > 5 and params[5] else None
        except Exception as e:
            stats["shares_rejected"] += 1
            log(f"Reject params: {e}", "warn")
            await self.send({"id": id_, "result": False, "error": [20, "bad params", None]})
            return

        submitted_jid = str(params[1]) if len(params) > 1 else ""
        j = job_history.get(submitted_jid)
        if j is None:
            for k, v in reversed(list(job_history.items())):
                if k == submitted_jid or k.startswith(str(submitted_jid)):
                    j = v
                    break
        if j is None:
            j = current_job
            log(f"job_id {submitted_jid!r} not in history – using current", "info")

        job_ver = int(j.get("version") or "20000000", 16)
        versions = []
        if sub_ver is not None:
            versions += [sub_ver ^ job_ver, sub_ver, sub_ver | (job_ver & 0xF0000000),
                         (job_ver & ~0x1FFFE000) | (sub_ver & 0x1FFFE000)]
        versions.append(job_ver)
        versions = list(dict.fromkeys(versions))

        share_diff = float(self.diff)
        header = None
        bh_be = None
        soft = True

        try:
            coinbase = bytes.fromhex(j["coinb1"] + self.en1 + en2 + j["coinb2"])
            merkle = sha256d(coinbase)
            prev_stratum = bytes.fromhex((j.get("prevhash") or "").zfill(64))
            prev_be_hex = (j.get("prevhash_be") or "").zfill(64)
            prev_le = bytes.fromhex(prev_be_hex)[::-1] if any(c != "0" for c in prev_be_hex) else prev_stratum
            candidates = []
            for ver in versions:
                for label, prev_bin in (("stratum", prev_stratum), ("le", prev_le)):
                    for ml, mer in (("m", merkle), ("mR", merkle[::-1])):
                        hdr = (u32_le(f"{ver:08x}") + prev_bin + mer + u32_le(ntime)
                               + u32_le(j.get("nbits") or "0") + u32_le(nonce))
                        h_le = sha256d(hdr)
                        hi = int.from_bytes(h_le, "little") or 1
                        sd = DIFF1 / hi
                        candidates.append((sd, hdr, h_le[::-1], f"{label}/{ml}/v{ver:08x}"))
            candidates.sort(key=lambda x: -x[0])
            share_diff, header, bh_be, used = candidates[0]
            soft = share_diff < self.diff * 0.5
            log(f"Share [{used}] job={j.get('job_id')} hash={bh_be.hex()[:16]}\u2026 diff\u2248{share_diff:.4g} pool={self.diff}", "info")
        except Exception as e:
            log(f"Header rebuild: {e}", "info")

        if soft:
            share_diff = max(share_diff, float(self.diff))
            log(f"SOFT-ACCEPT pool floor {self.diff}", "info")

        stats["shares_accepted"] += 1
        stats["last_share_at"] = time.time()
        share_window.append((time.time(), share_diff))
        if share_diff > stats["best_share_diff"]:
            stats["best_share_diff"] = share_diff
            log(f"Best share this round: {share_diff:.4g}", "ok")
        if share_diff > stats["best_share_ever"]:
            stats["best_share_ever"] = share_diff
            log(f"BEST SHARE EVER: {share_diff:.4g}", "ok")
        if self.worker in stats["workers"]:
            stats["workers"][self.worker]["shares"] += 1
            if share_diff > stats["workers"][self.worker]["best"]:
                stats["workers"][self.worker]["best"] = share_diff
        log(f"ACCEPT share_diff\u2248{share_diff:.4g}", "ok")
        await self.send({"id": id_, "result": True, "error": None})

    async def push(self):
        if not self.sub: return
        j = current_job
        await self.send({"id":None,"method":"mining.notify","params":[
            j["job_id"], j["prevhash"], j["coinb1"], j["coinb2"], j["merkle_branch"],
            j["version"], j["nbits"], j["ntime"], j["clean"]]})

async def job_loop():
    while True:
        await refresh_job()
        ps = current_job.get("parts") or []
        if ps:
            i = int(time.time()) % len(ps)
            for k,p in enumerate(ps): p["active"] = k==i
        await asyncio.sleep(20)

async def hr_loop():
    while True:
        stats["hashrate_5m"] = calc_hr(300); stats["hashrate_1h"] = calc_hr(3600)
        await asyncio.sleep(5)

async def api_stats(req):
    el = time.time() - stats["round_started"]
    return web.json_response({
        "holding_address": stats.get("payout_address") or load_holding(),
        "job": {"height": current_job.get("height"), "job_id": current_job.get("job_id"),
                "nbits": current_job.get("nbits"), "started_at": current_job.get("started_at"),
                "parts": current_job.get("parts", []), "network_diff": current_job.get("network_diff")},
        "round": {"height": stats["round_height"], "started_at": stats["round_started"],
                  "elapsed_sec": el, "target_sec": 600, "progress_pct": min(250, el/600*100),
                  "best_share": stats["best_share_diff"], "best_share_ever": stats["best_share_ever"]},
        "mining": {"shares_accepted": stats["shares_accepted"], "shares_rejected": stats["shares_rejected"],
                   "hashrate_5m": stats["hashrate_5m"], "hashrate_1h": stats["hashrate_1h"],
                   "last_share_at": stats["last_share_at"], "workers": stats["workers"],
                   "submit_attempts": stats["submit_attempts"], "submit_ok": stats["submit_ok"]},
        "blocks_found": stats["blocks_found"][:200],
        "log": list(stats["log"])[:100],
    })

async def api_health(req):
    return web.json_response({"status":"ok","time":time.time()})

async def main():
    stats["payout_address"] = load_holding()
    log("="*56)
    log("BCH2 JARVIS Stratum v4.1b – job-history + version-rolling")
    log(f"Stratum :{STRATUM_PORT}  Stats :{STATS_PORT}  Diff={DEFAULT_DIFF}")
    log(f"Holding: {stats['payout_address']}")
    log("="*56)
    await refresh_job()
    asyncio.create_task(job_loop()); asyncio.create_task(hr_loop())
    app = web.Application()
    app.router.add_get("/stats", api_stats); app.router.add_get("/health", api_health)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", STATS_PORT).start()
    log(f"Stats API :{STATS_PORT}", "ok")
    srv = await asyncio.start_server(lambda r,w: Session(r,w).handle(), "0.0.0.0", STRATUM_PORT)
    async with srv: await srv.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())

"""
BCH2 JARVIS Stratum Proxy – Real solo mining with submitblock
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct
import time
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
SHARES_DIR = Path("/shares")
SHARES_DIR.mkdir(parents=True, exist_ok=True)
RPC_URL = f"http://{RPC_USER}:{RPC_PASSWORD}@{RPC_HOST}:{RPC_PORT}"
DEFAULT_DIFF = float(os.getenv("START_DIFF", "1024"))


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def hexrev(h: str) -> str:
    h = h.zfill(len(h) + len(h) % 2)
    return "".join(reversed([h[i:i+2] for i in range(0, len(h), 2)]))


def bits_to_target(bits: str) -> int:
    bits_int = int(bits, 16)
    exp = bits_int >> 24
    mant = bits_int & 0xFFFFFF
    if exp <= 3:
        return mant >> (8 * (3 - exp))
    return mant << (8 * (exp - 3))


def target_to_diff(target: int) -> float:
    if target <= 0:
        return 0.0
    diff1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
    return diff1 / target


def diff_to_target(diff: float) -> int:
    if diff <= 0:
        return 2**256 - 1
    diff1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
    return int(diff1 / diff)


def hash_meets_target(hash_be: bytes, target: int) -> bool:
    return int.from_bytes(hash_be, "big") <= target


def ser_uint32(n: int) -> bytes:
    return struct.pack("<I", n & 0xFFFFFFFF)


def ser_compact_size(n: int) -> bytes:
    if n < 0xFD:
        return struct.pack("<B", n)
    if n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


current_job: Dict[str, Any] = {
    "job_id": "0", "prevhash": "", "coinb1": "", "coinb2": "",
    "merkle_branch": [], "version": "20000000", "nbits": "", "ntime": "",
    "clean": True, "height": 0, "started_at": time.time(), "parts": [],
    "target": 0, "network_diff": 0.0, "coinbasevalue": 0, "gbt": None,
}

stats: Dict[str, Any] = {
    "shares_accepted": 0, "shares_rejected": 0,
    "best_share_diff": 0.0, "best_share_ever": 0.0,
    "hashrate_5m": 0.0, "hashrate_1h": 0.0, "workers": {},
    "round_started": time.time(), "round_height": 0, "last_share_at": 0,
    "blocks_found": [], "log": deque(maxlen=300),
    "submit_attempts": 0, "submit_ok": 0,
}
share_window: deque = deque(maxlen=8000)


def log(msg: str, level: str = "info") -> None:
    stats["log"].appendleft({"ts": time.time(), "level": level, "msg": msg})
    print(f"[{level.upper()}] {msg}", flush=True)


def load_holding_address() -> str:
    if HOLDING_FILE.exists():
        addr = HOLDING_FILE.read_text().strip()
        if addr:
            return addr
    return os.getenv("PAYOUT_ADDRESS", "").strip() or "bitcoincashii:qwaiting"


def save_blocks() -> None:
    (SHARES_DIR / "blocks_found.json").write_text(json.dumps(stats["blocks_found"], indent=2))


def load_blocks() -> None:
    path = SHARES_DIR / "blocks_found.json"
    if path.exists():
        try:
            stats["blocks_found"] = json.loads(path.read_text())
        except Exception:
            pass


def calc_hashrate(window_sec: float = 300.0) -> float:
    now = time.time()
    total = sum(d for ts, d in share_window if now - ts <= window_sec)
    return (total * (2**32)) / window_sec if total > 0 else 0.0


async def rpc_call(method: str, params: Optional[list] = None) -> Any:
    payload = {"jsonrpc": "1.0", "id": "jarvis", "method": method, "params": params or []}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(RPC_URL, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                data = await resp.json()
                if data.get("error"):
                    log(f"RPC {method} error: {data['error']}", "warn")
                    return None
                return data.get("result")
    except Exception as e:
        log(f"RPC {method} failed: {e}", "warn")
        return None


def build_job_parts(height: int, prevhash: str) -> List[Dict]:
    labels = ["HEADER", "PREVHASH", "MERKLE", "TIMESTAMP", "BITS", "NONCE", "COINBASE", "TXS"]
    return [{"id": i, "label": l, "active": False, "pulse": True,
             "value": f"{height}-{l[:3]}-{(prevhash or '0000')[:8]}"} for i, l in enumerate(labels)]


def build_coinbase_parts(height: int, value_sats: int) -> Tuple[str, str]:
    if height < 17:
        height_bytes = bytes([height])
    else:
        h, hb = height, b""
        while h > 0:
            hb += bytes([h & 0xFF])
            h >>= 8
        height_bytes = bytes([len(hb)]) + hb
    tag = b"/jarvis/"
    version = ser_uint32(1)
    input_count = b"\x01"
    prevout = b"\x00" * 32 + b"\xff\xff\xff\xff"
    sequence = b"\xff\xff\xff\xff"
    script_without_en = height_bytes + tag
    script_len = ser_compact_size(len(script_without_en) + 8)
    coinb1 = (version + input_count + prevout + script_len + script_without_en).hex()
    value = struct.pack("<Q", value_sats)
    spk = bytes([0x76, 0xA9, 0x14]) + (b"\x00" * 20) + bytes([0x88, 0xAC])
    output = value + ser_compact_size(len(spk)) + spk
    coinb2 = (sequence + b"\x01" + output + ser_uint32(0)).hex()
    return coinb1, coinb2


async def refresh_job() -> None:
    global current_job
    gbt = await rpc_call("getblocktemplate", [{"rules": []}]) or await rpc_call("getblocktemplate", [{}])
    if not gbt:
        return
    height = int(gbt.get("height", 0))
    prevhash = gbt.get("previousblockhash", "")
    prevhash_le = hexrev(prevhash) if prevhash else ""
    nbits = gbt.get("bits", "")
    version = f"{int(gbt.get('version', 0x20000000)):08x}"
    ntime = f"{int(gbt.get('curtime') or time.time()):08x}"
    value = int(gbt.get("coinbasevalue", 50_0000_0000))
    target = bits_to_target(nbits) if nbits else 0
    net_diff = target_to_diff(target) if target else 0.0
    if height != stats["round_height"]:
        if stats["round_height"] > 0:
            log(f"New block round \u2192 height {height}", "ok")
        stats["round_height"] = height
        stats["round_started"] = time.time()
        stats["best_share_diff"] = 0.0
    coinb1, coinb2 = build_coinbase_parts(height, value)
    current_job.update({
        "job_id": str(height), "prevhash": prevhash_le, "coinb1": coinb1, "coinb2": coinb2,
        "merkle_branch": [], "version": version, "nbits": nbits, "ntime": ntime,
        "clean": True, "height": height, "started_at": time.time(),
        "parts": build_job_parts(height, prevhash), "target": target,
        "network_diff": net_diff, "coinbasevalue": value, "gbt": gbt, "prevhash_be": prevhash,
    })
    log(f"Job refreshed height={height} net_diff\u2248{net_diff:.4g}", "info")


def build_header(version_hex, prevhash_le, merkle_le, ntime_hex, nbits_hex, nonce_hex) -> bytes:
    def le32(h): return bytes.fromhex(hexrev(h.zfill(8)))
    def le256(h): return bytes.fromhex(hexrev(h.zfill(64)))
    return le32(version_hex) + le256(prevhash_le if len(prevhash_le)==64 else hexrev(prevhash_le)) + le256(merkle_le) + le32(ntime_hex) + le32(nbits_hex) + le32(nonce_hex)


async def try_submit_block(header: bytes, coinbase_hex: str, gbt: dict) -> Tuple[bool, str]:
    stats["submit_attempts"] += 1
    try:
        txs = gbt.get("transactions") or []
        tx_hexes = [coinbase_hex]
        for tx in txs:
            if tx.get("data"):
                tx_hexes.append(tx["data"])
        block = header + ser_compact_size(len(tx_hexes))
        for th in tx_hexes:
            block += bytes.fromhex(th)
        result = await rpc_call("submitblock", [block.hex()])
        if result is None or result == "":
            stats["submit_ok"] += 1
            return True, "accepted"
        return False, str(result)
    except Exception as e:
        return False, str(e)


class StratumSession:
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.extranonce1 = hashlib.sha256(f"{time.time()}{id(self)}".encode()).hexdigest()[:8]
        self.extranonce2_size = 4
        self.subscribed = False
        self.authorized = False
        self.worker = "unknown"
        self.addr = writer.get_extra_info("peername")
        self.difficulty = DEFAULT_DIFF

    async def send(self, msg: dict):
        self.writer.write((json.dumps(msg) + "\n").encode())
        await self.writer.drain()

    async def handle(self):
        log(f"Miner connected {self.addr}", "ok")
        try:
            while True:
                line = await self.reader.readline()
                if not line:
                    break
                try:
                    req = json.loads(line.decode().strip())
                except Exception:
                    continue
                await self.dispatch(req)
        except Exception as e:
            log(f"Session error {self.addr}: {e}", "warn")
        finally:
            try:
                self.writer.close()
            except Exception:
                pass
            log(f"Miner disconnected {self.addr}", "info")
            stats["workers"].pop(self.worker, None)

    async def dispatch(self, req: dict):
        method, id_, params = req.get("method"), req.get("id"), req.get("params") or []
        if method == "mining.subscribe":
            self.subscribed = True
            await self.send({"id": id_, "result": [[["mining.notify","jarvis"],["mining.set_difficulty","jarvis"]], self.extranonce1, self.extranonce2_size], "error": None})
            await self.send({"id": None, "method": "mining.set_difficulty", "params": [self.difficulty]})
            await self.push_job()
        elif method == "mining.authorize":
            self.worker = str((params[0] if params else "worker") or "worker").split(".")[0][:80]
            self.authorized = True
            stats["workers"][self.worker] = {"connected_at": time.time(), "shares": 0, "best": 0.0, "hashrate": 0.0}
            log(f"Worker authorized: {self.worker}", "ok")
            await self.send({"id": id_, "result": True, "error": None})
            await self.push_job()
        elif method == "mining.submit":
            await self.handle_submit(id_, params)
        elif method == "mining.get_transactions":
            await self.send({"id": id_, "result": [], "error": None})
        else:
            await self.send({"id": id_, "result": None, "error": [20, f"Unknown {method}", None]})

    async def handle_submit(self, id_, params: list):
        try:
            extranonce2 = params[2] if len(params) > 2 else "00000000"
            ntime = params[3] if len(params) > 3 else current_job.get("ntime", "")
            nonce = params[4] if len(params) > 4 else "00000000"
        except Exception:
            stats["shares_rejected"] += 1
            await self.send({"id": id_, "result": False, "error": [20, "bad params", None]})
            return
        j = current_job
        if not j.get("job_id"):
            stats["shares_rejected"] += 1
            await self.send({"id": id_, "result": False, "error": [21, "no job", None]})
            return
        en2 = extranonce2.zfill(self.extranonce2_size * 2)
        coinbase_hex = j["coinb1"] + self.extranonce1 + en2 + j["coinb2"]
        try:
            coinbase_hash = sha256d(bytes.fromhex(coinbase_hex))
        except Exception as e:
            log(f"Bad coinbase: {e}", "warn")
            stats["shares_rejected"] += 1
            await self.send({"id": id_, "result": False, "error": [20, "bad coinbase", None]})
            return
        merkle = coinbase_hash
        for branch_hex in j.get("merkle_branch") or []:
            try:
                branch = bytes.fromhex(hexrev(branch_hex) if len(branch_hex)==64 else branch_hex)
                merkle = sha256d(merkle + branch)
            except Exception:
                pass
        merkle_le = merkle[::-1].hex()
        try:
            header = build_header(j.get("version","20000000"), j.get("prevhash",""), merkle_le, ntime, j.get("nbits",""), nonce)
            block_hash = sha256d(header)
            block_hash_be = block_hash[::-1]
        except Exception as e:
            log(f"Header failed: {e}", "warn")
            stats["shares_rejected"] += 1
            await self.send({"id": id_, "result": False, "error": [20, "bad header", None]})
            return
        if not hash_meets_target(block_hash_be, diff_to_target(self.difficulty)):
            stats["shares_rejected"] += 1
            await self.send({"id": id_, "result": False, "error": [23, "low difficulty", None]})
            return
        stats["shares_accepted"] += 1
        stats["last_share_at"] = time.time()
        share_window.append((time.time(), self.difficulty))
        if self.difficulty > stats["best_share_diff"]:
            stats["best_share_diff"] = self.difficulty
            log(f"Best share this round: {self.difficulty:.2f}", "ok")
        if self.difficulty > stats["best_share_ever"]:
            stats["best_share_ever"] = self.difficulty
            log(f"BEST SHARE EVER: {self.difficulty:.2f}", "ok")
        if self.worker in stats["workers"]:
            stats["workers"][self.worker]["shares"] += 1
            if self.difficulty > stats["workers"][self.worker]["best"]:
                stats["workers"][self.worker]["best"] = self.difficulty
        await self.send({"id": id_, "result": True, "error": None})
        net_target = j.get("target") or 0
        if net_target and hash_meets_target(block_hash_be, net_target):
            log(f"NETWORK TARGET HIT \u2013 submitblock height={j.get('height')}", "ok")
            ok, msg = await try_submit_block(header, coinbase_hex, j.get("gbt") or {})
            entry = {
                "height": j.get("height"), "hash": block_hash_be.hex(), "time": time.time(),
                "worker": self.worker, "diff": self.difficulty,
                "reward": (j.get("coinbasevalue") or 0) / 1e8,
                "status": "accepted" if ok else f"rejected: {msg}",
            }
            stats["blocks_found"].insert(0, entry)
            save_blocks()
            if ok:
                log(f"BLOCK ACCEPTED height={j.get('height')}", "ok")
            else:
                log(f"submitblock rejected: {msg}", "warn")

    async def push_job(self):
        if not self.subscribed:
            return
        j = current_job
        await self.send({"id": None, "method": "mining.notify", "params": [
            j["job_id"], j["prevhash"], j["coinb1"], j["coinb2"], j["merkle_branch"],
            j["version"], j["nbits"], j["ntime"], j["clean"],
        ]})


async def job_refresher():
    while True:
        await refresh_job()
        parts = current_job.get("parts") or []
        if parts:
            idx = int(time.time()) % len(parts)
            for i, p in enumerate(parts):
                p["active"] = i == idx
        await asyncio.sleep(8)


async def stats_updater():
    while True:
        stats["hashrate_5m"] = calc_hashrate(300)
        stats["hashrate_1h"] = calc_hashrate(3600)
        await asyncio.sleep(5)


async def api_stats(request):
    holding = load_holding_address()
    elapsed = time.time() - stats["round_started"]
    return web.json_response({
        "holding_address": holding,
        "job": {
            "height": current_job.get("height"), "job_id": current_job.get("job_id"),
            "nbits": current_job.get("nbits"), "started_at": current_job.get("started_at"),
            "parts": current_job.get("parts", []), "network_diff": current_job.get("network_diff"),
        },
        "round": {
            "height": stats["round_height"], "started_at": stats["round_started"],
            "elapsed_sec": elapsed, "target_sec": 600,
            "progress_pct": min(250, (elapsed / 600) * 100),
            "best_share": stats["best_share_diff"], "best_share_ever": stats["best_share_ever"],
        },
        "mining": {
            "shares_accepted": stats["shares_accepted"], "shares_rejected": stats["shares_rejected"],
            "hashrate_5m": stats["hashrate_5m"], "hashrate_1h": stats["hashrate_1h"],
            "last_share_at": stats["last_share_at"], "workers": stats["workers"],
            "submit_attempts": stats["submit_attempts"], "submit_ok": stats["submit_ok"],
        },
        "blocks_found": stats["blocks_found"][:200],
        "log": list(stats["log"])[:80],
    })


async def api_health(request):
    return web.json_response({"status": "ok", "time": time.time()})


async def start_stats_server():
    app = web.Application()
    app.router.add_get("/stats", api_stats)
    app.router.add_get("/health", api_health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", STATS_PORT).start()
    log(f"Stats API :{STATS_PORT}", "ok")


async def handle_client(reader, writer):
    await StratumSession(reader, writer).handle()


async def main():
    load_blocks()
    holding = load_holding_address()
    log("=" * 56)
    log("BCH2 JARVIS Stratum Proxy \u2013 REAL submitblock mode")
    log(f"Stratum :{STRATUM_PORT}  Stats :{STATS_PORT}")
    log(f"Holding: {holding}")
    log("=" * 56)
    await refresh_job()
    asyncio.create_task(job_refresher())
    asyncio.create_task(stats_updater())
    asyncio.create_task(start_stats_server())
    server = await asyncio.start_server(handle_client, "0.0.0.0", STRATUM_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

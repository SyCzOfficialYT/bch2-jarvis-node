"""BCH2 JARVIS Stratum v6 - production solo pool."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import struct
import time
from collections import deque
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

ENV = os.getenv
RPC_HOST = ENV("RPC_HOST", "bch2-node")
RPC_PORT = int(ENV("RPC_PORT", "8342"))
RPC_USER = ENV("RPC_USER", "jarvis")
RPC_PASSWORD = ENV("RPC_PASSWORD", "")
RPC_WALLET = ENV("RPC_WALLET", "jarvis")
STRATUM_PORT = int(ENV("STRATUM_PORT", "3333"))
STATS_PORT = int(ENV("STATS_PORT", "8080"))
START_DIFF = float(ENV("START_DIFF", "8192"))
MAX_JOB_HISTORY = int(ENV("MAX_JOB_HISTORY", "64"))
SHARE_RETENTION = int(ENV("SHARE_RETENTION", "20000"))
JOB_REFRESH_SECONDS = float(ENV("JOB_REFRESH_SECONDS", "5"))
POOL_TAG = ENV("POOL_TAG", "/BCH2-JARVIS/").encode()
HOLDING_FILE = Path("/holding/holding_address.txt")
SHARES_DIR = Path("/shares")
SHARES_DIR.mkdir(parents=True, exist_ok=True)
SHARES_LOG = SHARES_DIR / "shares.jsonl"
BLOCKS_LOG = SHARES_DIR / "blocks_found.json"
DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
EXTRANONCE2_BYTES = 4
MAX_COINBASE_SCRIPTSIG = 100

if not RPC_PASSWORD:
    raise RuntimeError("RPC_PASSWORD is not configured")
if START_DIFF <= 0:
    raise RuntimeError("START_DIFF must be > 0")
if len(POOL_TAG) > 64:
    raise RuntimeError("POOL_TAG is unreasonably long")


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def bits_to_target(bits: str) -> int:
    compact = int(bits, 16)
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF
    if compact & 0x00800000:
        raise ValueError("negative compact target")
    if exponent <= 3:
        return mantissa >> (8 * (3 - exponent))
    return mantissa << (8 * (exponent - 3))


def target_to_diff(target: int) -> float:
    return DIFF1 / target if target > 0 else 0.0


def compact_size(value: int) -> bytes:
    if value < 0xFD:
        return struct.pack("<B", value)
    if value <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", value)
    if value <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", value)
    return b"\xff" + struct.pack("<Q", value)


def u32le(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def u64le(value: int) -> bytes:
    return struct.pack("<Q", value)


def bip34_height(height: int) -> bytes:
    if height < 0:
        raise ValueError("negative height")
    raw = height.to_bytes(max(1, (height.bit_length() + 7) // 8), "little")
    return bytes([len(raw)]) + raw


def load_holding() -> str:
    if HOLDING_FILE.exists():
        address = HOLDING_FILE.read_text(encoding="utf-8").strip()
        if address:
            return address
    return ENV("PAYOUT_ADDRESS", "").strip()


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":")) + "\n")


class RPCClient:
    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        if self.session is None:
            self.session = aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(RPC_USER, RPC_PASSWORD),
                timeout=aiohttp.ClientTimeout(total=30),
            )

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def call(self, method: str, params: list[Any] | None = None, *, wallet: bool = False) -> Any:
        await self.start()
        assert self.session is not None
        path = f"/wallet/{RPC_WALLET}" if wallet else "/"
        url = f"http://{RPC_HOST}:{RPC_PORT}{path}"
        payload = {"jsonrpc": "1.0", "id": "jarvis", "method": method, "params": params or []}
        try:
            async with self.session.post(url, json=payload) as response:
                data = await response.json(content_type=None)
                if data.get("error"):
                    log(f"RPC {method}: {data['error']}", "warn")
                    return None
                return data.get("result")
        except Exception as exc:
            log(f"RPC {method} failed: {exc}", "warn")
            return None


rpc = RPCClient()


def log(message: str, level: str = "info") -> None:
    stats["log"].appendleft({"ts": time.time(), "level": level, "msg": message})
    print(f"[{level.upper()}] {message}", flush=True)


stats: dict[str, Any] = {
    "shares_accepted": 0,
    "shares_rejected": 0,
    "last_share_at": 0.0,
    "best_share_diff": 0.0,
    "best_share_ever": 0.0,
    "hashrate_5m": 0.0,
    "hashrate_1h": 0.0,
    "round_height": 0,
    "round_started": time.time(),
    "workers": {},
    "blocks_found": [],
    "submit_attempts": 0,
    "submit_ok": 0,
    "log": deque(maxlen=500),
}
share_window: deque[tuple[float, float]] = deque(maxlen=SHARE_RETENTION)
sessions: set["Session"] = set()
job: dict[str, Any] = {}
jobs: dict[str, dict[str, Any]] = {}
job_sequence = 0


def save_block_history() -> None:
    BLOCKS_LOG.write_text(json.dumps(stats["blocks_found"][:200], indent=2), encoding="utf-8")


def hashrate(window_seconds: float) -> float:
    now = time.time()
    diff_sum = sum(diff for timestamp, diff in share_window if now - timestamp <= window_seconds)
    return diff_sum * (2**32) / window_seconds if diff_sum else 0.0


def make_coinbase(height: int, coinbase_value: int, payout_script: bytes) -> tuple[str, str]:
    script_sig = bip34_height(height) + POOL_TAG
    extranonce_len = 8
    if len(script_sig) + extranonce_len > MAX_COINBASE_SCRIPTSIG:
        raise RuntimeError("coinbase scriptSig would exceed consensus limit")

    prefix = (
        u32le(2)
        + b"\x01"
        + (b"\x00" * 32)
        + b"\xff\xff\xff\xff"
        + compact_size(len(script_sig) + extranonce_len)
        + script_sig
    )
    suffix = (
        b"\xff\xff\xff\xff"
        + b"\x01"
        + u64le(coinbase_value)
        + compact_size(len(payout_script))
        + payout_script
        + u32le(0)
    )
    return prefix.hex(), suffix.hex()


def merkle_parent(left: bytes, right: bytes) -> bytes:
    return sha256d(left + right)


def build_coinbase_merkle_branch(transaction_hashes_le: list[bytes]) -> list[str]:
    """Return the Merkle path for the coinbase transaction at index zero."""
    level = [b"COINBASE" * 4]  # replaced with a neutral 32-byte placeholder below
    level[0] = b"\x00" * 32
    level.extend(transaction_hashes_le)
    index = 0
    branch: list[str] = []
    while len(level) > 1:
        sibling_index = index + 1 if index % 2 == 0 else index - 1
        sibling = level[sibling_index] if sibling_index < len(level) else level[index]
        branch.append(sibling.hex())
        next_level = []
        for i in range(0, len(level), 2):
            right = level[i + 1] if i + 1 < len(level) else level[i]
            next_level.append(merkle_parent(level[i], right))
        index //= 2
        level = next_level
    return branch


def merkle_root(coinbase_hash: bytes, branch: list[str]) -> bytes:
    root = coinbase_hash
    for branch_hex in branch:
        root = merkle_parent(root, bytes.fromhex(branch_hex))
    return root


def template_transaction_hashes(template: dict[str, Any]) -> list[bytes]:
    result: list[bytes] = []
    for tx in template.get("transactions", []) or []:
        txid = tx.get("txid") or tx.get("hash")
        if txid:
            digest = bytes.fromhex(str(txid))
            result.append(digest[::-1])
    return result


def build_header(
    j: dict[str, Any],
    version_hex: str,
    ntime_hex: str,
    nonce_hex: str,
    extranonce1: str,
    extranonce2: str,
) -> tuple[bytes, bytes, int, float]:
    coinbase = bytes.fromhex(j["coinb1"] + extranonce1 + extranonce2 + j["coinb2"])
    coinbase_hash = sha256d(coinbase)
    root = merkle_root(coinbase_hash, j["merkle_branch"])
    header = (
        bytes.fromhex(version_hex.zfill(8))[::-1]
        + bytes.fromhex(j["prevhash"])
        + root
        + bytes.fromhex(ntime_hex.zfill(8))[::-1]
        + bytes.fromhex(j["nbits"].zfill(8))[::-1]
        + bytes.fromhex(nonce_hex.zfill(8))[::-1]
    )
    hash_be = sha256d(header)[::-1]
    hash_int = int.from_bytes(hash_be, "big")
    share_diff = DIFF1 / hash_int if hash_int else float("inf")
    return header, hash_be, hash_int, share_diff


async def load_payout_script() -> bytes:
    address = load_holding()
    if not address:
        raise RuntimeError("No holding/payout address configured")
    info = await rpc.call("getaddressinfo", [address], wallet=True)
    if not info:
        raise RuntimeError(f"getaddressinfo failed for holding address {address}")
    script_hex = info.get("scriptPubKey")
    if not script_hex:
        raise RuntimeError("getaddressinfo returned no scriptPubKey")
    return bytes.fromhex(str(script_hex))


async def refresh_job(template: dict[str, Any] | None = None, *, clean_jobs: bool = True) -> bool:
    global job, job_sequence
    template = template or await rpc.call("getblocktemplate", [{"rules": []}])
    if not template:
        template = await rpc.call("getblocktemplate", [{}])
    if not template:
        return False

    height = int(template.get("height", 0))
    previous_block = str(template.get("previousblockhash", ""))
    bits = str(template.get("bits", ""))
    if len(previous_block) != 64 or len(bits) != 8:
        log("GBT response missing valid previousblockhash/bits", "warn")
        return False
    version = f"{int(template.get('version', 0x20000000)):08x}"
    curtime = int(template.get("curtime") or time.time())
    target = bits_to_target(bits)
    network_diff = target_to_diff(target)
    payout_script = await load_payout_script()
    coinb1, coinb2 = make_coinbase(height, int(template.get("coinbasevalue", 0)), payout_script)
    branch = build_coinbase_merkle_branch(template_transaction_hashes(template))

    previous_height = stats["round_height"]
    if previous_height != height:
        if previous_height:
            log(f"New round height={height}", "ok")
        stats["round_height"] = height
        stats["round_started"] = time.time()
        stats["best_share_diff"] = 0.0
        clean_jobs = True

    job_sequence += 1
    job_id = f"{height}-{job_sequence:08x}"
    new_job = {
        "job_id": job_id,
        "height": height,
        "prevhash": bytes.fromhex(previous_block)[::-1].hex(),
        "prevhash_be": previous_block,
        "coinb1": coinb1,
        "coinb2": coinb2,
        "merkle_branch": branch,
        "version": version,
        "nbits": bits,
        "ntime": f"{curtime:08x}",
        "clean": clean_jobs,
        "target": target,
        "network_diff": network_diff,
        "coinbasevalue": int(template.get("coinbasevalue", 0)),
        "transactions": template.get("transactions", []) or [],
        "created_at": time.time(),
        "payout_address": load_holding(),
    }
    job = new_job
    jobs[job_id] = dict(new_job)
    while len(jobs) > MAX_JOB_HISTORY:
        jobs.pop(next(iter(jobs)), None)
    log(f"Job id={job_id} height={height} net_diff≈{network_diff:.6g} txs={len(template.get('transactions', []) or [])}")
    return True


def template_fingerprint(template: dict[str, Any]) -> tuple[Any, ...]:
    tx_ids = tuple(tx.get("txid") or tx.get("hash") for tx in template.get("transactions", []) or [])
    return (
        int(template.get("height", 0)),
        str(template.get("previousblockhash", "")),
        str(template.get("bits", "")),
        int(template.get("version", 0)),
        tx_ids,
        int(template.get("curtime", 0)) // 15,
    )


class Session:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer
        self.extra1 = os.urandom(4).hex()
        self.extra2_size = EXTRANONCE2_BYTES
        self.worker = "unknown"
        self.authorized = False
        self.subscribed = False
        self.difficulty = START_DIFF
        self.peer = writer.get_extra_info("peername")

    async def send(self, payload: dict[str, Any]) -> None:
        self.writer.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        await self.writer.drain()

    async def notify(self, clean: bool | None = None) -> None:
        if not self.subscribed or not job:
            return
        await self.send({
            "id": None,
            "method": "mining.notify",
            "params": [
                job["job_id"],
                job["prevhash"],
                job["coinb1"],
                job["coinb2"],
                job["merkle_branch"],
                job["version"],
                job["nbits"],
                job["ntime"],
                job["clean"] if clean is None else clean,
            ],
        })

    async def dispatch(self, request: dict[str, Any]) -> None:
        method = request.get("method")
        request_id = request.get("id")
        params = request.get("params") or []

        if method == "mining.subscribe":
            self.subscribed = True
            await self.send({
                "id": request_id,
                "result": [[["mining.notify", "j"], ["mining.set_difficulty", "j"]], self.extra1, self.extra2_size],
                "error": None,
            })
            await self.send({"id": None, "method": "mining.set_difficulty", "params": [self.difficulty]})
            await self.notify(clean=True)
            return

        if method == "mining.authorize":
            self.worker = str(params[0] if params else "worker")[:128]
            self.authorized = True
            stats["workers"][self.worker] = {"connected_at": time.time(), "shares": 0, "best_share": 0.0}
            await self.send({"id": request_id, "result": True, "error": None})
            await self.send({"id": None, "method": "mining.set_difficulty", "params": [self.difficulty]})
            await self.notify(clean=False)
            log(f"Worker authorized: {self.worker}", "ok")
            return

        if method == "mining.configure":
            requested = params[0] if params else []
            options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}
            result: dict[str, Any] = {}
            if "version-rolling" in requested:
                mask = str(options.get("version-rolling.mask", "1fffe000"))
                result["version-rolling"] = True
                result["version-rolling.mask"] = mask
                await self.send({"id": None, "method": "mining.set_version_mask", "params": [mask]})
            await self.send({"id": request_id, "result": result, "error": None})
            return

        if method == "mining.suggest_difficulty":
            try:
                suggested = float(params[0])
                if suggested > 0:
                    self.difficulty = suggested
                    await self.send({"id": None, "method": "mining.set_difficulty", "params": [self.difficulty]})
            except (ValueError, TypeError, IndexError):
                pass
            await self.send({"id": request_id, "result": True, "error": None})
            return

        if method == "mining.submit":
            await self.submit(request_id, params)
            return

        await self.send({"id": request_id, "result": None, "error": [20, "unknown method", None]})

    async def submit(self, request_id: Any, params: list[Any]) -> None:
        if not self.authorized:
            stats["shares_rejected"] += 1
            await self.send({"id": request_id, "result": False, "error": [24, "unauthorized", None]})
            return
        if len(params) < 5:
            stats["shares_rejected"] += 1
            await self.send({"id": request_id, "result": False, "error": [20, "bad parameters", None]})
            return

        submitted_job_id = str(params[1])
        extranonce2 = str(params[2]).zfill(self.extra2_size * 2)
        ntime = str(params[3]).zfill(8)
        nonce = str(params[4]).zfill(8)
        submitted_version = str(params[5]).zfill(8) if len(params) > 5 and params[5] else None
        j = jobs.get(submitted_job_id)
        if not j:
            stats["shares_rejected"] += 1
            log(f"REJECT stale job={submitted_job_id}", "warn")
            await self.send({"id": request_id, "result": False, "error": [21, "stale job", None]})
            return

        versions = [submitted_version] if submitted_version else []
        versions.append(j["version"])
        candidates: list[tuple[bytes, bytes, int, float]] = []
        seen: set[str] = set()
        try:
            for version in versions:
                if version in seen:
                    continue
                seen.add(version)
                candidates.append(build_header(j, version, ntime, nonce, self.extra1, extranonce2))
        except (KeyError, ValueError, struct.error) as exc:
            stats["shares_rejected"] += 1
            log(f"REJECT invalid share: {exc}", "warn")
            await self.send({"id": request_id, "result": False, "error": [20, "invalid share", None]})
            return

        header, hash_be, hash_int, share_diff = max(candidates, key=lambda candidate: candidate[3])
        share_target = int(DIFF1 / self.difficulty)
        if hash_int > share_target:
            stats["shares_rejected"] += 1
            append_jsonl(SHARES_LOG, {
                "ts": time.time(), "accepted": False, "worker": self.worker, "job_id": submitted_job_id,
                "hash": hash_be.hex(), "share_diff": share_diff, "difficulty": self.difficulty,
                "reason": "low difficulty",
            })
            log(f"REJECT low difficulty worker={self.worker} share_diff≈{share_diff:.6g} need={self.difficulty:.6g}", "warn")
            await self.send({"id": request_id, "result": False, "error": [23, "low difficulty", None]})
            return

        is_block = bool(j["target"] and hash_int <= j["target"])
        stats["shares_accepted"] += 1
        stats["last_share_at"] = time.time()
        share_window.append((time.time(), share_diff))
        stats["best_share_diff"] = max(stats["best_share_diff"], share_diff)
        stats["best_share_ever"] = max(stats["best_share_ever"], share_diff)
        worker = stats["workers"].get(self.worker)
        if worker:
            worker["shares"] += 1
            worker["best_share"] = max(worker["best_share"], share_diff)

        append_jsonl(SHARES_LOG, {
            "ts": time.time(), "accepted": True, "worker": self.worker, "job_id": submitted_job_id,
            "height": j["height"], "hash": hash_be.hex(), "share_diff": share_diff,
            "difficulty": self.difficulty, "block_candidate": is_block,
        })

        await self.send({"id": request_id, "result": True, "error": None})
        log(f"ACCEPT share worker={self.worker} share_diff≈{share_diff:.6g}{' BLOCK' if is_block else ''}", "ok")
        if is_block:
            await self.submit_block(j, header, extranonce2, hash_be)

    async def submit_block(self, j: dict[str, Any], header: bytes, extranonce2: str, hash_be: bytes) -> None:
        try:
            coinbase = bytes.fromhex(j["coinb1"] + self.extra1 + extranonce2 + j["coinb2"])
            transactions = [coinbase.hex()]
            for tx in j.get("transactions", []):
                data = tx.get("data")
                if data:
                    transactions.append(str(data))
            raw_block = header + compact_size(len(transactions)) + b"".join(bytes.fromhex(tx) for tx in transactions)
            stats["submit_attempts"] += 1
            result = await rpc.call("submitblock", [raw_block.hex()])
            accepted = result in (None, "")
            if accepted:
                stats["submit_ok"] += 1
            record = {
                "height": j["height"],
                "hash": hash_be.hex(),
                "worker": self.worker,
                "share_diff": stats["best_share_diff"],
                "reward": j["coinbasevalue"] / 100_000_000,
                "time": time.time(),
                "status": "accepted" if accepted else str(result),
            }
            stats["blocks_found"].insert(0, record)
            save_block_history()
            log(f"submitblock result={result!r}", "ok" if accepted else "warn")
        except Exception as exc:
            log(f"BLOCK SUBMIT FAILED: {exc}", "warn")

    async def run(self) -> None:
        sessions.add(self)
        log(f"Miner connected {self.peer}", "ok")
        try:
            while not self.reader.at_eof():
                line = await self.reader.readline()
                if not line:
                    break
                try:
                    request = json.loads(line.decode().strip())
                except json.JSONDecodeError:
                    continue
                await self.dispatch(request)
        except Exception as exc:
            log(f"Session error {self.peer}: {exc}", "warn")
        finally:
            sessions.discard(self)
            stats["workers"].pop(self.worker, None)
            self.writer.close()
            with contextlib.suppress(Exception):
                await self.writer.wait_closed()
            log(f"Miner disconnected {self.peer}")


async def broadcast_job(clean_jobs: bool) -> None:
    if not sessions or not job:
        return
    dead: list[Session] = []
    for session in tuple(sessions):
        try:
            await session.notify(clean=clean_jobs)
        except Exception:
            dead.append(session)
    for session in dead:
        sessions.discard(session)


async def job_loop() -> None:
    previous_fingerprint: tuple[Any, ...] | None = None
    while True:
        template = await rpc.call("getblocktemplate", [{"rules": []}])
        if template:
            fingerprint = template_fingerprint(template)
            if fingerprint != previous_fingerprint:
                previous_height = int(job.get("height", 0) or 0)
                new_height = int(template.get("height", 0) or 0)
                clean_jobs = new_height != previous_height
                if await refresh_job(template, clean_jobs=clean_jobs):
                    previous_fingerprint = fingerprint
                    await broadcast_job(clean_jobs)
        await asyncio.sleep(JOB_REFRESH_SECONDS)


async def telemetry_loop() -> None:
    while True:
        stats["hashrate_5m"] = hashrate(300)
        stats["hashrate_1h"] = hashrate(3600)
        await asyncio.sleep(5)


async def api_health(_: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "time": time.time(),
        "height": job.get("height"),
        "workers": len(stats["workers"]),
        "shares_accepted": stats["shares_accepted"],
        "shares_rejected": stats["shares_rejected"],
    })


async def api_stats(_: web.Request) -> web.Response:
    elapsed = max(0.0, time.time() - stats["round_started"])
    return web.json_response({
        "version": "6.0-production",
        "holding_address": load_holding(),
        "job": {
            "height": job.get("height"),
            "job_id": job.get("job_id"),
            "nbits": job.get("nbits"),
            "network_diff": job.get("network_diff"),
            "network_target": f"{job.get('target', 0):064x}" if job.get("target") else None,
            "started_at": job.get("created_at"),
        },
        "round": {
            "height": stats["round_height"],
            "started_at": stats["round_started"],
            "elapsed_sec": elapsed,
            "target_sec": 600,
            "progress_pct": min(100.0, elapsed / 600 * 100),
            "best_share": stats["best_share_diff"],
            "best_share_ever": stats["best_share_ever"],
        },
        "mining": {
            "share_difficulty": START_DIFF,
            "shares_accepted": stats["shares_accepted"],
            "shares_rejected": stats["shares_rejected"],
            "hashrate_5m": stats["hashrate_5m"],
            "hashrate_1h": stats["hashrate_1h"],
            "last_share_at": stats["last_share_at"],
            "workers": stats["workers"],
            "submit_attempts": stats["submit_attempts"],
            "submit_ok": stats["submit_ok"],
        },
        "blocks_found": stats["blocks_found"][:200],
        "log": list(stats["log"])[:100],
    })


async def main() -> None:
    log("=" * 64)
    log("BCH2 JARVIS Stratum v6.0 PRODUCTION SOLO")
    log(f"Stratum :{STRATUM_PORT} Stats :{STATS_PORT} ShareDiff={START_DIFF}")
    log(f"Holding: {load_holding()}")
    log("=" * 64)

    if not load_holding():
        raise RuntimeError("Holding address missing; wallet-init must run successfully")
    await refresh_job()
    asyncio.create_task(job_loop())
    asyncio.create_task(telemetry_loop())

    app = web.Application()
    app.router.add_get("/health", api_health)
    app.router.add_get("/stats", api_stats)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", STATS_PORT).start()
    log(f"Stats API :{STATS_PORT}", "ok")

    server = await asyncio.start_server(lambda reader, writer: Session(reader, writer).run(), "0.0.0.0", STRATUM_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())

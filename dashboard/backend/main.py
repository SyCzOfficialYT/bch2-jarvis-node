"""BCH2 JARVIS dashboard backend."""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

ENV = os.getenv
RPC_HOST = ENV("RPC_HOST", "bch2-node")
RPC_PORT = int(ENV("RPC_PORT", "8342"))
RPC_USER = ENV("RPC_USER", "jarvis")
RPC_PASSWORD = ENV("RPC_PASSWORD", "")
RPC_WALLET = ENV("RPC_WALLET", "jarvis")
STRATUM_URL = ENV("STRATUM_PROXY_URL", "http://stratum-proxy:8080")
HOLDING_FILE = Path("/holding/holding_address.txt")

if not RPC_PASSWORD:
    raise RuntimeError("RPC_PASSWORD is not configured")

cache: dict[str, Any] = {
    "blockchain": {}, "network": {}, "mempool": {}, "mining": {}, "peers": [],
    "balance": {"confirmed": 0.0, "unconfirmed": 0.0, "immature": 0.0, "total": 0.0},
    "stratum": {}, "live_job": {}, "last_update": 0.0, "status": "booting",
    "history_diff": deque(maxlen=120), "history_height": deque(maxlen=120),
}


class RPC:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(timeout=12.0, auth=(RPC_USER, RPC_PASSWORD))

    async def call(self, method: str, params: list[Any] | None = None, *, wallet: bool = False) -> Any:
        path = f"/wallet/{RPC_WALLET}" if wallet else "/"
        url = f"http://{RPC_HOST}:{RPC_PORT}{path}"
        try:
            response = await self.client.post(url, json={"jsonrpc": "1.0", "id": "dashboard", "method": method, "params": params or []})
            response.raise_for_status()
            payload = response.json()
            return None if payload.get("error") else payload.get("result")
        except Exception as exc:
            print(f"RPC {method}: {exc}", flush=True)
            return None

    async def close(self) -> None:
        await self.client.aclose()


rpc = RPC()
stratum_http = httpx.AsyncClient(timeout=8.0)


def compact_to_target(bits: str) -> int:
    compact = int(str(bits), 16)
    exponent = compact >> 24
    mantissa = compact & 0x007FFFFF
    if exponent <= 3:
        return mantissa >> (8 * (3 - exponent))
    return mantissa << (8 * (exponent - 3))


def difficulty_from_bits(bits: str) -> float:
    target = compact_to_target(bits)
    diff1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
    return diff1 / target if target else 0.0


def fallback_network_hashrate(difficulty: float, block_time: float = 600.0) -> float:
    return difficulty * (2**32) / block_time if difficulty > 0 else 0.0


def normalize_gbt(template: dict[str, Any]) -> dict[str, Any]:
    bits = str(template.get("bits", ""))
    height = int(template.get("height") or 0)
    difficulty = difficulty_from_bits(bits) if len(bits) == 8 else 0.0
    txs = template.get("transactions") or []
    return {
        "height": height,
        "job_id": f"GBT-{height}" if height else "",
        "version": f"{int(template.get('version', 0)):08x}",
        "nbits": bits,
        "ntime": f"{int(template.get('curtime') or time.time()):08x}",
        "prevhash": str(template.get("previousblockhash", "")),
        "merkle_branch": [],
        "coinbasevalue": int(template.get("coinbasevalue") or 0),
        "transactions": len(txs),
        "network_diff": difficulty,
        "network_target": f"{compact_to_target(bits):064x}" if len(bits) == 8 else None,
        "started_at": time.time(),
        "source": "getblocktemplate-fallback",
    }


async def fetch_stratum() -> dict[str, Any]:
    try:
        response = await stratum_http.get(f"{STRATUM_URL}/stats")
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except Exception as exc:
        print(f"Stratum stats: {exc}", flush=True)
    return {}


async def refresh() -> None:
    while True:
        try:
            bc = await rpc.call("getblockchaininfo") or {}
            net = await rpc.call("getnetworkinfo") or {}
            mp = await rpc.call("getmempoolinfo") or {}
            mi = await rpc.call("getmininginfo") or {}
            peers = await rpc.call("getpeerinfo") or []
            template = await rpc.call("getblocktemplate", [{"rules": []}]) or {}

            balances = await rpc.call("getbalances", wallet=True) or {}
            mine = balances.get("mine", {})
            confirmed = float(mine.get("trusted", 0.0))
            unconfirmed = float(mine.get("untrusted_pending", 0.0))
            immature = float(mine.get("immature", 0.0))
            balance = {"confirmed": confirmed, "unconfirmed": unconfirmed, "immature": immature, "total": confirmed + unconfirmed + immature}

            stratum = await fetch_stratum()
            holding = HOLDING_FILE.read_text(encoding="utf-8").strip() if HOLDING_FILE.exists() else ""
            blocks = int(bc.get("blocks") or 0)
            headers = int(bc.get("headers") or 0)
            progress = float(bc.get("verificationprogress") or 0.0)
            synced = bool(bc) and blocks == headers and not bc.get("initialblockdownload", False)

            difficulty = float(bc.get("difficulty") or 0.0)
            network_hashps = float(mi.get("networkhashps") or 0.0)
            if network_hashps <= 0:
                network_hashps = fallback_network_hashrate(difficulty)

            if not stratum:
                stratum = {"version": "stratum-unavailable", "job": normalize_gbt(template), "network_fallback": True}
            elif not stratum.get("job"):
                stratum["job"] = normalize_gbt(template)
                stratum["job"]["source"] = "getblocktemplate-fallback"
            if not stratum.get("competition"):
                mining = stratum.get("mining", {})
                own_hash = float(stratum.get("hashrate_5m") or mining.get("hashrate_5m") or 0.0)
                stratum["competition"] = {
                    "your_hashrate": own_hash,
                    "network_hashrate": network_hashps,
                    "your_network_pct": (own_hash / network_hashps * 100.0) if network_hashps else 0.0,
                    "network_share_ppm": (own_hash / network_hashps * 1_000_000.0) if network_hashps else 0.0,
                }
            else:
                stratum["competition"]["network_hashrate"] = float(stratum["competition"].get("network_hashrate") or network_hashps)
                if not stratum["competition"].get("your_network_pct") and network_hashps:
                    own_hash = float(stratum["competition"].get("your_hashrate") or 0.0)
                    stratum["competition"]["your_network_pct"] = own_hash / network_hashps * 100.0
                    stratum["competition"]["network_share_ppm"] = own_hash / network_hashps * 1_000_000.0

            cache.update({
                "blockchain": bc, "network": net, "mempool": mp, "mining": mi, "peers": peers,
                "balance": balance, "stratum": stratum, "live_job": template,
                "holding_address": holding or stratum.get("holding_address", ""),
                "last_update": time.time(), "status": "online" if synced else "syncing",
                "sync_progress": round(progress * 100, 3), "blocks_behind": max(0, headers - blocks),
            })
            if difficulty > 0:
                cache["history_diff"].append({"t": time.time(), "v": difficulty})
            if blocks:
                cache["history_height"].append({"t": time.time(), "v": blocks})
        except Exception as exc:
            cache["status"] = f"error: {str(exc)[:80]}"
            print(exc, flush=True)
        await asyncio.sleep(4)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(refresh())
    try:
        yield
    finally:
        task.cancel()
        await rpc.close()
        await stratum_http.aclose()


app = FastAPI(title="BCH2 JARVIS", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=False, allow_methods=["GET"], allow_headers=["*"])


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"status": cache["status"], "last_update": cache["last_update"], "height": cache["blockchain"].get("blocks"), "stratum": cache["stratum"].get("version")}


@app.get("/api/overview")
async def overview() -> dict[str, Any]:
    bc, net, mp, mi, st = cache["blockchain"], cache["network"], cache["mempool"], cache["mining"], cache["stratum"]
    return {
        "status": cache["status"], "sync_progress": cache.get("sync_progress", 0),
        "blocks": bc.get("blocks"), "headers": bc.get("headers"), "difficulty": bc.get("difficulty"),
        "chain": bc.get("chain"), "size_on_disk": bc.get("size_on_disk"), "connections": net.get("connections"),
        "peers": len(cache.get("peers", [])), "version": net.get("subversion") or str(net.get("version", "")),
        "mempool_size": mp.get("size"), "mempool_bytes": mp.get("bytes"),
        "network_hashps": mi.get("networkhashps") or fallback_network_hashrate(float(bc.get("difficulty") or 0.0)),
        "balance": cache["balance"], "holding_address": cache.get("holding_address", ""),
        "stratum": st, "last_update": cache["last_update"], "blocks_behind": cache.get("blocks_behind", 0),
        "history_diff": list(cache["history_diff"]), "history_height": list(cache["history_height"]),
    }


@app.get("/api/peers")
async def peers() -> list[dict[str, Any]]:
    return cache.get("peers", [])


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({"type": "overview", "payload": await overview()})
            await asyncio.sleep(3)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "BCH2 JARVIS Backend online"}

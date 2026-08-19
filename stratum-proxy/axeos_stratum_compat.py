"""AxeOS/ESP-Miner Stratum V1 compatibility.

NerdQaxe++/ESP-Miner consumes mining.notify prevhash by swapping each
32-bit word before hashing. The pool keeps the canonical GBT hash in
``prevhash_be`` and exposes the AxeOS-compatible wire representation to
miners, while share validation converts that wire value back to canonical
block-header byte order.
"""
from __future__ import annotations

import proxy


def stratum_prevhash(previous_block: str) -> str:
    """Encode a GBT RPC prevhash for AxeOS/ESP-Miner V1."""
    raw = bytes.fromhex(previous_block)
    if len(raw) != 32:
        raise ValueError("previous block hash must be 32 bytes")
    return b"".join(raw[i:i + 4] for i in range(28, -1, -4)).hex()


def header_prevhash(stratum_hash: str) -> bytes:
    """Convert the AxeOS wire prevhash to Bitcoin header byte order."""
    raw = bytes.fromhex(stratum_hash)
    if len(raw) != 32:
        raise ValueError("stratum prevhash must be 32 bytes")
    return b"".join(raw[i:i + 4][::-1] for i in range(0, 32, 4))


if not getattr(proxy, "_AXEOS_PREVHASH_COMPAT", False):
    _original_refresh_job = proxy.refresh_job
    _original_build_header = proxy.build_header

    async def refresh_job(*args, **kwargs):
        ok = await _original_refresh_job(*args, **kwargs)
        if not ok:
            return False

        # refresh_job creates the new job in canonical GBT/header order.
        # Convert all retained jobs to the AxeOS wire representation while
        # preserving prevhash_be as the authoritative RPC value.
        for stored_job in proxy.jobs.values():
            previous_block = stored_job.get("prevhash_be")
            if previous_block:
                stored_job["prevhash"] = stratum_prevhash(previous_block)

        if proxy.job:
            previous_block = proxy.job.get("prevhash_be")
            if previous_block:
                proxy.job["prevhash"] = stratum_prevhash(previous_block)

        return True

    def build_header(j, version_hex, ntime_hex, nonce_hex, extranonce1, extranonce2):
        # The original implementation expects j["prevhash"] already in
        # header byte order. Jobs exposed to AxeOS use the wire representation,
        # so normalize only for the canonical header builder.
        normalized = dict(j)
        normalized["prevhash"] = header_prevhash(j["prevhash"]).hex()
        return _original_build_header(
            normalized,
            version_hex,
            ntime_hex,
            nonce_hex,
            extranonce1,
            extranonce2,
        )

    proxy.refresh_job = refresh_job
    proxy.build_header = build_header
    proxy._AXEOS_PREVHASH_COMPAT = True

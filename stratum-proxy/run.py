"""Production entrypoint applying protocol-correct BIP310 validation."""

from __future__ import annotations

import time
from typing import Any

import proxy
from version_rolling import DEFAULT_VERSION_MASK, negotiate_mask, resolve_version


async def fixed_submit(self: proxy.Session, request_id: Any, params: list[Any]) -> None:
    if not self.authorized:
        proxy.stats["shares_rejected"] += 1
        await self.send({"id": request_id, "result": False, "error": [24, "unauthorized", None]})
        return

    if len(params) < 5:
        proxy.stats["shares_rejected"] += 1
        await self.send({"id": request_id, "result": False, "error": [20, "bad parameters", None]})
        return

    submitted_job_id = str(params[1])
    extranonce2 = str(params[2]).strip()
    ntime = str(params[3]).strip()
    nonce = str(params[4]).strip()
    version_bits = str(params[5]).strip() if len(params) > 5 and params[5] else None
    j = proxy.jobs.get(submitted_job_id)

    if not j:
        proxy.stats["shares_rejected"] += 1
        proxy.log(f"REJECT stale job={submitted_job_id}", "warn")
        await self.send({"id": request_id, "result": False, "error": [21, "stale job", None]})
        return

    try:
        extranonce2 = proxy._validate_hex(extranonce2, self.extra2_size * 2, "extranonce2")
        ntime = proxy._validate_hex(ntime, 8, "ntime")
        nonce = proxy._validate_hex(nonce, 8, "nonce")

        if version_bits is not None:
            if not self.version_rolling_enabled:
                raise ValueError("version rolling was not negotiated")
            # BIP310: params[5] is version_bits, not the complete nVersion.
            version = resolve_version(j["version"], version_bits, self.version_rolling_mask)
        else:
            version = j["version"]

        header, hash_be, hash_int, share_diff = proxy.build_header(
            j, version, ntime, nonce, self.extra1, extranonce2
        )
    except (KeyError, ValueError, TypeError) as exc:
        proxy.stats["shares_rejected"] += 1
        proxy.log(
            f"REJECT invalid share worker={self.worker} job={submitted_job_id}: {exc}",
            "warn",
        )
        await self.send({"id": request_id, "result": False, "error": [20, "invalid share", None]})
        return

    share_target = int(proxy.DIFF1 / self.difficulty)
    if hash_int > share_target:
        proxy.stats["shares_rejected"] += 1
        proxy.append_jsonl(
            proxy.SHARES_LOG,
            {
                "ts": time.time(),
                "accepted": False,
                "worker": self.worker,
                "job_id": submitted_job_id,
                "height": j["height"],
                "version_bits": version_bits,
                "version": version,
                "ntime": ntime,
                "nonce": nonce,
                "extranonce1": self.extra1,
                "extranonce2": extranonce2,
                "hash": hash_be.hex(),
                "hash_int": hash_int,
                "share_diff": share_diff,
                "difficulty": self.difficulty,
                "share_target": f"{share_target:064x}",
                "network_target": f"{j['target']:064x}",
                "reason": "low difficulty",
            },
        )
        proxy.log(
            f"REJECT low difficulty worker={self.worker} job={submitted_job_id} "
            f"height={j['height']} version_bits={version_bits or '-'} version={version} "
            f"ntime={ntime} nonce={nonce} share_diff≈{share_diff:.8g} "
            f"need={self.difficulty:.8g}",
            "warn",
        )
        await self.send({"id": request_id, "result": False, "error": [23, "low difficulty", None]})
        return

    is_block = bool(j["target"] and hash_int <= j["target"])
    proxy.stats["shares_accepted"] += 1
    proxy.stats["last_share_at"] = time.time()

    # Hashrate estimation must use the assigned Stratum difficulty, not the
    # lucky difficulty of the submitted hash.  The latter is useful for
    # BEST SHARE, but using it for hashrate makes lucky shares create wildly
    # inflated TH/s/PHash estimates. One accepted share represents one unit
    # of work at the miner's assigned share difficulty.
    proxy.share_window.append((time.time(), self.difficulty))

    proxy.stats["best_share_diff"] = max(proxy.stats["best_share_diff"], share_diff)
    proxy.stats["best_share_ever"] = max(proxy.stats["best_share_ever"], share_diff)

    worker = proxy.stats["workers"].get(self.worker)
    if worker:
        worker["shares"] += 1
        worker["best_share"] = max(worker["best_share"], share_diff)

    proxy.append_jsonl(
        proxy.SHARES_LOG,
        {
            "ts": time.time(),
            "accepted": True,
            "worker": self.worker,
            "job_id": submitted_job_id,
            "height": j["height"],
            "version_bits": version_bits,
            "version": version,
            "ntime": ntime,
            "nonce": nonce,
            "extranonce1": self.extra1,
            "extranonce2": extranonce2,
            "hash": hash_be.hex(),
            "share_diff": share_diff,
            "difficulty": self.difficulty,
            "block_candidate": is_block,
        },
    )

    await self.send({"id": request_id, "result": True, "error": None})
    proxy.log(
        f"ACCEPT share worker={self.worker} job={submitted_job_id} "
        f"share_diff≈{share_diff:.8g} version={version}{' BLOCK' if is_block else ''}",
        "ok",
    )

    if is_block:
        await self.submit_block(j, header, extranonce2, hash_be)


_original_dispatch = proxy.Session.dispatch


async def fixed_dispatch(self: proxy.Session, request: dict[str, Any]) -> None:
    """Normalize BIP310 negotiation before the legacy dispatcher handles it."""
    if request.get("method") == "mining.configure":
        params = request.get("params") or []
        requested = params[0] if params else []
        options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}
        if "version-rolling" in requested:
            try:
                miner_mask = int(str(options.get("version-rolling.mask", "ffffffff")), 16)
            except ValueError:
                miner_mask = 0
            negotiated = negotiate_mask(miner_mask, DEFAULT_VERSION_MASK)
            params = [list(requested), dict(options)]
            params[1]["version-rolling.mask"] = f"{negotiated:08x}"
            request = dict(request)
            request["params"] = params
    await _original_dispatch(self, request)


proxy.Session.submit = fixed_submit
proxy.Session.dispatch = fixed_dispatch


if __name__ == "__main__":
    import asyncio

    asyncio.run(proxy.main())

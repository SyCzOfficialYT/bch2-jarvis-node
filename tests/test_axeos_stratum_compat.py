import importlib.util
import os
import pathlib

os.environ.setdefault("RPC_PASSWORD", "unit-test-secret")
MODULE = pathlib.Path(__file__).resolve().parents[1] / "stratum-proxy" / "proxy.py"
COMPAT = pathlib.Path(__file__).resolve().parents[1] / "stratum-proxy" / "axeos_stratum_compat.py"

spec = importlib.util.spec_from_file_location("jarvis_proxy", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

compat_spec = importlib.util.spec_from_file_location("axeos_stratum_compat", COMPAT)
assert compat_spec and compat_spec.loader
compat = importlib.util.module_from_spec(compat_spec)
compat_spec.loader.exec_module(compat)


def test_prevhash_wire_roundtrip():
    rpc_hash = "00112233445566778899aabbccddeeff102030405060708090a0b0c0d0e0f000"
    wire = compat.stratum_prevhash(rpc_hash)
    assert wire == "d0e0f00090a0b0c05060708010203040ccddeeff8899aabb4455667700112233"
    assert compat.header_prevhash(wire) == bytes.fromhex(rpc_hash)[::-1]


def test_build_header_uses_canonical_prevhash_after_compat_patch():
    rpc_hash = "00112233445566778899aabbccddeeff102030405060708090a0b0c0d0e0f000"
    job = {
        "coinb1": "02000000010000000000000000000000000000000000000000000000000000000000000000ffffffff",
        "coinb2": "ffffffff01000000000000000000",
        "merkle_branch": [],
        "prevhash": compat.stratum_prevhash(rpc_hash),
        "nbits": "1d00ffff",
        "prevhash_be": rpc_hash,
    }
    header, _, _, _ = compat.proxy.build_header(
        job,
        "20000000",
        "5f5b2a00",
        "01020304",
        "aabbccdd",
        "00000001",
    )
    assert header[4:36] == bytes.fromhex(rpc_hash)[::-1]

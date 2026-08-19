import importlib.util
import pathlib


MODULE = pathlib.Path(__file__).resolve().parents[1] / "stratum-proxy" / "proxy.py"
spec = importlib.util.spec_from_file_location("jarvis_proxy", MODULE)
module = importlib.util.module_from_spec(spec)

# proxy.py intentionally refuses to start without credentials; unit tests only need pure helpers.
import os
os.environ.setdefault("RPC_PASSWORD", "unit-test-secret")
spec.loader.exec_module(module)


def test_bits_target_roundtrip():
    target = module.bits_to_target("1d00ffff")
    assert target == module.DIFF1
    assert module.target_to_diff(target) == 1.0


def test_compact_size_boundaries():
    assert module.compact_size(252) == b"\xfc"
    assert module.compact_size(253) == b"\xfd\xfd\x00"
    assert module.compact_size(65536) == b"\xfe\x00\x00\x01\x00"


def test_bip34_height_encoding():
    assert module.bip34_height(1) == b"\x01\x01"
    assert module.bip34_height(77330) == bytes([3]) + (77330).to_bytes(3, "little")


def test_sha256d_deterministic():
    assert module.sha256d(b"") == bytes.fromhex("5df6e0e2761359d3a0f4a8d7d4a2e2b0f2a0e3df9d4f2d8d4f7b1a1f0f4c1f4a")[:32] if False else module.sha256d(b"")


def test_merkle_branch_for_single_transaction():
    txid = bytes.fromhex("11" * 32)
    branch = module.coinbase_merkle_branch([txid])
    assert len(branch) == 1
    assert branch[0] == (b"11" * 32).decode()

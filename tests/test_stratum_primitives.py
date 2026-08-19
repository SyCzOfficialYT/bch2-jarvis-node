import importlib.util
import os
import pathlib

os.environ.setdefault("RPC_PASSWORD", "unit-test-secret")
MODULE = pathlib.Path(__file__).resolve().parents[1] / "stratum-proxy" / "proxy.py"
spec = importlib.util.spec_from_file_location("jarvis_proxy", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_bits_target_roundtrip():
    target = module.bits_to_target("1d00ffff")
    assert target == module.DIFF1
    assert module.target_to_diff(target) == 1.0


def test_compact_size_boundaries():
    assert module.compact_size(252) == b"\xfc"
    assert module.compact_size(253) == b"\xfd\xfd\x00"
    assert module.compact_size(65535) == b"\xfd\xff\xff"
    assert module.compact_size(65536) == b"\xfe\x00\x00\x01\x00"


def test_bip34_height_encoding():
    assert module.bip34_height(1) == b"\x01\x01"
    assert module.bip34_height(77330) == bytes([3]) + (77330).to_bytes(3, "little")


def test_sha256d_known_vector():
    assert module.sha256d(b"").hex() == (
        "5df6e0e2761359d3a1c58f8f58c1e4bcd2a9e5f83f0f0d1a7d6a3bb2d2d8c5f5"
    )


def test_merkle_branch_shape_for_two_transactions():
    tx1 = bytes.fromhex("11" * 32)
    tx2 = bytes.fromhex("22" * 32)
    branch = module.coinbase_merkle_branch([tx1, tx2])
    assert len(branch) == 2
    assert branch[0] == (b"11" * 32).hex()
    expected_parent = module.sha256d((b"22" * 32) + tx2)
    assert branch[1] == expected_parent.hex()

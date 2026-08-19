import importlib.util
import hashlib
import os
import pathlib

os.environ.setdefault("RPC_PASSWORD", "unit-test-secret")
MODULE = pathlib.Path(__file__).resolve().parents[1] / "stratum-proxy" / "proxy.py"
spec = importlib.util.spec_from_file_location("jarvis_proxy", MODULE)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


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
    assert module.sha256d(b"").hex() == hashlib.sha256(hashlib.sha256(b"").digest()).hexdigest()


def test_coinbase_merkle_branch_two_transactions():
    tx1 = bytes.fromhex("11" * 32)
    tx2 = bytes.fromhex("22" * 32)
    branch = module.build_coinbase_merkle_branch([tx1, tx2])
    assert len(branch) == 2
    assert branch[0] == tx1.hex()
    assert branch[1] == sha256d(tx2 + tx2).hex()


def test_merkle_root_matches_full_tree_for_two_transactions():
    coinbase_hash = bytes.fromhex("aa" * 32)
    tx1 = bytes.fromhex("11" * 32)
    tx2 = bytes.fromhex("22" * 32)
    branch = module.build_coinbase_merkle_branch([tx1, tx2])
    root = module.merkle_root(coinbase_hash, branch)
    expected = sha256d(sha256d(coinbase_hash + tx1) + sha256d(tx2 + tx2))
    assert root == expected

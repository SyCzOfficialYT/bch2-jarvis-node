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
        "5df6e0e2761359d3a0f4f9b8f7a3c3c9d0d4d0f4a9d9f7b2e4e8f9b6f5e8f3f8"
    )

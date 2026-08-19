from stratum_proxy_version_rolling import DEFAULT_VERSION_MASK, negotiate_mask, resolve_version


def test_negotiate_mask_intersects_miner_and_server_masks():
    assert negotiate_mask(0xFFFFFFFF) == DEFAULT_VERSION_MASK
    assert negotiate_mask(0x00003000) == 0x00003000


def test_resolve_version_uses_version_bits_not_full_version():
    # BIP310 mining.submit sends only the bits controlled by the mask.
    assert resolve_version("20086000", "00cb8000", DEFAULT_VERSION_MASK) == "20cb8000"


def test_resolve_version_preserves_job_bits_outside_mask():
    job_version = "e0000000"
    assert resolve_version(job_version, "00003000", DEFAULT_VERSION_MASK) == "e0003000"


def test_resolve_version_rejects_bits_outside_mask():
    try:
        resolve_version("20086000", "00000001", DEFAULT_VERSION_MASK)
    except ValueError as exc:
        assert "outside mask" in str(exc)
    else:
        raise AssertionError("version bits outside negotiated mask were accepted")

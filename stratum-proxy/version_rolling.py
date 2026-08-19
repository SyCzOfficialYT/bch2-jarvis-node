"""BIP310 version-rolling helpers for Stratum V1."""

from __future__ import annotations


DEFAULT_VERSION_MASK = 0x1FFFE000


def negotiate_mask(miner_mask: int, server_mask: int = DEFAULT_VERSION_MASK) -> int:
    """Return the BIP310 intersection of miner and server masks."""
    return (int(miner_mask) & int(server_mask)) & 0xFFFFFFFF


def resolve_version(job_version: str, version_bits: str, mask: int) -> str:
    """Build nVersion from job version and BIP310 version_bits.

    BIP310's sixth mining.submit parameter is *version_bits*, not the
    complete nVersion. Only bits covered by the negotiated mask are taken
    from the miner; all other bits remain from the job version.
    """
    job = int(str(job_version), 16) & 0xFFFFFFFF
    bits = int(str(version_bits), 16) & 0xFFFFFFFF
    mask = int(mask) & 0xFFFFFFFF

    if bits & ~mask:
        raise ValueError(f"version bits outside mask {mask:08x}")

    resolved = (job & ~mask) | (bits & mask)
    return f"{resolved & 0xFFFFFFFF:08x}"

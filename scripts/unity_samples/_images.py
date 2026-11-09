"""The samples' images, written with the standard library alone: one PNG writer
every recipe shares (``write_png``), so a sample's textures are byte for byte the
same on every run. A helper module (its name starts with ``_``), never a recipe.
"""


def write_png(path: str, pixel, size: int = 16) -> str:
    """An 8-bit RGBA PNG of *size* x *size* texels, ``pixel(x, y) -> (r, g, b,
    a)`` with ``y`` 0 the top row, written with the standard library's
    ``zlib`` and ``struct`` (byte for byte the same on every run).

    Returns:
        *path*.
    """
    import struct
    import zlib

    rows = b"".join(
        b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(size)) for y in range(size)
    )

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(
            b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b"")
        )
    return path

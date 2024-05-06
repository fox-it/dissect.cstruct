import io

from dissect.cstruct.cstruct import cstruct


def test_void(cs: cstruct) -> None:
    assert not cs.void

    stream = io.BytesIO(b"AAAA")
    assert not cs.void(stream)

    assert stream.tell() == 0
    assert cs.void().dumps() == b""

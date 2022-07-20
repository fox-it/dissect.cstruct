from io import BytesIO

import pytest

from dissect import cstruct
from dissect.cstruct.bitbuffer import BitBuffer


def test_bitbuffer_read():
    cs = cstruct.cstruct()

    bb = BitBuffer(BytesIO(b"\xff"), "<")
    assert bb.read(cs.uint8, 8) == 0b11111111

    bb = BitBuffer(BytesIO(b"\xf0"), "<")
    assert bb.read(cs.uint8, 4) == 0b0000
    assert bb.read(cs.uint8, 4) == 0b1111

    bb = BitBuffer(BytesIO(b"\xf0"), ">")
    assert bb.read(cs.uint8, 4) == 0b1111
    assert bb.read(cs.uint8, 4) == 0b0000

    bb = BitBuffer(BytesIO(b"\xff\x00"), "<")
    assert bb.read(cs.uint16, 12) == 0b11111111
    assert bb.read(cs.uint16, 4) == 0b0

    bb = BitBuffer(BytesIO(b"\xff\x00"), ">")
    assert bb.read(cs.uint16, 12) == 0b000000001111
    assert bb.read(cs.uint16, 4) == 0b1111

    bb = BitBuffer(BytesIO(b"\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff"), "<")
    with pytest.raises(ValueError) as exc:
        assert bb.read(cs.uint32, 160)
    assert str(exc.value) == "Reading straddled bits is unsupported"

    assert bb.read(cs.uint32, 30) == 0b111111111111111111111111111111
    assert bb.read(cs.uint32, 2) == 0b11
    assert bb.read(cs.uint32, 32) == 0b11111111111111111111111111111111

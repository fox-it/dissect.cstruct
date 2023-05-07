import io

import pytest

from dissect.cstruct.cstruct import cstruct


def test_char_read(cs: cstruct):
    assert cs.char(b"A") == b"A"
    assert cs.char(b"AAAA\x00") == b"A"
    assert cs.char(io.BytesIO(b"AAAA\x00")) == b"A"


def test_char_write(cs: cstruct):
    assert cs.char(b"A").dumps() == b"A"


def test_char_array(cs: cstruct):
    buf = b"AAAA\x00"

    assert cs.char[4](buf) == b"AAAA"
    assert cs.char[4](io.BytesIO(buf)) == b"AAAA"

    assert cs.char[None](buf) == b"AAAA"
    assert cs.char[None](io.BytesIO(buf)) == b"AAAA"


def test_char_array_write(cs: cstruct):
    buf = b"AAAA\x00"

    assert cs.char[4](buf).dumps() == b"AAAA"
    assert cs.char[None](buf).dumps() == b"AAAA\x00"


def test_char_operator(cs: cstruct):
    new_char = cs.char(b"A") + b"B"
    assert new_char == b"AB"
    assert isinstance(new_char, cs.char)


def test_char_eof(cs: cstruct):
    with pytest.raises(EOFError):
        cs.char(b"")

    with pytest.raises(EOFError):
        cs.char[4](b"")

    with pytest.raises(EOFError):
        cs.char[None](b"AAAA")

    assert cs.char[0](b"") == b""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


def test_wchar_read(cs: cstruct) -> None:
    buf = b"A\x00A\x00A\x00A\x00\x00\x00"

    assert cs.wchar("A") == "A"
    assert cs.wchar(buf) == "A"
    assert cs.wchar(io.BytesIO(buf)) == "A"


def test_wchar_write(cs: cstruct) -> None:
    assert cs.wchar("A").dumps() == b"A\x00"
    assert cs.wchar(b"A\x00").dumps() == b"A\x00"


def test_wchar_array(cs: cstruct) -> None:
    buf = b"A\x00A\x00A\x00A\x00\x00\x00"

    assert cs.wchar[4]("AAAA") == "AAAA"
    assert cs.wchar[4](buf) == "AAAA"
    assert cs.wchar[4](io.BytesIO(buf)) == "AAAA"
    assert cs.wchar[None](io.BytesIO(buf)) == "AAAA"


def test_wchar_array_write(cs: cstruct) -> None:
    buf = b"A\x00A\x00A\x00A\x00\x00\x00"

    assert cs.wchar[4](buf).dumps() == b"A\x00A\x00A\x00A\x00"
    assert cs.wchar[None](buf).dumps() == b"A\x00A\x00A\x00A\x00\x00\x00"


def test_wchar_be_read(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.wchar(b"\x00A\x00A\x00A\x00A\x00\x00") == "A"


def test_wchar_be_write(cs: cstruct) -> None:
    cs.endian = ">"

    assert cs.wchar("A").dumps() == b"\x00A"


def test_wchar_be_array(cs: cstruct) -> None:
    cs.endian = ">"

    buf = b"\x00A\x00A\x00A\x00A\x00\x00"

    assert cs.wchar[4](buf) == "AAAA"
    assert cs.wchar[None](buf) == "AAAA"


def test_wchar_be_array_write(cs: cstruct) -> None:
    cs.endian = ">"

    buf = b"\x00A\x00A\x00A\x00A\x00\x00"

    assert cs.wchar[4](buf).dumps() == b"\x00A\x00A\x00A\x00A"
    assert cs.wchar[None](buf).dumps() == buf


def test_wchar_eof(cs: cstruct) -> None:
    with pytest.raises(EOFError):
        cs.wchar(b"A")

    with pytest.raises(EOFError):
        cs.wchar[4](b"")

    with pytest.raises(EOFError):
        cs.wchar[None](b"A\x00A\x00A\x00A\x00")

    assert cs.wchar[0](b"") == ""


def test_wchar_default(cs: cstruct) -> None:
    assert cs.wchar.__default__() == "\x00"
    assert cs.wchar[4].__default__() == "\x00\x00\x00\x00"
    assert cs.wchar[None].__default__() == ""

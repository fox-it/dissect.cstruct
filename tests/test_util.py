import pytest

from dissect import cstruct
from dissect.cstruct.utils import dumpstruct, hexdump

from .utils import verify_compiled


def test_hexdump(capsys):
    hexdump(b"\x00" * 16)
    captured = capsys.readouterr()
    assert captured.out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................\n"

    out = hexdump(b"\x00" * 16, output="string")
    assert out == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    out = hexdump(b"\x00" * 16, output="generator")
    assert next(out) == "00000000  00 00 00 00 00 00 00 00  00 00 00 00 00 00 00 00   ................"

    with pytest.raises(ValueError) as excinfo:
        hexdump("b\x00", output="str")
    assert str(excinfo.value) == "Invalid output argument: 'str' (should be 'print', 'generator' or 'string')."


def test_dumpstruct(capsys, compiled):
    cdef = """
    struct test {
        uint32 testval;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x39\x05\x00\x00"
    obj = cs.test(buf)

    dumpstruct(cs.test, buf)
    captured_1 = capsys.readouterr()

    dumpstruct(obj)
    captured_2 = capsys.readouterr()

    assert captured_1.out == captured_2.out

    out_1 = dumpstruct(cs.test, buf, output="string")
    out_2 = dumpstruct(obj, output="string")

    assert out_1 == out_2

    with pytest.raises(ValueError) as excinfo:
        dumpstruct(obj, output="generator")
    assert str(excinfo.value) == "Invalid output argument: 'generator' (should be 'print' or 'string')."

import pytest

from dissect import cstruct
from dissect.cstruct.types.pointer import PointerInstance

from .utils import verify_compiled


@pytest.mark.parametrize("compiled", [True, False])
def test_pointer_basic(compiled):
    d = """
    struct ptrtest {
        uint32  *ptr1;
        uint32  *ptr2;
    };
    """
    c = cstruct.cstruct(pointer="uint16")
    c.load(d, compiled=compiled)

    assert verify_compiled(c.ptrtest, compiled)

    d = b"\x04\x00\x08\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    p = c.ptrtest(d)

    assert p.ptr1 != 0
    assert p.ptr2 != 0
    assert p.ptr1 != p.ptr2
    assert p.ptr1 == 4
    assert p.ptr2 == 8
    assert p.ptr1.dereference() == 0x04030201
    assert p.ptr2.dereference() == 0x08070605

    p.ptr1 += 2
    p.ptr2 -= 2
    assert p.ptr1 == p.ptr2
    assert p.ptr1.dereference() == p.ptr2.dereference() == 0x06050403

    assert p.dumps() == b"\x06\x00\x06\x00"

    with pytest.raises(cstruct.NullPointerDereference):
        c.ptrtest(b"\x00\x00\x00\x00").ptr1.dereference()


@pytest.mark.parametrize("compiled", [True, False])
def test_pointer_struct(compiled):
    d = """
    struct test {
        char    magic[4];
        wchar   wmagic[4];
        uint8   a;
        uint16  b;
        uint32  c;
        char    string[];
        wchar   wstring[];
    };

    struct ptrtest {
        test    *ptr;
    };
    """
    c = cstruct.cstruct(pointer="uint16")
    c.load(d, compiled=compiled)

    assert verify_compiled(c.test, compiled)
    assert verify_compiled(c.ptrtest, compiled)

    d = b"\x02\x00testt\x00e\x00s\x00t\x00\x01\x02\x03\x04\x05\x06\x07lalala\x00t\x00e\x00s\x00t\x00\x00\x00"
    p = c.ptrtest(d)

    assert p.ptr != 0

    assert p.ptr.magic == b"test"
    assert p.ptr.wmagic == "test"
    assert p.ptr.a == 0x01
    assert p.ptr.b == 0x0302
    assert p.ptr.c == 0x07060504
    assert p.ptr.string == b"lalala"
    assert p.ptr.wstring == "test"

    assert p.dumps() == b"\x02\x00"

    with pytest.raises(cstruct.NullPointerDereference):
        c.ptrtest(b"\x00\x00\x00\x00").ptr.magic


def test_pointer_arithmetic():
    inst = PointerInstance(None, None, 0, None)
    assert inst._addr == 0

    inst += 4
    assert inst._addr == 4

    inst -= 2
    assert inst._addr == 2

    inst *= 12
    assert inst._addr == 24

    inst //= 2
    assert inst._addr == 12

    inst %= 10
    assert inst._addr == 2

    inst **= 4
    assert inst._addr == 16

    inst <<= 1
    assert inst._addr == 32

    inst >>= 2
    assert inst._addr == 8

    inst &= 2
    assert inst._addr == 0

    inst ^= 4
    assert inst._addr == 4

    inst |= 8
    assert inst._addr == 12

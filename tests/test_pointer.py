import pytest

from dissect import cstruct
from dissect.cstruct.types.pointer import PointerInstance

from .utils import verify_compiled


@pytest.mark.parametrize("compiled", [True, False])
def test_pointer_basic(compiled):
    cdef = """
    struct ptrtest {
        uint32  *ptr1;
        uint32  *ptr2;
    };
    """
    cs = cstruct.cstruct(pointer="uint16")
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.ptrtest, compiled)

    buf = b"\x04\x00\x08\x00\x01\x02\x03\x04\x05\x06\x07\x08"
    obj = cs.ptrtest(buf)

    assert obj.ptr1 != 0
    assert obj.ptr2 != 0
    assert obj.ptr1 != obj.ptr2
    assert obj.ptr1 == 4
    assert obj.ptr2 == 8
    assert obj.ptr1.dereference() == 0x04030201
    assert obj.ptr2.dereference() == 0x08070605

    obj.ptr1 += 2
    obj.ptr2 -= 2
    assert obj.ptr1 == obj.ptr2
    assert obj.ptr1.dereference() == obj.ptr2.dereference() == 0x06050403

    assert obj.dumps() == b"\x06\x00\x06\x00"

    with pytest.raises(cstruct.NullPointerDereference):
        cs.ptrtest(b"\x00\x00\x00\x00").ptr1.dereference()


@pytest.mark.parametrize("compiled", [True, False])
def test_pointer_struct(compiled):
    cdef = """
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
    cs = cstruct.cstruct(pointer="uint16")
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)
    assert verify_compiled(cs.ptrtest, compiled)

    buf = b"\x02\x00testt\x00e\x00s\x00t\x00\x01\x02\x03\x04\x05\x06\x07lalala\x00t\x00e\x00s\x00t\x00\x00\x00"
    obj = cs.ptrtest(buf)

    assert obj.ptr != 0

    assert obj.ptr.magic == b"test"
    assert obj.ptr.wmagic == "test"
    assert obj.ptr.a == 0x01
    assert obj.ptr.b == 0x0302
    assert obj.ptr.c == 0x07060504
    assert obj.ptr.string == b"lalala"
    assert obj.ptr.wstring == "test"

    assert obj.dumps() == b"\x02\x00"

    with pytest.raises(cstruct.NullPointerDereference):
        cs.ptrtest(b"\x00\x00\x00\x00").ptr.magic


@pytest.mark.parametrize("compiled", [True, False])
def test_array_of_pointers(compiled):
    cdef = """
    struct mainargs {
        uint8_t argc;
        char *args[4];
    }
    """
    cs = cstruct.cstruct(pointer="uint16")
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.mainargs, compiled)

    buf = b"\x02\x09\x00\x16\x00\x00\x00\x00\x00argument one\x00argument two\x00"
    obj = cs.mainargs(buf)

    assert obj.argc == 2
    assert obj.args[2] == 0
    assert obj.args[3] == 0
    assert obj.args[0].dereference() == b'argument one'
    assert obj.args[1].dereference() == b'argument two'


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

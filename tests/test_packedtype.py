import pytest
from dissect import cstruct

from dissect.cstruct.types import PackedType

from .utils import verify_compiled


def test_packedtype_float():
    cs = cstruct.cstruct()

    assert cs.float16.dumps(420.69) == b"\x93^"
    assert cs.float.dumps(31337.6969) == b"e\xd3\xf4F"
    assert cs.float16.reads(b"\x69\x69") == 2770.0
    assert cs.float.reads(b"M0MS") == 881278648320.0


def test_packedtype_float_struct(compiled):
    cdef = """
    struct test {
        float16 a;
        float   b;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"69\xb1U$G"
    obj = cs.test(buf)

    assert obj.a == 0.6513671875
    assert obj.b == 42069.69140625


def test_packedtype_float_struct_be(compiled):
    cdef = """
    struct test {
        float16 a;
        float   b;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)
    cs.endian = ">"

    assert verify_compiled(cs.test, compiled)

    buf = b"69G$U\xb1"
    obj = cs.test(buf)
    print(obj)

    assert obj.a == 0.388916015625
    assert obj.b == 42069.69140625


def test_packedtype_range():
    cs = cstruct.cstruct()
    float16 = PackedType(cs, "float16", 2, "e")
    float16.dumps(-65519.999999999996)
    float16.dumps(65519.999999999996)
    with pytest.raises(OverflowError):
        float16.dumps(-65519.999999999997)
    with pytest.raises(OverflowError):
        float16.dumps(65519.999999999997)

import pytest

from dissect import cstruct
from dissect.cstruct.types import PackedType

from .utils import verify_compiled


def test_packedtype_struct_float(compiled):
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


def test_packedtype_struct_float_be(compiled):
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

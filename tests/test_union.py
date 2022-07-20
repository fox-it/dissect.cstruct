from dissect import cstruct

from .utils import verify_compiled


def test_union():
    cdef = """
    union test {
        uint32 a;
        char   b[8];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=False)

    assert len(cs.test) == 8

    buf = b"zomgbeef"
    obj = cs.test(buf)

    assert obj.a == 0x676D6F7A
    assert obj.b == b"zomgbeef"

    assert obj.dumps() == buf
    assert cs.test().dumps() == b"\x00\x00\x00\x00\x00\x00\x00\x00"


def test_union_nested(compiled):
    cdef = """
    struct test {
        char magic[4];
        union {
            struct {
                uint32 a;
                uint32 b;
            } a;
            struct {
                char   b[8];
            } b;
        } c;
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    assert len(cs.test) == 12

    buf = b"zomgholybeef"
    obj = cs.test(buf)

    assert obj.magic == b"zomg"
    assert obj.c.a.a == 0x796C6F68
    assert obj.c.a.b == 0x66656562
    assert obj.c.b.b == b"holybeef"

    assert obj.dumps() == buf


def test_union_anonymous(compiled):
    cdef = """
    typedef struct test
    {
        union
        {
            uint32 a;
            struct
            {
                char b[3];
                char c;
            };
        };
        uint32 d;
    }
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    buf = b"\x01\x01\x02\x02\x03\x03\x04\x04"
    obj = cs.test(buf)

    assert obj.a == 0x02020101
    assert obj.b == b"\x01\x01\x02"
    assert obj.c == b"\x02"
    assert obj.d == 0x04040303
    assert obj.dumps() == buf

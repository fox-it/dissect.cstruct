import io

from dissect.cstruct.cstruct import cstruct

from .utils import verify_compiled


def test_void_read(cs: cstruct) -> None:
    assert not cs.void

    stream = io.BytesIO(b"AAAA")
    assert not cs.void(stream)

    assert stream.tell() == 0


def test_void_write(cs: cstruct) -> None:
    assert cs.void().dumps() == b""


def test_void_array_read(cs: cstruct) -> None:
    assert not cs.void[4]

    stream = io.BytesIO(b"AAAA")
    assert not any(cs.void[4](stream))
    assert not any(cs.void[None](stream))
    assert stream.tell() == 0


def test_void_array_write(cs: cstruct) -> None:
    assert cs.void[4](b"AAAA").dumps() == b""
    assert cs.void[None](b"AAAA").dumps() == b""


def test_void_default(cs: cstruct) -> None:
    assert cs.void() == cs.void.default()
    assert not cs.void()
    assert not cs.void.default()

    assert cs.void[1].default() == [cs.void()]
    assert cs.void[None].default() == []


def test_void_struct(cs: cstruct, compiled: bool) -> None:
    cdef = """
    struct test {
        void    a;
        void    b[4];
        void    c[];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    stream = io.BytesIO(b"AAAA")

    obj = cs.test(stream)
    assert not obj.a
    assert not any(obj.b)
    assert not any(obj.c)

    assert stream.tell() == 0

    assert obj.dumps() == b""

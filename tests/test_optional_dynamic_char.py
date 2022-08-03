import struct

from io import BytesIO
from dissect import cstruct

cdef = """
typedef struct STRUCT_A {
    uint8 character_count;
    char data[character_count];
};

typedef struct STRUCT_B {
    char name[];
};

typedef struct test {
    uint8 type;
    STRUCT_B name;    // optional name
    STRUCT_A payload; // optional struct based on type and name
};
"""


def test_optional_dumps_write():
    buf_1 = BytesIO(b"\x69zomg\x00\x04nice")
    buf_2 = BytesIO(b"\x68zomg\x00")
    buf_3 = BytesIO(b"\x67")

    bufs = [buf_1, buf_2, buf_3]

    cs = cstruct.cstruct()
    cs.load(cdef)

    for buf in bufs:
        type = struct.unpack("b", buf.read(1))[0]

        if type == 0x69:
            buf.seek(0)
            obj = cs.test(buf)
            obj.dumps()

        if type == 0x68:
            obj = cs.test(type=type, name=None, payload=None)

            try:
                obj.dumps()
            except TypeError as e:
                assert str(e) != 'can only concatenate list (not "bytes") to list'

        if type == 0x67:
            obj = cs.test(type=type, name=buf.read(), payload=None)

            try:
                obj.dumps()
            except TypeError as e:
                assert str(e) != 'can only concatenate list (not "bytes") to list'

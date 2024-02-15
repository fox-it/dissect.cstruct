import pytest

from dissect.cstruct.cstruct import cstruct


def test_leb128_unsigned_read_EOF(cs: cstruct):
    with pytest.raises(EOFError) as ex:
        cs.uleb128(b"\x8b")
    assert str(ex.value) == "EOF reached, while final LEB128 byte was not yet read."


def test_leb128_unsigned_read(cs: cstruct):
    assert cs.uleb128(b"\x02") == 2
    assert cs.uleb128(b"\x8b%") == 4747
    assert cs.uleb128(b"\xc9\x8f\xb0\x06") == 13371337
    assert cs.uleb128(b"~") == 126
    assert cs.uleb128(b"\xf5Z") == 11637
    assert cs.uleb128(b"\xde\xd6\xcf|") == 261352286


def test_leb128_signed_read(cs: cstruct):
    assert cs.ileb128(b"\x02") == 2
    assert cs.ileb128(b"\x8b%") == 4747
    assert cs.ileb128(b"\xc9\x8f\xb0\x06") == 13371337
    assert cs.ileb128(b"~") == -2
    assert cs.ileb128(b"\xf5Z") == -4747
    assert cs.ileb128(b"\xde\xd6\xcf|") == -7083170


def test_leb128_struct_unsigned(cs: cstruct):
    cdef = """
    struct test {
        uleb128 len;
        char  data[len];
    };
    """
    cs.load(cdef)

    buf = b"\xaf\x18"
    buf += b"A" * 3119
    obj = cs.test(buf)

    assert obj.len == 3119
    assert obj.data == (b"A" * 3119)
    assert len(obj.data) == 3119
    assert len(buf) == 3119 + 2


def test_leb128_struct_unsigned_zero(cs: cstruct):
    cdef = """
    struct test {
        uleb128 numbers[];
    };
    """
    cs.load(cdef)

    buf = b"\xaf\x18\x8b%\xc9\x8f\xb0\x06\x00"
    obj = cs.test(buf)

    assert len(obj.numbers) == 3
    assert obj.numbers[0] == 3119
    assert obj.numbers[1] == 4747
    assert obj.numbers[2] == 13371337


def test_leb128_struct_signed_zero(cs: cstruct):
    cdef = """
    struct test {
        ileb128 numbers[];
    };
    """
    cs.load(cdef)

    buf = b"\xaf\x18\xf5Z\xde\xd6\xcf|\x00"
    obj = cs.test(buf)

    assert len(obj.numbers) == 3
    assert obj.numbers[0] == 3119
    assert obj.numbers[1] == -4747
    assert obj.numbers[2] == -7083170


def test_leb128_nested_struct_unsigned(cs: cstruct):
    cdef = """
    struct entry {
        uleb128 len;
        char  data[len];
        uint32 crc;
    };
    struct nested {
        uleb128  name_len;
        char     name[name_len];
        uleb128  n_entries;
        entry    entries[n_entries];
    };
    """
    cs.load(cdef)

    # Dummy file format specifying 300 entries
    buf = b"\x08Testfile\xac\x02"

    # Each entry has 4 byte data + 4 byte CRC
    buf += b"\x04AAAABBBB" * 300

    obj = cs.nested(buf)

    assert obj.name_len == 8
    assert obj.name == b"Testfile"
    assert obj.n_entries == 300


def test_leb128_nested_struct_signed(cs: cstruct):
    cdef = """
    struct entry {
        ileb128 len;
        char  data[len];
        uint32 crc;
    };
    struct nested {
        ileb128  name_len;
        char     name[name_len];
        ileb128  n_entries;
        entry    entries[n_entries];
    };
    """
    cs.load(cdef)

    # Dummy file format specifying 300 entries
    buf = b"\x08Testfile\xac\x02"

    # Each entry has 4 byte data + 4 byte CRC
    buf += b"\x04AAAABBBB" * 300

    obj = cs.nested(buf)

    assert obj.name_len == 8
    assert obj.name == b"Testfile"
    assert obj.n_entries == 300


def test_leb128_unsigned_write(cs: cstruct):
    assert cs.uleb128(2).dumps() == b"\x02"
    assert cs.uleb128(4747).dumps() == b"\x8b%"
    assert cs.uleb128(13371337).dumps() == b"\xc9\x8f\xb0\x06"
    assert cs.uleb128(126).dumps() == b"~"
    assert cs.uleb128(11637).dumps() == b"\xf5Z"
    assert cs.uleb128(261352286).dumps() == b"\xde\xd6\xcf|"


def test_leb128_signed_write(cs: cstruct):
    assert cs.ileb128(2).dumps() == b"\x02"
    assert cs.ileb128(4747).dumps() == b"\x8b%"
    assert cs.ileb128(13371337).dumps() == b"\xc9\x8f\xb0\x06"
    assert cs.ileb128(-2).dumps() == b"~"
    assert cs.ileb128(-4747).dumps() == b"\xf5Z"
    assert cs.ileb128(-7083170).dumps() == b"\xde\xd6\xcf|"
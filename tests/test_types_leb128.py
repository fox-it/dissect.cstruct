import io

import pytest
from dissect import cstruct


def test_leb128_unsigned_read_EOF():
    cs = cstruct.cstruct()

    with pytest.raises(EOFError, match="EOF reached, while final LEB128 byte was not yet read"):
        cs.uleb128(b"\x8b")


def test_leb128_unsigned_read():
    cs = cstruct.cstruct()

    assert cs.uleb128(b"\x02") == 2
    assert cs.uleb128(b"\x8b\x25") == 4747
    assert cs.uleb128(b"\xc9\x8f\xb0\x06") == 13371337
    assert cs.uleb128(b"\x7e") == 126
    assert cs.uleb128(b"\xf5\x5a") == 11637
    assert cs.uleb128(b"\xde\xd6\xcf\x7c") == 261352286


def test_leb128_signed_read():
    cs = cstruct.cstruct()

    assert cs.ileb128(b"\x02") == 2
    assert cs.ileb128(b"\x8b\x25") == 4747
    assert cs.ileb128(b"\xc9\x8f\xb0\x06") == 13371337
    assert cs.ileb128(b"\x7e") == -2
    assert cs.ileb128(b"\xf5\x5a") == -4747
    assert cs.ileb128(b"\xde\xd6\xcf\x7c") == -7083170


@pytest.mark.parametrize("compiled", [True, False])
def test_leb128_struct_unsigned(compiled):
    cdef = """
    struct test {
        uleb128 len;
        char    data[len];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    buf = b"\xaf\x18"
    buf += b"\x41" * 3119
    obj = cs.test(buf)

    assert obj.len == 3119
    assert obj.data == (b"\x41" * 3119)
    assert len(obj.data) == 3119
    assert len(buf) == 3119 + 2

    assert obj.dumps() == buf


@pytest.mark.parametrize("compiled", [True, False])
def test_leb128_struct_unsigned_zero(compiled):
    cdef = """
    struct test {
        uleb128 numbers[];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    buf = b"\xaf\x18\x8b\x25\xc9\x8f\xb0\x06\x00"
    obj = cs.test(buf)

    assert len(obj.numbers) == 3
    assert obj.numbers[0] == 3119
    assert obj.numbers[1] == 4747
    assert obj.numbers[2] == 13371337

    assert obj.dumps() == buf


@pytest.mark.parametrize("compiled", [True, False])
def test_leb128_struct_signed_zero(compiled):
    cdef = """
    struct test {
        ileb128 numbers[];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    buf = b"\xaf\x18\xf5\x5a\xde\xd6\xcf\x7c\x00"
    obj = cs.test(buf)

    assert len(obj.numbers) == 3
    assert obj.numbers[0] == 3119
    assert obj.numbers[1] == -4747
    assert obj.numbers[2] == -7083170

    assert obj.dumps() == buf


@pytest.mark.parametrize("compiled", [True, False])
def test_leb128_nested_struct_unsigned(compiled):
    cdef = """
    struct entry {
        uleb128 len;
        char    data[len];
        uint32  crc;
    };
    struct nested {
        uleb128 name_len;
        char    name[name_len];
        uleb128 n_entries;
        entry   entries[n_entries];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    # Dummy file format specifying 300 entries
    buf = b"\x08\x54\x65\x73\x74\x66\x69\x6c\x65\xac\x02"

    # Each entry has 4 byte data + 4 byte CRC
    buf += b"\x04\x41\x41\x41\x41\x42\x42\x42\x42" * 300

    obj = cs.nested(buf)

    assert obj.name_len == 8
    assert obj.name == b"\x54\x65\x73\x74\x66\x69\x6c\x65"
    assert obj.n_entries == 300

    assert obj.dumps() == buf


@pytest.mark.parametrize("compiled", [True, False])
def test_leb128_nested_struct_signed(compiled):
    cdef = """
    struct entry {
        ileb128 len;
        char    data[len];
        uint32  crc;
    };
    struct nested {
        ileb128 name_len;
        char    name[name_len];
        ileb128 n_entries;
        entry   entries[n_entries];
    };
    """
    cs = cstruct.cstruct()
    cs.load(cdef, compiled=compiled)

    # Dummy file format specifying 300 entries
    buf = b"\x08\x54\x65\x73\x74\x66\x69\x6c\x65\xac\x02"

    # Each entry has 4 byte data + 4 byte CRC
    buf += b"\x04\x41\x41\x41\x41\x42\x42\x42\x42" * 300

    obj = cs.nested(buf)

    assert obj.name_len == 8
    assert obj.name == b"\x54\x65\x73\x74\x66\x69\x6c\x65"
    assert obj.n_entries == 300

    assert obj.dumps() == buf


def test_leb128_unsigned_write():
    cs = cstruct.cstruct()

    assert cs.uleb128.dumps(2) == b"\x02"
    assert cs.uleb128.dumps(4747) == b"\x8b\x25"
    assert cs.uleb128.dumps(13371337) == b"\xc9\x8f\xb0\x06"
    assert cs.uleb128.dumps(126) == b"\x7e"
    assert cs.uleb128.dumps(11637) == b"\xf5\x5a"
    assert cs.uleb128.dumps(261352286) == b"\xde\xd6\xcf\x7c"


def test_leb128_signed_write():
    cs = cstruct.cstruct()

    assert cs.ileb128.dumps(2) == b"\x02"
    assert cs.ileb128.dumps(4747) == b"\x8b\x25"
    assert cs.ileb128.dumps(13371337) == b"\xc9\x8f\xb0\x06"
    assert cs.ileb128.dumps(-2) == b"\x7e"
    assert cs.ileb128.dumps(-4747) == b"\xf5\x5a"
    assert cs.ileb128.dumps(-7083170) == b"\xde\xd6\xcf\x7c"


def test_leb128_write_negatives():
    cs = cstruct.cstruct()

    with pytest.raises(ValueError, match="Attempt to encode a negative integer using unsigned LEB128 encoding"):
        cs.uleb128.dumps(-2)
    assert cs.ileb128.dumps(-2) == b"\x7e"


def test_leb128_unsigned_write_amount_written():
    cs = cstruct.cstruct()

    out1 = io.BytesIO()
    bytes_written1 = cs.uleb128.write(out1, 2)
    assert bytes_written1 == out1.tell()

    out2 = io.BytesIO()
    bytes_written2 = cs.uleb128.write(out2, 4747)
    assert bytes_written2 == out2.tell()

    out3 = io.BytesIO()
    bytes_written3 = cs.uleb128.write(out3, 13371337)
    assert bytes_written3 == out3.tell()

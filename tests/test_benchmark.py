from __future__ import annotations

import io
from functools import partial
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.expression import Expression
from dissect.cstruct.lexer import tokenize
from dissect.cstruct.parser import CStyleParser, _join_line_continuations

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from dissect.cstruct.cstruct import cstruct
    from dissect.cstruct.lexer import Token


@pytest.mark.benchmark
def test_benchmark_basic(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of a simple struct with both the compiled and interpreted backends."""
    cdef = """
    struct test {
        uint32  a;
        uint64  b;
        uint16  c;
        uint8   d;
    };
    """
    cs.load(cdef, compiled=compiled)

    benchmark(lambda: cs.test(b"\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x03\x00\x04"))


@pytest.mark.benchmark
def test_benchmark_union(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of a simple union with both the compiled and interpreted backends."""
    cdef = """
    union test {
        uint32  a;
        uint64  b;
        uint16  c;
        uint8   d;
    };
    """
    cs.load(cdef, compiled=compiled)

    benchmark(lambda: cs.test(b"\x01\x02\x03\x04\x05\x06\x07\x08"))


@pytest.mark.benchmark
def test_benchmark_union_nested(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of a union with nested structures with both the compiled and interpreted backends."""
    cdef = """
    union test {
        struct {
            uint32  offset;
            uint32  block;
        } lsn;
        struct {
            uint16  low;
            uint16  mid;
            uint32  high;
        } parts;
        uint64  value;
    };
    """
    cs.load(cdef, compiled=compiled)

    benchmark(lambda: cs.test(b"\x01\x02\x03\x04\x05\x06\x07\x08"))


@pytest.mark.benchmark
def test_benchmark_union_array(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of an array of unions with both the compiled and interpreted backends."""
    cdef = """
    union test {
        uint32  a;
        char    b[4];
    };
    """
    cs.load(cdef, compiled=compiled)

    buf = bytes(range(64))
    benchmark(lambda: cs.test[16](buf))


@pytest.mark.benchmark
def test_benchmark_attribute_access(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the attribute access of a parsed struct."""
    cdef = """
    struct test {
        uint32  a;
        uint64  b;
        uint16  c;
        uint8   d;
    };
    """
    cs.load(cdef)
    obj = cs.test(b"\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x03\x00\x04")

    benchmark(lambda: (obj.a, obj.b, obj.c, obj.d))


@pytest.mark.benchmark
def test_benchmark_getattr_constants(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the resolving of constants on the cstruct instance."""
    cdef = """
    #define CONST1 1
    """
    cs.load(cdef)

    benchmark(lambda: cs.CONST1)


@pytest.mark.benchmark
def test_benchmark_getattr_types(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the resolving of types on the cstruct instance."""
    benchmark(lambda: cs.uint8)


@pytest.mark.benchmark
def test_benchmark_getattr_typedefs(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the resolving of typedefs on the cstruct instance."""
    cdef = """
    typedef uint8 my_uint8;
    """
    cs.load(cdef)

    benchmark(lambda: cs.my_uint8)


@pytest.mark.benchmark
def test_benchmark_expression_parse(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of expressions."""
    cs.load("#define a 5\n#define b 10")

    benchmark(lambda: Expression("a * 2 + b * (3 + 4) >> 1"))


@pytest.mark.benchmark
def test_benchmark_expression_evaluate(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the evaluation of expressions."""
    cs.load("#define a 5\n#define b 10")

    expression = Expression("a * 2 + b * (3 + 4) >> 1")
    benchmark(lambda: expression.evaluate(cs))


@pytest.mark.benchmark
def test_benchmark_expression_parse_and_evaluate(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing and evaluation of expressions."""
    cs.load("#define a 5\n#define b 10")

    benchmark(lambda: Expression("a * 2 + b * (3 + 4) >> 1").evaluate(cs))


_BENCHMARK_CDEF = """
struct SECURITY_DESCRIPTOR {
    uint8   Revision;
    uint8   Sbz1;
    uint16  Control;
    uint32  OffsetOwner;
    uint32  OffsetGroup;
    uint32  OffsetSacl;
    uint32  OffsetDacl;
};

struct LDAP_SID_IDENTIFIER_AUTHORITY {
    char    Value[6];
};

struct LDAP_SID {
    uint8   Revision;
    uint8   SubAuthorityCount;
    LDAP_SID_IDENTIFIER_AUTHORITY   IdentifierAuthority;
    uint32  SubAuthority[SubAuthorityCount];
};

struct ACL {
    uint8   AclRevision;
    uint8   Sbz1;
    uint16  AclSize;
    uint16  AceCount;
    uint16  Sbz2;
    char    Data[AclSize - 8];
};

struct ACE {
    uint8   AceType;
    uint8   AceFlags;
    uint16  AceSize;
    char    Data[AceSize - 4];
};

struct ACCESS_ALLOWED_ACE {
    uint16  Mask;
    LDAP_SID Sid;
};

struct ACCESS_ALLOWED_OBJECT_ACE {
    uint32  Mask;
    uint32  Flags;
    char    ObjectType[(Flags & 1) * 16];
    char    InheritedObjectType[(Flags & 2) * 8];
    LDAP_SID Sid;
};
"""


@pytest.mark.benchmark
def test_benchmark_lexer(benchmark: BenchmarkFixture) -> None:
    """Benchmark tokenizing a realistic set of struct definitions."""
    benchmark(lambda: tokenize(_BENCHMARK_CDEF))


@pytest.mark.benchmark
def test_benchmark_parser(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark parsing a realistic set of struct definitions."""
    cs.add_type = partial(cs.add_type, replace=True)

    parser = CStyleParser(cs)
    cdef = _join_line_continuations(_BENCHMARK_CDEF)
    tokens = tokenize(cdef)

    def parse(parser: CStyleParser, tokens: list[Token]) -> None:
        parser.reset()
        parser._tokens = tokens
        parser._parse()

    benchmark(lambda: parse(parser, tokens))


@pytest.mark.benchmark
def test_benchmark_lexer_and_parser(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark tokenizing and parsing a realistic set of struct definitions."""
    cs.add_type = partial(cs.add_type, replace=True)

    benchmark(lambda: cs.load(_BENCHMARK_CDEF))


@pytest.mark.benchmark
def test_benchmark_nested_dynamic(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of a realistic struct with nested structs and dynamically sized arrays."""
    cs.load(_BENCHMARK_CDEF, compiled=compiled)

    buf = (
        b"\x01\x00\x00\x00"  # Mask
        b"\x03\x00\x00\x00"  # Flags
        + bytes(range(16))  # ObjectType
        + bytes(range(16))  # InheritedObjectType
        + b"\x01\x04\x00\x00\x00\x00\x00\x05"  # Sid
        + b"\x15\x00\x00\x00" * 4  # Sid.SubAuthority
    )

    benchmark(lambda: cs.ACCESS_ALLOWED_OBJECT_ACE(buf))


@pytest.mark.benchmark
def test_benchmark_enum_flag_bits(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of a struct with enums, flags and bit fields."""
    cdef = """
    enum Type : uint16 {
        A = 1,
        B = 2,
    };

    flag Flags : uint16 {
        X = 1,
        Y = 2,
        Z = 4,
    };

    struct test {
        Type    type;
        Flags   flags;
        uint16  a : 4;
        uint16  b : 12;
        uint32  c;
    };
    """
    cs.load(cdef, compiled=compiled)

    benchmark(lambda: cs.test(b"\x01\x00\x05\x00\x34\x12\x01\x00\x00\x00"))


@pytest.mark.benchmark
def test_benchmark_flag_operators(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark bitwise operations on flags."""
    cdef = """
    flag Flags : uint16 {
        X = 1,
        Y = 2,
        Z = 4,
    };
    """
    cs.load(cdef)
    value = cs.Flags.X | cs.Flags.Z

    benchmark(lambda: (value & cs.Flags.X, value | cs.Flags.Y, value & 0x4))


@pytest.mark.benchmark
def test_benchmark_strings(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of a struct with fixed size and null-terminated strings."""
    cdef = """
    struct test {
        wchar   name[8];
        char    path[];
        wchar   description[];
    };
    """
    cs.load(cdef, compiled=compiled)

    buf = (
        "filename".encode("utf-16-le")  # name
        + b"some/path/to/a/file\x00"  # path
        + "A description".encode("utf-16-le")  # description
        + b"\x00\x00"
    )

    benchmark(lambda: cs.test(buf))


@pytest.mark.benchmark
@pytest.mark.parametrize("kind", ["bytes", "memoryview", "stream"])
def test_benchmark_primitive(cs: cstruct, kind: str, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of a primitive type from different kinds of input."""
    buf = b"\x01\x02\x03\x04"

    if kind == "stream":
        fh = io.BytesIO(buf)

        def read() -> int:
            fh.seek(0)
            return cs.uint32(fh)

        benchmark(read)
    else:
        obj = memoryview(buf) if kind == "memoryview" else buf
        benchmark(lambda: cs.uint32(obj))


@pytest.mark.benchmark
def test_benchmark_array(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the parsing of an array type created at runtime."""
    buf = bytes(range(64))

    benchmark(lambda: cs.uint32[16](buf))


@pytest.mark.benchmark
def test_benchmark_dumps(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark the writing of a simple struct."""
    cdef = """
    struct test {
        uint32  a;
        uint64  b;
        uint16  c;
        uint8   d;
    };
    """
    cs.load(cdef)
    obj = cs.test(b"\x01\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x03\x00\x04")

    benchmark(lambda: obj.dumps())


@pytest.mark.benchmark
def test_benchmark_load_and_read(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
    """Benchmark loading struct definitions and reading one struct, which includes any (lazy) compilation."""
    cs.add_type = partial(cs.add_type, replace=True)

    buf = b"\x02\x01\x00\x00\x00\x00\x00\x05" + b"\x15\x00\x00\x00" * 2

    def load_and_read() -> None:
        cs.load(_BENCHMARK_CDEF, compiled=compiled)
        cs.LDAP_SID(buf)

    benchmark(load_and_read)

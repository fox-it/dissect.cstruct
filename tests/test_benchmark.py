from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.expression import Expression

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from dissect.cstruct.cstruct import cstruct


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
def test_benchmark_lexer_and_parser(cs: cstruct, benchmark: BenchmarkFixture) -> None:
    """Benchmark tokenizing and parsing a realistic set of struct definitions."""
    cs.add_type = partial(cs.add_type, replace=True)

    benchmark(lambda: cs.load(_BENCHMARK_CDEF))

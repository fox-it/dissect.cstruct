from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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

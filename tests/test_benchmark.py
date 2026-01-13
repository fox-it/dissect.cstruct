from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_benchmark.fixture import BenchmarkFixture

    from dissect.cstruct.cstruct import cstruct


@pytest.mark.benchmark
def test_benchmark_basic(cs: cstruct, compiled: bool, benchmark: BenchmarkFixture) -> None:
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

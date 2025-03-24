from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.tools import stubgen

if TYPE_CHECKING:
    from pathlib import Path

    from dissect.cstruct.cstruct import cstruct


@pytest.mark.parametrize(
    ("cdef", "expected"),
    [
        pytest.param(
            """
            enum Test {
                A = 1,
                B = 2,
            };
            """,
            """
            class Test(Enum):
                A = ...
                B = ...
            """,
            id="enum",
        ),
        pytest.param(
            """
            enum Test : int8 {
                A = 1,
                B = 2,
            };
            """,
            """
            class Test(Enum):
                A = ...
                B = ...
            """,
            id="enum int8",
        ),
        pytest.param(
            """
            flag Test {
                A = 1,
                B = 2,
            };
            """,
            """
            class Test(Flag):
                A = ...
                B = ...
            """,
            id="flag",
        ),
    ],
)
def test_generate_enum_stub(cs: cstruct, cdef: str, expected: str) -> None:
    cs.load(cdef)

    assert stubgen.generate_enum_stub(cs.Test) == textwrap.dedent(expected).strip()


@pytest.mark.parametrize(
    ("cdef", "expected"),
    [
        pytest.param(
            """
            struct Test {
                uint8 a;
                uint8 b;
                unsigned short c;
            };
            """,
            """
            class Test(Structure):
                a: uint8
                b: uint8
                c: uint16
                @overload
                def __init__(self, a: uint8 | None = ..., b: uint8 | None = ..., c: uint16 | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
            """,
            id="basic",
        ),
        pytest.param(
            """
            struct Test {
                uint8 a[4];
                char b[4];
                wchar c[4];
            };
            """,
            """
            class Test(Structure):
                a: Array[uint8]
                b: CharArray
                c: WcharArray
                @overload
                def __init__(self, a: Array[uint8] | None = ..., b: CharArray | None = ..., c: WcharArray | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
            """,  # noqa: E501
            id="array",
        ),
        pytest.param(
            """
            struct Test {
                uint8 *a;
                uint8 *b[4];
            };
            """,
            """
            class Test(Structure):
                a: Pointer[uint8]
                b: Array[Pointer[uint8]]
                @overload
                def __init__(self, a: Pointer[uint8] | None = ..., b: Array[Pointer[uint8]] | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
            """,
            id="pointer",
        ),
        pytest.param(
            """
            struct Test {
                union {
                    uint8 a;
                    uint8 b;
                };
            };
            """,
            """
            class Test(Structure):
                a: uint8
                b: uint8
                @overload
                def __init__(self, a: uint8 | None = ..., b: uint8 | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
            """,
            id="anonymous nested",
        ),
        pytest.param(
            """
            struct Test {
                union {
                    uint8 a;
                    uint8 b;
                } x;
            };
            """,
            """
            class Test(Structure):
                class __anonymous_0__(Union):
                    a: uint8
                    b: uint8
                    @overload
                    def __init__(self, a: uint8 | None = ..., b: uint8 | None = ...): ...
                    @overload
                    def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
                x: __anonymous_0__
                @overload
                def __init__(self, x: __anonymous_0__ | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
            """,
            id="named nested",
        ),
        pytest.param(
            """
            struct Test {
                struct {
                    uint8 a;
                    uint8 b;
                } x[4];
            };
            """,
            """
            class Test(Structure):
                class __anonymous_0__(Structure):
                    a: uint8
                    b: uint8
                    @overload
                    def __init__(self, a: uint8 | None = ..., b: uint8 | None = ...): ...
                    @overload
                    def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
                x: Array[__anonymous_0__]
                @overload
                def __init__(self, x: Array[__anonymous_0__] | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
            """,
            id="named nested array",
        ),
    ],
)
def test_generate_structure_stub(cs: cstruct, cdef: str, expected: str) -> None:
    cs.load(cdef)

    assert stubgen.generate_structure_stub(cs.Test) == textwrap.dedent(expected).strip()


@pytest.mark.parametrize(
    ("cdef", "expected"),
    [
        pytest.param(
            """
            #define TEST 1

            enum TestEnum {
                A = 1,
                B = 2,
            };

            struct TestStruct {
                uint8 a;
            };
            """,
            """
            class cstruct(cstruct):
                TEST: int = ...
                class TestEnum(Enum):
                    A = ...
                    B = ...
                class TestStruct(Structure):
                    a: cstruct.uint8
                    @overload
                    def __init__(self, a: cstruct.uint8 | None = ...): ...
                    @overload
                    def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...

            """,
            id="cstruct stub",
        ),
        pytest.param(
            """
            typedef struct Test{
                uint8 a;
            } _test;
            """,
            """
            class cstruct(cstruct):
                class Test(Structure):
                    a: cstruct.uint8
                    @overload
                    def __init__(self, a: cstruct.uint8 | None = ...): ...
                    @overload
                    def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
                _test: TypeAlias = Test
            """,
            id="alias stub",
        ),
    ],
)
def test_generate_cstruct_stub(cs: cstruct, cdef: str, expected: str) -> None:
    cs.load(cdef)

    assert stubgen.generate_cstruct_stub(cs) == textwrap.dedent(expected).strip()


def test_generate_cstruct_stub_empty(cs: cstruct) -> None:
    expected = """
    class cstruct(cstruct):
        ...
    """

    assert stubgen.generate_cstruct_stub(cs) == textwrap.dedent(expected).strip()


def test_generate_file_stub(tmp_path: Path) -> None:
    test_content = """
        from dissect.cstruct import cstruct

        structure_def = \"\"\"
        struct Test {
            uint32  a;
            uint32  b;
        }
        \"\"\"

        c_structure = cstruct().load(structure_def)
    """
    test_file = tmp_path.joinpath("stub.py")
    test_file.write_text(textwrap.dedent(test_content).strip())

    expected = """
        # Generated by cstruct-stubgen
        from typing import overload, BinaryIO

        from typing_extensions import TypeAlias

        import dissect.cstruct as __cs__


        class _c_structure(__cs__.cstruct):
            class Test(__cs__.Structure):
                a: _c_structure.uint32
                b: _c_structure.uint32
                @overload
                def __init__(self, a: _c_structure.uint32 | None = ..., b: _c_structure.uint32 | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...
        c_structure: _c_structure
    """

    assert stubgen.generate_file_stub(test_file, tmp_path) == textwrap.dedent(expected).lstrip()

    assert stubgen.generate_file_stub(tmp_path.joinpath("unknown.py"), tmp_path) == ""

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

    # We don't want to strip all trailing whitespace in case it's part of the intended expected output
    # So just remove one newline from the final """ block
    assert stubgen.generate_enum_stub(cs.Test) == textwrap.dedent(expected).lstrip()[:-1]


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

    # We don't want to strip all trailing whitespace in case it's part of the intended expected output
    # So just remove one newline from the final """ block
    assert stubgen.generate_structure_stub(cs.Test) == textwrap.dedent(expected).lstrip()[:-1]


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
                TEST: Literal[1] = ...
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
        pytest.param(
            """
            typedef __u16 __fs16;
            typedef __u32 __fs32;
            typedef __u64 __fs64;

            struct Test {
                __fs16 a;
                __fs32 b;
                __fs64 c;
            };
            """,
            """
            class cstruct(cstruct):
                __fs16: TypeAlias = cstruct.uint16
                __fs32: TypeAlias = cstruct.uint32
                __fs64: TypeAlias = cstruct.uint64
                class Test(Structure):
                    a: cstruct.uint16
                    b: cstruct.uint32
                    c: cstruct.uint64
                    @overload
                    def __init__(self, a: cstruct.uint16 | None = ..., b: cstruct.uint32 | None = ..., c: cstruct.uint64 | None = ...): ...
                    @overload
                    def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...

            """,  # noqa: E501
            id="typedef stub",
        ),
        pytest.param(
            """
            #define INT 1
            #define FLOAT 2.0
            #define STRING "hello"
            #define BYTES b'c'
            """,
            """
            class cstruct(cstruct):
                INT: Literal[1] = ...
                FLOAT: Literal[2.0] = ...
                STRING: Literal['hello'] = ...
                BYTES: Literal[b'c'] = ...
            """,
            id="define literals",
        ),
    ],
)
def test_generate_cstruct_stub(cs: cstruct, cdef: str, expected: str) -> None:
    cs.load(cdef)

    # We don't want to strip all trailing whitespace in case it's part of the intended expected output
    # So just remove one newline from the final """ block
    assert stubgen.generate_cstruct_stub(cs) == textwrap.dedent(expected).lstrip()[:-1]


def test_generate_cstruct_stub_empty(cs: cstruct) -> None:
    expected = """
    class cstruct(cstruct):
        ...
    """

    assert stubgen.generate_cstruct_stub(cs) == textwrap.dedent(expected).strip()


def test_generate_file_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
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
        from typing import BinaryIO, Literal, overload

        import dissect.cstruct as __cs__
        from typing_extensions import TypeAlias

        class _c_structure(__cs__.cstruct):
            class Test(__cs__.Structure):
                a: _c_structure.uint32
                b: _c_structure.uint32
                @overload
                def __init__(self, a: _c_structure.uint32 | None = ..., b: _c_structure.uint32 | None = ...): ...
                @overload
                def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...

        # Technically `c_structure` is an instance of `_c_structure`, but then we can't use it in type hints
        c_structure: TypeAlias = _c_structure
    """

    assert stubgen.generate_file_stub(test_file, tmp_path) == textwrap.dedent(expected).lstrip()

    assert stubgen.generate_file_stub(tmp_path.joinpath("unknown.py"), tmp_path) == ""

    with monkeypatch.context() as m:
        caplog.set_level("DEBUG")
        for path in [tmp_path, test_file]:
            m.setattr("sys.argv", ["cstruct-stubgen", str(path)])

            stub_file = test_file.with_suffix(".pyi")
            stub_file.unlink(missing_ok=True)
            caplog.clear()

            stubgen.main()
            assert stubgen.generate_file_stub(test_file, tmp_path) == stub_file.read_text()
            assert f"Writing stub of file {test_file.resolve()} to {stub_file.name}" in caplog.text

        m.setattr("sys.argv", ["cstruct-stubgen", str(tmp_path.joinpath("unknown.py"))])
        caplog.clear()

        stubgen.main()
        assert stubgen.generate_file_stub(test_file, tmp_path) == stub_file.read_text()
        assert caplog.text == ""

import textwrap
from pathlib import Path

import pytest

from dissect.cstruct import cstruct
from dissect.cstruct.tools.stubify import stubify_cstruct, stubify_file, stubify_typedefs
from tests.utils import absolute_path


@pytest.mark.parametrize(
    ("definition", "name", "expected_stub"),
    [
        pytest.param(
            """
            struct Test {
                int a;
                int b;
            }
            """,
            "Test",
            """
            class Test(Structure):
                a: int32
                b: int32
                @overload
                def __init__(self, a: int32 = ..., b: int32 = ...): ...
                @overload
                def __init__(self, fh: bytes | bytearray | BinaryIO, /): ...
            """,
            id="standard structure",
        ),
        pytest.param(
            """
            struct Test {
                int a[];
            }
            """,
            "Test",
            """
            class Test(Structure):
                a: Array[int32]
                @overload
                def __init__(self, a: Array[int32] = ...): ...
                @overload
                def __init__(self, fh: bytes | bytearray | BinaryIO, /): ...
            """,
            id="array",
        ),
        pytest.param(
            """
            #define a 1
            #define b b"data"
            #define c "test"
            """,
            None,
            """
            a: int = ...
            b: bytes = ...
            c: str = ...
            """,
            id="definitions",
        ),
        pytest.param(
            """
            struct Test {
                int *a;
            }
            """,
            "Test",
            """
            class Test(Structure):
                a: Pointer[int32]
                @overload
                def __init__(self, a: Pointer[int32] = ...): ...
                @overload
                def __init__(self, fh: bytes | bytearray | BinaryIO, /): ...
            """,
            id="pointers",
        ),
        pytest.param(
            """
            enum Test {
                A = 1,
                B = 2,
                C = 2
            };
            """,
            "Test",
            """
            class Test(Enum, uint32):
                A = ...
                B = ...
                C = ...
            """,
            id="enums",
        ),
        pytest.param(
            """
            flag Test {
                A = 0x00001,
                B = 0x00002,
                C = 0x00004
            };
            """,
            "Test",
            """
            class Test(Flag, uint32):
                A = ...
                B = ...
                C = ...
            """,
            id="flags",
        ),
        pytest.param(
            """
            struct Test{
                union {
                    wchar a[];
                    char b[];
                }
            }
            """,
            "Test",
            """
            class Test(Structure):
                a: WcharArray
                b: CharArray
                @overload
                def __init__(self): ...
                @overload
                def __init__(self, fh: bytes | bytearray | BinaryIO, /): ...
            """,
            id="anonymous unions",
        ),
        pytest.param(
            """
            struct Test {
                union {
                    wchar a[];
                    char  b[];
                } u1;
            }
            """,
            "Test",
            """
            class Test(Structure):
                class _u1(Union):
                    a: WcharArray
                    b: CharArray
                    @overload
                    def __init__(self, a: WcharArray = ..., b: CharArray = ...): ...
                    @overload
                    def __init__(self, fh: bytes | bytearray | BinaryIO, /): ...
                u1: _u1
                @overload
                def __init__(self, u1: _u1 = ...): ...
                @overload
                def __init__(self, fh: bytes | bytearray | BinaryIO, /): ...
            """,
            id="defined union",
        ),
        pytest.param("""""", "", "...", id="empty"),
    ],
)
def test_to_type_stub(definition: str, name: str, expected_stub: str) -> None:
    structure = cstruct()
    ignore_list = list(structure.typedefs.keys())
    structure.load(definition)

    generated_stub = getattr(structure, name).cs if name else structure
    expected_stub = textwrap.dedent(expected_stub).strip()

    assert stubify_cstruct(generated_stub, ignore_type_defs=ignore_list).strip() == expected_stub


def test_to_type_stub_empty() -> None:
    structure = cstruct()
    ignore_list = list(structure.typedefs.keys())
    structure.load("")

    assert stubify_cstruct(structure, "test", ignore_type_defs=ignore_list) == "class test(cstruct):\n    ..."


def test_stubify_file() -> None:
    stub_file = absolute_path("data/stub_file.py")

    output = stubify_file(stub_file, stub_file.parent)

    assert output == absolute_path("data/stub_file.pyi").read_text()


def test_stubify_file_unknown_file(tmp_path: Path) -> None:
    assert stubify_file(tmp_path.joinpath("unknown_file.py"), tmp_path) == ""

    new_file = tmp_path.joinpath("new_file.py")
    new_file.touch()
    assert stubify_file(new_file, tmp_path) == ""


def test_stubify_typedef() -> None:
    structure = cstruct()
    expected_output = [
        "int8: TypeAlias = Packed[int]",
        "uint8: TypeAlias = Packed[int]",
        "int16: TypeAlias = Packed[int]",
        "uint16: TypeAlias = Packed[int]",
        "int32: TypeAlias = Packed[int]",
        "uint32: TypeAlias = Packed[int]",
        "int64: TypeAlias = Packed[int]",
        "uint64: TypeAlias = Packed[int]",
        "float16: TypeAlias = Packed[float]",
        "float: TypeAlias = Packed[float]",
        "double: TypeAlias = Packed[float]",
    ]

    assert stubify_typedefs(structure) == "\n".join(expected_output)
    assert stubify_typedefs(structure, ["int8"]) == "\n".join(expected_output[1:])
    assert stubify_typedefs(structure, ["int8", "double"]) == "\n".join(expected_output[1:-1])
    assert "float16: TypeAlias = Packed[float]" not in stubify_typedefs(structure, ["float16"])
    assert stubify_typedefs(structure, structure.typedefs.keys()) == ""

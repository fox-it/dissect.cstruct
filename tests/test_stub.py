import textwrap

import pytest

from dissect.cstruct import cstruct


@pytest.mark.parametrize(
    "definition, name, expected_stub",
    [
        (
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
                def __init__(self, a: int32=..., b: int32=...): ...
            """,
        ),
        (
            """
            struct Test {
                int a[];
            }
            """,
            "Test",
            """
            class Test(Structure):
                a: Array[int32]
                def __init__(self, a: Array[int32]=...): ...
            """,
        ),
        (
            """
            #define a 1
            #define b b"data"
            #define c "test"
            """,
            None,
            """
            a: int=...
            b: bytes=...
            c: str=...
            """,
        ),
        (
            """
            struct Test {
                int *a;
            }
            """,
            "Test",
            """
            class Test(Structure):
                a: Pointer[int32]
                def __init__(self, a: Pointer[int32]=...): ...
            """,
        ),
        (
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
        ),
        (
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
        ),
        (
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
                class __anonymous_0__(Union):
                    a: WcharArray
                    b: CharArray
                    def __init__(self, a: WcharArray=..., b: CharArray=...): ...
                a: WcharArray
                b: CharArray
                def __init__(self, __anonymous_0__: __anonymous_0__=...): ...
            """,
        ),
    ],
    ids=["standard structure", "array", "definitions", "pointers", "enums", "flags", "unions"],
)
def test_to_stub(definition: str, name: str, expected_stub: str):
    structure = cstruct()
    structure.load(definition)

    if name:
        generated_stub = getattr(structure, name).to_stub()
    else:
        generated_stub = structure.to_stub()
    expected_stub = textwrap.dedent(expected_stub).strip()

    assert expected_stub in generated_stub
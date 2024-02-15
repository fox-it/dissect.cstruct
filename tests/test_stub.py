import textwrap
from pathlib import Path

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
            class Test:
                a: int
                b: int
                def __call__(self, a: int=..., b: int=...): ...
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
            class Test:
                a: Array
                def __call__(self, a: Array=...): ...
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
            struct Test{
                union {
                    int a;
                    int b;
                }
            }
            """,
            "Test",
            """""",
        ),
    ],
    ids=["standard structure", "array", "definitions", "unions"],
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

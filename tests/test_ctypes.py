from __future__ import annotations

import ctypes as _ctypes
from typing import TYPE_CHECKING, Any

import pytest

from dissect.cstruct.cstruct import cstruct, ctypes, ctypes_type

if TYPE_CHECKING:
    from dissect.cstruct.types.base import BaseType

DUMMY_CS = cstruct()


@pytest.mark.parametrize(
    ("input", "expected"),
    [
        (DUMMY_CS.int8, _ctypes.c_int8),
        (DUMMY_CS.char, _ctypes.c_char),
        (DUMMY_CS.char[3], _ctypes.c_char * 3),
        (DUMMY_CS.int8[3], _ctypes.c_int8 * 3),
        (DUMMY_CS._make_pointer(DUMMY_CS.int8), _ctypes.POINTER(_ctypes.c_int8)),
    ],
)
def test_ctypes_type(input: type[BaseType], expected: Any) -> None:
    assert expected == ctypes_type(input)


def test_ctypes_type_exception() -> None:
    with pytest.raises(NotImplementedError):
        ctypes_type(DUMMY_CS.float16)


def test_ctypes_structure(cs: cstruct) -> None:
    cdef = """
    struct test {
        uint8  a;
        uint16 b;
    };
    """
    cs.load(cdef)

    ctypes_struct = ctypes(cs.test)
    assert issubclass(ctypes_struct, _ctypes.Structure)
    assert ctypes_struct._fields_ == [
        ("a", _ctypes.c_uint8),
        ("b", _ctypes.c_uint16),
    ]

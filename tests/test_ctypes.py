import ctypes as _ctypes
from typing import Any

import pytest

from dissect.cstruct import MetaType, cstruct, ctypes_type

DUMMY_CSTRUCT = cstruct()


# TODO: test structure/union


@pytest.mark.parametrize(
    "input, expected",
    [
        (DUMMY_CSTRUCT.int8, _ctypes.c_int8),
        (DUMMY_CSTRUCT.char, _ctypes.c_char),
        (DUMMY_CSTRUCT.char[3], _ctypes.c_char * 3),
        (DUMMY_CSTRUCT.int8[3], _ctypes.c_int8 * 3),
        (DUMMY_CSTRUCT._make_pointer(DUMMY_CSTRUCT.int8), _ctypes.POINTER(_ctypes.c_int8)),
    ],
)
def test_ctypes_type(input: MetaType, expected: Any) -> None:
    assert expected == ctypes_type(input)


def test_ctypes_type_exception() -> None:
    with pytest.raises(NotImplementedError):
        ctypes_type(DUMMY_CSTRUCT.float16)

import ctypes as _ctypes

import pytest
from dissect import cstruct

DUMMY_CSTRUCT = cstruct.cstruct()


# TODO: test structure/union


@pytest.mark.parametrize(
    "cstruct_type, ctypes_type",
    [
        (DUMMY_CSTRUCT.int8, _ctypes.c_int8),
        (DUMMY_CSTRUCT.char, _ctypes.c_char),
        (DUMMY_CSTRUCT.char[3], _ctypes.c_char * 3),
        (DUMMY_CSTRUCT.int8[3], _ctypes.c_int8 * 3),
        (DUMMY_CSTRUCT._make_pointer(DUMMY_CSTRUCT.int8), _ctypes.POINTER(_ctypes.c_int8)),
    ],
)
def test_ctypes_type(cstruct_type, ctypes_type):
    assert ctypes_type == cstruct.ctypes_type(cstruct_type)


def test_ctypes_type_exception():
    with pytest.raises(NotImplementedError):
        cstruct.ctypes_type(DUMMY_CSTRUCT.float16)

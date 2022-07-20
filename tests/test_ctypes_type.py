import pytest
import ctypes as _ctypes

from dissect import cstruct


DUMMY_CSTRUCT = cstruct.cstruct()
PACKED_TYPE_INT8 = cstruct.PackedType(DUMMY_CSTRUCT, "int8", 1, "b")


@pytest.mark.parametrize(
    "cstruct_type, ctypes_type",
    [
        (PACKED_TYPE_INT8, _ctypes.c_int8),
        (cstruct.CharType(DUMMY_CSTRUCT), _ctypes.c_char),
        (cstruct.Array(DUMMY_CSTRUCT, PACKED_TYPE_INT8, 3), _ctypes.c_int8 * 3),
        (cstruct.Pointer(DUMMY_CSTRUCT, PACKED_TYPE_INT8), _ctypes.POINTER(_ctypes.c_int8)),
    ],
)
def test_ctypes_type(cstruct_type, ctypes_type):
    assert ctypes_type == cstruct.ctypes_type(cstruct_type)


def test_ctypes_type_exception():
    with pytest.raises(NotImplementedError):
        cstruct.ctypes_type("FAIL")

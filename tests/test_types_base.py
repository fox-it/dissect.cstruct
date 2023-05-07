import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exceptions import ArraySizeError


def test_array_size_mismatch(cs: cstruct):
    with pytest.raises(ArraySizeError):
        cs.uint8[2]([1, 2, 3]).dumps()

    assert cs.uint8[2]([1, 2]).dumps()

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dissect.cstruct.exception import DefinitionError, Error, ReadError, WriteError
from tests.util import verify_compiled

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct


@pytest.mark.parametrize("exception", [EOFError, Error])
def test_eof_error(cs: cstruct, compiled: bool, exception: type[Exception]) -> None:
    """Test that a short read can be caught as the built-in ``EOFError`` and a cstruct error."""
    cdef = """
    struct test {
        uint32  a;
        uint16  b;
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    with pytest.raises(exception, match=r"^Read 1 bytes, but expected 4$"):
        cs.uint32(b"\x00")

    # The compiled structure reads both fields at once
    message = r"^Read 5 bytes, but expected 6$" if compiled else r"^Read 1 bytes, but expected 2$"
    with pytest.raises(exception, match=message) as exc_info:
        cs.test(b"\x00" * 5)

    assert not isinstance(exc_info.value, ValueError)


def test_value_error(cs: cstruct, compiled: bool) -> None:
    """Test that an invalid definition, data or value can be caught as a ``ValueError``."""
    cdef = """
    struct test {
        uint8   n;
        uint8   a[1 / n];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test, compiled)

    with pytest.raises(ValueError, match=r"(?m)^line 1: Duplicate type: test$") as exc_info:
        cs.load("struct test { uint8 a; };")

    assert isinstance(exc_info.value, DefinitionError)

    with pytest.raises(ValueError, match=r"^Invalid array size '1 / n': ") as exc_info:
        cs.test(b"\x00")

    assert isinstance(exc_info.value, ReadError)

    with pytest.raises(ValueError, match=r"^Cannot write uint8: ") as exc_info:
        cs.uint8.dumps(256)

    assert isinstance(exc_info.value, WriteError)

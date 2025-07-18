from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.types.base import BaseType


@pytest.mark.parametrize(
    "name",
    [name for name in cstruct().typedefs if " " not in name],
)
def test_cstruct_type_annotation(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        patch("typing.TYPE_CHECKING", True),
        patch("dissect.cstruct.types.base.MetaType.__getitem__", lambda self, item: self),
    ):
        for module in [module for module in sys.modules if module in ("dissect.cstruct.cstruct")]:
            monkeypatch.delitem(sys.modules, module)

        from dissect.cstruct import cstruct  # noqa: PLC0415

        if name.startswith("__"):
            name = f"_cstruct{name}"

        assert issubclass(getattr(cstruct, name), BaseType), f"Missing type annotation for {name}"

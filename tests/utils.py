from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dissect.cstruct import Structure


def verify_compiled(struct: type[Structure], compiled: bool) -> bool:
    return struct.__compiled__ == compiled

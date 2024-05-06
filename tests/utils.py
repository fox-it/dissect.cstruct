from __future__ import annotations

from dissect.cstruct import Structure


def verify_compiled(struct: type[Structure], compiled: bool) -> bool:
    return struct.__compiled__ == compiled

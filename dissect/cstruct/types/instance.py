from io import BytesIO
from typing import Any, BinaryIO, Dict

from dissect.cstruct.types import BaseType


class Instance:
    """Holds parsed structure data."""

    __slots__ = ("_type", "_values", "_sizes", "owner")

    def __init__(self, type_: BaseType, values: Dict[str, Any], sizes: Dict[str, int] = None):
        # Done in this manner to check if the attr is in the lookup
        object.__setattr__(self, "_type", type_)
        object.__setattr__(self, "_values", values)
        object.__setattr__(self, "_sizes", sizes)
        self.owner = None
        for key, value in values.items():
            Instance.set_owner(self, value)

    @classmethod
    def set_owner(cls, self, value):
        if isinstance(value, Instance):
            value.owner = self
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                Instance.set_owner(self, item)

    def __getattr__(self, attr: str) -> Any:
        try:
            return self._values[attr]
        except KeyError:
            raise AttributeError(f"Invalid attribute: {attr}")

    def __setattr__(self, attr: str, value: Any) -> None:
        if attr in self._type.lookup:
            self._values[attr] = value
            Instance.set_owner(self, value)
            self.changed(attr)
        else:
            super().__setattr__(attr, value)

    def __getitem__(self, item: str) -> Any:
        return self._values[item]

    def __contains__(self, attr: str) -> bool:
        return attr in self._values

    def __repr__(self) -> str:
        values = ", ".join([f"{k}={hex(v) if isinstance(v, int) else repr(v)}" for k, v in self._values.items()])
        return f"<{self._type.name} {values}>"

    def __len__(self) -> int:
        return len(self.dumps())

    def __bytes__(self) -> bytes:
        return self.dumps()

    def _size(self, field: str) -> int:
        return self._sizes[field]

    def write(self, stream: BinaryIO) -> int:
        """Write this structure to a writable file-like object.

        Args:
            fh: File-like objects that supports writing.

        Returns:
            The amount of bytes written.
        """
        return self._type.write(stream, self)

    def dumps(self) -> bytes:
        """Dump this structure to a byte string.

        Returns:
            The raw bytes of this structure.
        """
        s = BytesIO()
        self.write(s)
        return s.getvalue()

    def changed(self, attr):
        if self._type.__class__.__name__ == 'Union':
            dump = BytesIO()
            attr_field = None
            for field in self._type.fields:
                dump.seek(0)
                if field.offset:
                    dump.seek(field.offset)
                if field.type.__class__.__name__ in ('Structure', 'Union') and field.type.anonymous:
                    field.type._write(dump, self)
                else:
                    if field.name != attr:
                        field.type._write(dump, getattr(self, field.name))
                    else:
                        attr_field = field
            if attr_field is not None:
                dump.seek(0)
                if attr_field.offset:
                    dump.seek(attr_field.offset)
                attr_field.type._write(dump, getattr(self, attr))
            dump.seek(0)
            self._type._read(dump, instance=self)
        if isinstance(self.owner, Instance):
            for field in self.owner._type.fields:
                if getattr(self.owner, field.name) is self:
                    self.owner.changed(field.name)
                    break

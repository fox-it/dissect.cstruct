from __future__ import annotations

from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class Expression:
    """Expression parser for simple calculations in definitions."""

    operators = [
        ("*", lambda a, b: a * b),
        ("/", lambda a, b: a // b),
        ("%", lambda a, b: a % b),
        ("+", lambda a, b: a + b),
        ("-", lambda a, b: a - b),
        (">>", lambda a, b: a >> b),
        ("<<", lambda a, b: a << b),
        ("&", lambda a, b: a & b),
        ("^", lambda a, b: a ^ b),
        ("|", lambda a, b: a | b),
    ]

    def __init__(self, cstruct: cstruct, expression: str):
        self.cstruct = cstruct
        self.expression = expression

    def __repr__(self) -> str:
        return self.expression

    def evaluate(self, context: Dict[str, int] = None) -> int:
        context = context or {}
        levels = []
        buf = ""

        for i in range(len(self.expression)):
            if self.expression[i] == "(":
                levels.append(buf)
                buf = ""
                continue

            if self.expression[i] == ")":
                if levels[-1] == "sizeof":
                    value = len(self.cstruct.resolve(buf))
                    levels[-1] = ""
                else:
                    value = self.evaluate_part(buf, context)
                buf = levels.pop()
                buf += str(value)
                continue

            buf += self.expression[i]

        return self.evaluate_part(buf, context)

    def evaluate_part(self, buf: str, context: Dict[str, int]) -> int:
        buf = buf.strip()

        # Very simple way to support an expression(part) that is a single,
        # negative value. To use negative values in more complex expressions,
        # they must be wrapped in brackets, e.g.: 2 * (-5).
        #
        # To have full support for the negation operator a proper expression
        # parser must be build.
        if buf.startswith("-") and buf[1:].isnumeric():
            return int(buf)

        for operator in self.operators:
            if operator[0] in buf:
                a, b = buf.rsplit(operator[0], 1)

                return operator[1](self.evaluate_part(a, context), self.evaluate_part(b, context))

        if buf in context:
            return context[buf]

        if buf.startswith("0x"):
            return int(buf, 16)

        if buf in self.cstruct.consts:
            return int(self.cstruct.consts[buf])

        return int(buf)

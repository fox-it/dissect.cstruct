from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dissect.cstruct.exception import ExpressionParserError
from dissect.cstruct.lexer import IDENTIFIER_TYPES, Lexer, TokenCursor, TokenType
from dissect.cstruct.util import offsetof, sizeof

if TYPE_CHECKING:
    from collections.abc import Callable

    from dissect.cstruct import cstruct
    from dissect.cstruct.lexer import Token

_MISSING = object()

BINARY_OPERATORS: dict[TokenType, Callable[[int, int], int]] = {
    TokenType.PIPE: lambda a, b: a | b,
    TokenType.CARET: lambda a, b: a ^ b,
    TokenType.AMPERSAND: lambda a, b: a & b,
    TokenType.LSHIFT: lambda a, b: a << b,
    TokenType.RSHIFT: lambda a, b: a >> b,
    TokenType.PLUS: lambda a, b: a + b,
    TokenType.MINUS: lambda a, b: a - b,
    TokenType.STAR: lambda a, b: a * b,
    TokenType.SLASH: lambda a, b: a // b,
    TokenType.PERCENT: lambda a, b: a % b,
}

UNARY_OPERATORS: dict[TokenType, Callable[[int], int]] = {
    TokenType.UNARY_MINUS: lambda a: -a,
    TokenType.TILDE: lambda a: ~a,
}

OPERATORS = set(BINARY_OPERATORS.keys()) | set(UNARY_OPERATORS.keys())

OPERATOR_SOURCE: dict[TokenType, str] = {
    TokenType.PIPE: "|",
    TokenType.CARET: "^",
    TokenType.AMPERSAND: "&",
    TokenType.LSHIFT: "<<",
    TokenType.RSHIFT: ">>",
    TokenType.PLUS: "+",
    TokenType.MINUS: "-",
    TokenType.STAR: "*",
    TokenType.SLASH: "//",
    TokenType.PERCENT: "%",
    TokenType.UNARY_MINUS: "-",
    TokenType.TILDE: "~",
}

FUNCTION_TOKENS = {
    TokenType.SIZEOF: 1,
    TokenType.OFFSETOF: 2,
}

PRECEDENCE_LEVELS = {
    TokenType.PIPE: 0,
    TokenType.CARET: 1,
    TokenType.AMPERSAND: 2,
    TokenType.LSHIFT: 3,
    TokenType.RSHIFT: 3,
    TokenType.PLUS: 4,
    TokenType.MINUS: 4,
    TokenType.STAR: 5,
    TokenType.SLASH: 5,
    TokenType.PERCENT: 5,
    TokenType.UNARY_MINUS: 6,
    TokenType.TILDE: 6,
    # Functions
    TokenType.SIZEOF: 7,
    TokenType.OFFSETOF: 7,
}


def _sizeof(cs: cstruct, name: str) -> int:
    return sizeof(cs.resolve(name))


def _offsetof(cs: cstruct, name: str, field: str) -> int:
    return offsetof(cs.resolve(name), field)


FUNCTIONS: dict[TokenType, Callable[..., int]] = {
    TokenType.SIZEOF: _sizeof,
    TokenType.OFFSETOF: _offsetof,
}


def _error(msg: str, line: int) -> ExpressionParserError:
    return ExpressionParserError(f"line {line}: {msg}")


def _identifier(cs: cstruct, context: dict[str, Any], ident: str, line: int) -> int:
    """Resolve an identifier to an integer value."""
    obj = None
    for i, part in enumerate(ident.split(".")):
        if i == 0:
            if part in context:
                obj = context[part]
            elif part in cs.consts:
                obj = cs.consts[part]
            elif part in cs.types:
                obj = cs.types[part]
            else:
                raise _error(f"Unknown identifier: '{ident}'", line)
        else:
            obj = obj.get(part, _MISSING) if isinstance(obj, dict) else getattr(obj, part, _MISSING)
            if obj is _MISSING:
                raise _error(f"Unknown identifier: '{ident}'", line)

    try:
        return int(obj)
    except (ValueError, TypeError):
        raise _error(f"Identifier '{ident}' does not resolve to an integer", line)


# Globals used by the source code of an expression
SOURCE_GLOBALS = {func.__name__: func for func in (_identifier, *FUNCTIONS.values())}


class _Evaluator:
    """Calculates the value of an expression."""

    def __init__(self, cs: cstruct, context: dict[str, Any]):
        self.cs = cs
        self.context = context

    def number(self, value: int) -> int:
        return value

    def identifier(self, ident: str, token: Token) -> int:
        return _identifier(self.cs, self.context, ident, token.line)

    def unary(self, operator: TokenType, value: int) -> int:
        return UNARY_OPERATORS[operator](value)

    def binary(self, operator: TokenType, left: int, right: int) -> int:
        return BINARY_OPERATORS[operator](left, right)

    def function(self, operator: TokenType, args: list[str]) -> int:
        return FUNCTIONS[operator](self.cs, *args)


class _SourceBuilder:
    """Builds the Python source code of an expression."""

    def __init__(self, variables: dict[str, str], context: str):
        self.variables = variables
        self.context = context

    def number(self, value: int) -> str:
        return repr(value)

    def identifier(self, ident: str, token: Token) -> str:
        if ident in self.variables:
            return self.variables[ident]
        return f"_identifier(cs, {self.context}, {ident!r}, {token.line})"

    def unary(self, operator: TokenType, value: str) -> str:
        return f"({OPERATOR_SOURCE[operator]}{value})"

    def binary(self, operator: TokenType, left: str, right: str) -> str:
        return f"({left} {OPERATOR_SOURCE[operator]} {right})"

    def function(self, operator: TokenType, args: list[str]) -> str:
        return f"{FUNCTIONS[operator].__name__}(cs, {', '.join(map(repr, args))})"


def precedence(o1: TokenType, o2: TokenType) -> bool:
    # Unary (prefix) operators are right-associative, so use strict greater-than
    if o2 in UNARY_OPERATORS:
        return PRECEDENCE_LEVELS[o1] > PRECEDENCE_LEVELS[o2]
    return PRECEDENCE_LEVELS[o1] >= PRECEDENCE_LEVELS[o2]


class Expression(TokenCursor):
    """Expression parser for calculations in definitions."""

    def __init__(self, expression: str):
        self.expression = expression

        tokens = Lexer(expression).tokenize()
        super().__init__(tokens)
        self._stack: list[TokenType] = []
        self._queue: list[int | str] = []

    def __repr__(self) -> str:
        return self.expression

    def _reset(self) -> None:
        """Reset the expression state for a new input."""
        self._reset_cursor()
        self._stack = []
        self._queue = []

    def _error(self, msg: str, *, token: Token | None = None) -> ExpressionParserError:
        return _error(msg, (token if token is not None else self._current()).line)

    def _evaluate_expression(self, backend: _Evaluator | _SourceBuilder) -> None:
        operator = self._stack.pop(-1)
        result = 0

        if operator in UNARY_OPERATORS:
            if len(self._queue) < 1:
                raise ExpressionParserError("Invalid expression: not enough operands")

            result = backend.unary(operator, self._queue.pop(-1))
        elif operator in BINARY_OPERATORS:
            if len(self._queue) < 2:
                raise ExpressionParserError("Invalid expression: not enough operands")

            right = self._queue.pop(-1)
            left = self._queue.pop(-1)
            result = backend.binary(operator, left, right)
        elif operator in FUNCTION_TOKENS:
            num_args = FUNCTION_TOKENS[operator]
            if len(self._queue) < num_args:
                raise ExpressionParserError("Invalid expression: not enough operands")

            args = [self._queue.pop(-1) for _ in range(num_args)][::-1]
            result = backend.function(operator, args)

        self._queue.append(result)

    def evaluate(self, cs: cstruct, context: dict[str, int] | None = None) -> int:
        """Evaluates an expression using a Shunting-Yard implementation.

        Args:
            cs: The cstruct instance to evaluate against.
            context: The context to evaluate against.
        """
        return self._evaluate(_Evaluator(cs, context or {}))

    def source(self, variables: dict[str, str] | None = None, context: str = "context") -> str:
        """Return the Python source code of this expression.

        Args:
            variables: The source code map for accessing local variables.
            context: The symbol name of the context.
        """
        return self._evaluate(_SourceBuilder(variables or {}, context))

    def _evaluate(self, backend: _Evaluator | _SourceBuilder) -> int | str:
        self._reset()

        while (token := self._current()).type != TokenType.EOF:
            if token.type == TokenType.NUMBER:
                self._queue.append(backend.number(int(self._take().value, 0)))

            elif token.type in OPERATORS:
                while (
                    len(self._stack) != 0
                    and self._stack[-1] != TokenType.LPAREN
                    and precedence(self._stack[-1], token.type)
                ):
                    self._evaluate_expression(backend)

                self._stack.append(self._take().type)

            elif token.type in FUNCTION_TOKENS:
                func = self._take().type
                self._stack.append(func)

                self._expect(TokenType.LPAREN)

                num_args = FUNCTION_TOKENS[func]
                while num_args > 1:
                    self._queue.append(self._collect_until(TokenType.COMMA))
                    self._expect(TokenType.COMMA)
                    num_args -= 1

                self._queue.append(self._collect_until(TokenType.RPAREN))
                self._expect(TokenType.RPAREN)

                # Evaluate immediately
                self._evaluate_expression(backend)

            elif token.type in IDENTIFIER_TYPES:
                self._queue.append(backend.identifier(self._take().value, token))

            elif token.type == TokenType.LPAREN:
                if self._previous().type == TokenType.NUMBER:
                    raise self._error(
                        f"Parser expected sizeof or an arethmethic operator instead got: '{self._previous().value}'",
                        token=self._previous(),
                    )

                self._stack.append(self._take().type)

            elif token.type == TokenType.RPAREN:
                if self._previous().type == TokenType.LPAREN:
                    raise self._error(
                        "Parser expected an expression, instead received empty parenthesis.",
                        token=self._previous(),
                    )

                if len(self._stack) == 0:
                    raise self._error("Mismatched parentheses")

                while self._stack[-1] != TokenType.LPAREN:
                    self._evaluate_expression(backend)
                    if len(self._stack) == 0:
                        raise self._error("Mismatched parentheses")

                self._stack.pop(-1)  # Pop the '('
                self._take()

            else:
                raise self._error(f"Unmatched token: '{token.value}'", token=token)

        while len(self._stack) != 0:
            if TokenType.LPAREN in self._stack:
                raise self._error("Mismatched parentheses")
            self._evaluate_expression(backend)

        if len(self._queue) != 1:
            raise self._error("Invalid expression: too many operands")

        return self._queue[0]

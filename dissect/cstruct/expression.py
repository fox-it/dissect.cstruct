from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dissect.cstruct.exception import ExpressionParserError, UnknownIdentifierError
from dissect.cstruct.lexer import IDENTIFIER_TYPES, Lexer, TokenCursor, TokenType, join_tokens
from dissect.cstruct.util import offsetof, sizeof

if TYPE_CHECKING:
    from collections.abc import Callable

    from dissect.cstruct import cstruct
    from dissect.cstruct.lexer import Token
    from dissect.cstruct.types import BaseType

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


def _resolve_type(cs: cstruct, name: str, pointers: int, dimensions: list[int]) -> type[BaseType]:
    """Resolve the type of ``sizeof`` or ``offsetof`` like the type of a field, e.g. ``uint8 *[4]``."""
    type_ = cs.resolve(name)
    for _ in range(pointers):
        type_ = cs._make_pointer(type_)
    for count in reversed(dimensions):
        type_ = cs._make_array(type_, count)
    return type_


def _sizeof(type_: type[BaseType]) -> int:
    try:
        return sizeof(type_)
    except TypeError:
        raise ExpressionParserError(f"Type '{type_.__name__}' has a dynamic size") from None


def _offsetof(type_: type[BaseType], field: str) -> int:
    try:
        return offsetof(type_, field)
    except (TypeError, ValueError) as e:
        raise ExpressionParserError(str(e)) from None


FUNCTIONS: dict[TokenType, Callable[..., int]] = {
    TokenType.SIZEOF: _sizeof,
    TokenType.OFFSETOF: _offsetof,
}


def _identifier(cs: cstruct, context: dict[str, Any], ident: str) -> int:
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
                raise UnknownIdentifierError(f"Unknown identifier: '{ident}'")
        else:
            obj = obj.get(part, _MISSING) if isinstance(obj, dict) else getattr(obj, part, _MISSING)
            if obj is _MISSING:
                raise UnknownIdentifierError(f"Unknown identifier: '{ident}'")

    try:
        return int(obj)
    except (ValueError, TypeError):
        raise ExpressionParserError(f"Identifier '{ident}' does not resolve to an integer")


# Globals used by the source code of an expression
SOURCE_GLOBALS = {func.__name__: func for func in (_identifier, _resolve_type, *FUNCTIONS.values())}


class _Evaluator:
    """Calculates the value of an expression."""

    def __init__(self, cs: cstruct, context: dict[str, Any]):
        self.cs = cs
        self.context = context

    def number(self, value: int) -> int:
        return value

    def identifier(self, ident: str) -> int:
        return _identifier(self.cs, self.context, ident)

    def unary(self, operator: TokenType, value: int) -> int:
        return UNARY_OPERATORS[operator](value)

    def binary(self, operator: TokenType, left: int, right: int) -> int:
        return BINARY_OPERATORS[operator](left, right)

    def function(self, operator: TokenType, args: tuple[Any, ...]) -> int:
        (name, pointers, dimensions), *fields = args
        if pointers or dimensions:
            counts = [dimension._run(self) for dimension in dimensions]
            type_ = _resolve_type(self.cs, name, pointers, counts)
        else:
            type_ = self.cs.resolve(name)
        return FUNCTIONS[operator](type_, *fields)


class _SourceBuilder:
    """Builds the Python source code of an expression."""

    def __init__(self, variables: dict[str, str], context: str):
        self.variables = variables
        self.context = context

    def number(self, value: int) -> str:
        return repr(value)

    def identifier(self, ident: str) -> str:
        if ident in self.variables:
            return self.variables[ident]
        return f"_identifier(cs, {self.context}, {ident!r})"

    def unary(self, operator: TokenType, value: str) -> str:
        return f"({OPERATOR_SOURCE[operator]}{value})"

    def binary(self, operator: TokenType, left: str, right: str) -> str:
        return f"({left} {OPERATOR_SOURCE[operator]} {right})"

    def function(self, operator: TokenType, args: tuple[Any, ...]) -> str:
        (name, pointers, dimensions), *fields = args
        if pointers or dimensions:
            counts = ", ".join(dimension._run(self) for dimension in dimensions)
            type_ = f"_resolve_type(cs, {name!r}, {pointers}, [{counts}])"
        else:
            type_ = f"cs.resolve({name!r})"
        return f"{FUNCTIONS[operator].__name__}({', '.join([type_, *map(repr, fields)])})"


def precedence(o1: TokenType, o2: TokenType) -> bool:
    # Unary (prefix) operators are right-associative, so use strict greater-than
    if o2 in UNARY_OPERATORS:
        return PRECEDENCE_LEVELS[o1] > PRECEDENCE_LEVELS[o2]
    return PRECEDENCE_LEVELS[o1] >= PRECEDENCE_LEVELS[o2]


class Expression(TokenCursor):
    """Expression parser for calculations in definitions.

    The expression is parsed when it's created, so a syntax error raises right away.
    Calculating with invalid operands (e.g. division by zero) raises an exception when evaluating.

    Raises:
        ExpressionParserError: If the expression is invalid.
    """

    def __init__(self, expression: str):
        self.expression = expression

        tokens = Lexer(expression).tokenize()
        super().__init__(tokens)
        self._postfix = self._parse()

    def __repr__(self) -> str:
        return self.expression

    def _error(self, msg: str, *, token: Token | None = None) -> ExpressionParserError:
        return ExpressionParserError(msg)

    def evaluate(self, cs: cstruct, context: dict[str, int] | None = None) -> int:
        """Evaluates an expression.

        Args:
            cs: The cstruct instance to evaluate against.
            context: The context to evaluate against.
        """
        return self._run(_Evaluator(cs, context or {}))

    def source(self, variables: dict[str, str] | None = None, context: str = "context") -> str:
        """Return the Python source code of this expression.

        Args:
            variables: The source code map for accessing local variables.
            context: The symbol name of the context.
        """
        return self._run(_SourceBuilder(variables or {}, context))

    def _run(self, backend: _Evaluator | _SourceBuilder) -> int | str:
        """Calculate the expression from its postfix notation."""
        stack = []

        for type_, value in self._postfix:
            if type_ in BINARY_OPERATORS:
                right = stack.pop()
                stack[-1] = backend.binary(type_, stack[-1], right)
            elif type_ in UNARY_OPERATORS:
                stack[-1] = backend.unary(type_, stack[-1])
            elif type_ in FUNCTION_TOKENS:
                stack.append(backend.function(type_, value))
            elif type_ == TokenType.NUMBER:
                stack.append(backend.number(value))
            else:
                stack.append(backend.identifier(value))

        return stack[0]

    def _pop_operator(self, stack: list[TokenType], output: list[tuple[TokenType, Any]], operands: int) -> int:
        """Move an operator from the stack to the output, and return the amount of values the output calculates."""
        operator = stack.pop(-1)
        needed = 2 if operator in BINARY_OPERATORS else 1
        if operands < needed:
            raise ExpressionParserError("Invalid expression: not enough operands")

        output.append((operator, None))
        return operands - needed + 1

    def _parse_type_name(self) -> tuple[str, int, list[Expression]]:
        """Parse a type name like the type of a field, e.g. ``struct header *[4]``."""
        # Types share a single namespace, so the kind of a type is optional
        self._match(TokenType.STRUCT, TokenType.UNION, TokenType.ENUM, TokenType.FLAG)

        if not self._at(TokenType.IDENTIFIER):
            raise self._error(f"expected a type name, got {self._describe(self._current())}")

        # E.g. unsigned long long
        parts = []
        while token := self._match(TokenType.IDENTIFIER):
            parts.append(token.value)

        pointers = 0
        while self._match(TokenType.STAR):
            pointers += 1

        dimensions = []
        while self._match(TokenType.LBRACKET):
            if not (tokens := self._collect_until(TokenType.RBRACKET)):
                raise self._error("expected an array size")
            self._expect(TokenType.RBRACKET)
            dimensions.append(Expression(join_tokens(tokens)))

        return " ".join(parts), pointers, dimensions

    def _parse(self) -> list[tuple[TokenType, Any]]:
        """Convert the expression to postfix notation using a Shunting-Yard implementation."""
        output: list[tuple[TokenType, Any]] = []
        stack: list[TokenType] = []
        # The amount of values the output calculates
        operands = 0

        while (token := self._current()).type != TokenType.EOF:
            if token.type == TokenType.NUMBER:
                output.append((TokenType.NUMBER, int(self._take().value, 0)))
                operands += 1

            elif token.type in OPERATORS:
                while len(stack) != 0 and stack[-1] != TokenType.LPAREN and precedence(stack[-1], token.type):
                    operands = self._pop_operator(stack, output, operands)

                stack.append(self._take().type)

            elif token.type in FUNCTION_TOKENS:
                func = self._take().type

                self._expect(TokenType.LPAREN)

                # The type, followed by the names of fields
                args = [self._parse_type_name()]
                for _ in range(FUNCTION_TOKENS[func] - 1):
                    self._expect(TokenType.COMMA)
                    if not self._at(*IDENTIFIER_TYPES):
                        raise self._error(f"expected a field name, got {self._describe(self._current())}")
                    args.append(self._take().value)

                self._expect(TokenType.RPAREN)

                output.append((func, tuple(args)))
                operands += 1

            elif token.type in IDENTIFIER_TYPES:
                output.append((token.type, self._take().value))
                operands += 1

            elif token.type == TokenType.LPAREN:
                if self._previous().type == TokenType.NUMBER:
                    raise self._error(
                        f"Parser expected sizeof or an arithmethic operator instead got: '{self._previous().value}'",
                        token=self._previous(),
                    )

                stack.append(self._take().type)

            elif token.type == TokenType.RPAREN:
                if self._previous().type == TokenType.LPAREN:
                    raise self._error(
                        "Parser expected an expression, instead received empty parenthesis.",
                        token=self._previous(),
                    )

                if len(stack) == 0:
                    raise self._error("Mismatched parentheses")

                while stack[-1] != TokenType.LPAREN:
                    operands = self._pop_operator(stack, output, operands)
                    if len(stack) == 0:
                        raise self._error("Mismatched parentheses")

                stack.pop(-1)  # Pop the '('
                self._take()

            else:
                raise self._error(f"Unmatched token: '{token.value}'", token=token)

        while len(stack) != 0:
            if TokenType.LPAREN in stack:
                raise self._error("Mismatched parentheses")
            operands = self._pop_operator(stack, output, operands)

        if operands == 0:
            raise self._error("Invalid expression: not enough operands")

        if operands > 1:
            raise self._error("Invalid expression: too many operands")

        return output

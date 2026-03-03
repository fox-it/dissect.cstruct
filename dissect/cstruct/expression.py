from __future__ import annotations

from typing import TYPE_CHECKING

from dissect.cstruct.exceptions import ExpressionParserError
from dissect.cstruct.lexer import _IDENTIFIER_TYPES, Lexer, Token, TokenCursor, TokenType
from dissect.cstruct.utils import offsetof, sizeof

if TYPE_CHECKING:
    from collections.abc import Callable

    from dissect.cstruct import cstruct


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


def precedence(o1: TokenType, o2: TokenType) -> bool:
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
        return ExpressionParserError(f"line {(token if token is not None else self._current()).line}: {msg}")

    def _evaluate_expression(self, cs: cstruct) -> None:
        operator = self._stack.pop(-1)
        result = 0

        if operator in UNARY_OPERATORS:
            if len(self._queue) < 1:
                raise ExpressionParserError("Invalid expression: not enough operands")

            result = UNARY_OPERATORS[operator](self._queue.pop(-1))
        elif operator in BINARY_OPERATORS:
            if len(self._queue) < 2:
                raise ExpressionParserError("Invalid expression: not enough operands")

            right = self._queue.pop(-1)
            left = self._queue.pop(-1)
            result = BINARY_OPERATORS[operator](left, right)
        elif operator in FUNCTION_TOKENS:
            num_args = FUNCTION_TOKENS[operator]
            if len(self._queue) < num_args:
                raise ExpressionParserError("Invalid expression: not enough operands")

            args = [self._queue.pop(-1) for _ in range(num_args)][::-1]
            if operator == TokenType.SIZEOF:
                type_ = cs.resolve(args[0])
                result = sizeof(type_)
            elif operator == TokenType.OFFSETOF:
                type_ = cs.resolve(args[0])
                result = offsetof(type_, args[1])

        self._queue.append(result)

    def evaluate(self, cs: cstruct, context: dict[str, int] | None = None) -> int:
        """Evaluates an expression using a Shunting-Yard implementation."""
        self._reset()
        context = context or {}

        while (token := self._current()).type != TokenType.EOF:
            if token.type == TokenType.NUMBER:
                self._queue.append(int(self._take().value, 0))

            elif token.type in OPERATORS:
                while (
                    len(self._stack) != 0
                    and self._stack[-1] != TokenType.LPAREN
                    and precedence(self._stack[-1], token.type)
                ):
                    self._evaluate_expression(cs)

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
                self._evaluate_expression(cs)

            elif token.type in _IDENTIFIER_TYPES:
                if token.value in context:
                    self._queue.append(int(context[self._take().value]))

                elif token.value in cs.consts:
                    self._queue.append(int(cs.consts[self._take().value]))

                else:
                    raise self._error(f"Unknown identifier: '{token.value}'", token=token)

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
                    self._evaluate_expression(cs)
                    if len(self._stack) == 0:
                        raise self._error("Mismatched parentheses")

                self._stack.pop(-1)  # Pop the '('
                self._take()

            else:
                raise self._error(f"Unmatched token: '{token.value}'", token=token)

        while len(self._stack) != 0:
            if TokenType.LPAREN in self._stack:
                raise self._error("Mismatched parentheses")
            self._evaluate_expression(cs)

        if len(self._queue) != 1:
            raise self._error("Invalid expression: too many operands")

        return self._queue[0]

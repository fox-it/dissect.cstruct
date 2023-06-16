from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict

from dissect.cstruct.exceptions import ExpressionParserError

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class ExpressionTokenizer:
    def __init__(self, expression: str):
        self.expression = expression
        self.i: int = 0
        self.tokens = []

    def equal(self, token: str, expected: str) -> bool:
        if isinstance(expected, set):
            return token in expected
        else:
            return token == expected

    def alnum(self, token: str) -> bool:
        return token.isalnum()

    def alpha(self, token: str) -> bool:
        return token.isalpha()

    def digit(self, token: str) -> bool:
        return token.isdigit()

    def digitHex(self, token: str) -> bool:
        return token.isdigit() or token in {"a", "b", "c", "d", "e", "f", "A", "B", "C", "D", "E", "F"}

    def operator(self, token) -> bool:
        op: set[str] = {"*", "/", "+", "-", "%", "&", "^", "|", "(", ")", "~"}
        return token in op

    def match(self, func: Callable = None, expected: str = None, consume: bool = True, append: bool = True) -> bool:
        if self.outOfBounds():
            return False

        token: str = self.getToken()

        if expected and self.equal(token, expected):
            if append:
                self.tokens.append(token)
            if consume:
                self.consume()
            return True

        if func and func(token):
            if append:
                self.tokens.append(token)
            if consume:
                self.consume()
            return True

        return False

    def consume(self):
        self.i += 1

    def outOfBounds(self):
        return self.i >= len(self.expression)

    def getToken(self) -> str:
        if self.i >= len(self.expression):
            raise Exception(f"Out of bounds index: {self.i}, length: {len(self.expression)}")
        return self.expression[self.i]

    def tokenize(self) -> list[str]:
        token = ""

        # Loop over expression runs in linear time
        while not self.outOfBounds():
            # if token is a single character operand add it to tokens
            if self.match(func=self.operator):
                continue

            # if token is a single digit, keep looping over expression and build the number
            elif self.match(self.digit, consume=False, append=False):
                token += self.getToken()
                self.consume()

                # support for binary and hexadecimal notation
                if self.match(expected="x", consume=False, append=False) or self.match(
                    expected="b", consume=False, append=False
                ):
                    token += self.getToken()
                    self.consume()
                while self.match(self.digitHex, consume=False, append=False):
                    token += self.getToken()
                    self.consume()
                    if self.outOfBounds():
                        break

                # checks for suffixes in numbers
                if self.match(expected={"u", "U"}, consume=False, append=False):
                    self.consume()
                    self.match(expected={"l", "L"}, append=False)
                    self.match(expected={"l", "L"}, append=False)

                elif self.match(expected={"l", "L"}, append=False):
                    self.match(expected={"l", "L"}, append=False)
                    self.match(expected={"u", "U"}, append=False)
                else:
                    pass

                # number cannot end on x or b in the case of binary or hexadecimal notation
                assert token[-1] != "x" and token[-1] != "b"

                if len(token) > 1 and token[0] == "0" and token[1] != "x" and token[1] != "b":
                    token = token[:1] + "o" + token[1:]
                self.tokens.append(token)
                token = ""

            # if token is alpha or underscore we need to build the identifier
            elif self.match(self.alpha, consume=False, append=False) or self.match(
                expected="_", consume=False, append=False
            ):
                while self.match(self.alnum, consume=False, append=False) or self.match(
                    expected="_", consume=False, append=False
                ):
                    token += self.getToken()
                    self.consume()
                    if self.outOfBounds():
                        break
                self.tokens.append(token)
                token = ""
            # if token is length 2 operand make sure next character is part of length 2 operand append to tokens
            elif self.match(expected=">", append=False) and self.match(expected=">", append=False):
                self.tokens.append(">>")
            elif self.match(expected="<", append=False) and self.match(expected="<", append=False):
                self.tokens.append("<<")
            elif self.match(expected=" ", append=False):
                continue
            else:
                raise Exception(f"Tokenizer does not recognize following token '{self.expression[self.i]}'")
        return self.tokens


class Expression:
    """Expression parser for calculations in definitions."""

    operators = {
        "*": lambda a, b: a * b,
        "/": lambda a, b: a // b,
        "%": lambda a, b: a % b,
        "+": lambda a, b: a + b,
        "-": lambda a, b: a - b,
        ">>": lambda a, b: a >> b,
        "<<": lambda a, b: a << b,
        "&": lambda a, b: a & b,
        "^": lambda a, b: a ^ b,
        "|": lambda a, b: a | b,
    }

    def precedence(self, o1: str, o2: str) -> bool:
        p = {
            "^": 1,
            "&": 5,
            "<<": 3,
            ">>": 3,
            "+": 4,
            "-": 4,
            "*": 5,
            "/": 5,
            "%": 5,
            "u": 6,
            "~": 6,
            "sizeof": 6,
        }  # Operator precedence levels
        return p[o1] >= p[o2]

    def __init__(self, cstruct: cstruct, expression: str):
        self.cstruct = cstruct
        self.expression = expression
        self.tokens = ExpressionTokenizer(expression).tokenize()
        self.stack = []
        self.queue = []

    def __repr__(self) -> str:
        return self.expression

    def evaluate_exp(self, context: Dict[str, int] = None) -> None:
        operator = self.stack.pop(-1)
        res = 0

        if operator == "u":
            right = self.queue.pop(-1)
            res = -1 * right
        elif operator == "~":
            right = self.queue.pop(-1)
            res = ~right
        else:
            right = self.queue.pop(-1)
            left = self.queue.pop(-1)
            res = self.operators[operator](left, right)
        self.queue.append(res)

    def isNumber(self, currentToken: str) -> bool:
        return currentToken.isnumeric() or (
            len(currentToken) > 2
            and currentToken[0] == "0"
            and (currentToken[1] == "x" or currentToken[1] == "b" or currentToken[1] == "o")
        )

    def parseErr(self, condition: bool, error: str) -> None:
        if condition:
            raise ExpressionParserError(error)

    def evaluate(self, context: Dict[str, int] = None) -> int:
        """Evaluates an expression using a Shunting-Yard implementation"""

        self.stack = []
        self.queue = []
        context = context or {}
        tempExpression = self.tokens
        opKeys = set(self.operators.keys())

        # unary minus Tokens; we change the semantic of '-' depending on the previous token
        for i in range(len(self.tokens)):
            if self.tokens[i] == "-":
                if i == 0:
                    self.tokens[i] = "u"
                    continue
                if self.tokens[i - 1] in opKeys or self.tokens[i - 1] == "u" or self.tokens[i - 1] == "(":
                    self.tokens[i] = "u"
                    continue

        i = 0
        while i < len(tempExpression):
            currentToken = tempExpression[i]
            if self.isNumber(currentToken):
                self.queue.append(int(currentToken, 0))
            elif currentToken in context:
                self.queue.append(context[currentToken])
            elif currentToken in self.cstruct.consts:
                self.queue.append(self.cstruct.consts[currentToken])
            elif currentToken == "u":
                self.stack.append(currentToken)
            elif currentToken == "~":
                self.stack.append(currentToken)
            elif currentToken == "sizeof":
                assert tempExpression[i + 1] == "("
                self.queue.append(len(self.cstruct.resolve(tempExpression[i + 2])))
                assert tempExpression[i + 3] == ")"
                i += 3
            elif currentToken in opKeys:
                while (
                    len(self.stack) != 0 and self.stack[-1] != "(" and (self.precedence(self.stack[-1], currentToken))
                ):
                    self.evaluate_exp(context)
                self.stack.append(currentToken)
            elif currentToken == "(":
                if i > 0:
                    previousToken = tempExpression[i - 1]
                    self.parseErr(
                        self.isNumber(previousToken),
                        f"Parser expected sizeof or an arethmethic operator instead got: '{previousToken}'",
                    )

                self.stack.append(currentToken)
            elif currentToken == ")":
                if i > 0:
                    previousToken = tempExpression[i - 1]
                    self.parseErr(
                        previousToken == "(",
                        f"Parser expected an expression, instead received empty parenthesis. Index: {i}",
                    )

                assert len(self.stack) != 0
                while self.stack[-1] != "(":
                    self.evaluate_exp(context)
                assert self.stack[-1] == "("
                self.stack.pop(-1)
            else:
                raise ExpressionParserError(f"unmatchedToken: '{currentToken}'")
            i += 1

        while len(self.stack) != 0:
            assert self.stack[-1] != "("
            self.evaluate_exp(context)

        return self.queue[0]

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from dissect.cstruct.exceptions import ExpressionParserError, ExpressionTokenizerError
from dissect.cstruct.expression import Expression

if TYPE_CHECKING:
    from dissect.cstruct.cstruct import cstruct

testdata = [
    ("1 * 0", 0),
    ("1 * 1", 1),
    ("7 * 8", 56),
    ("7*8", 56),
    ("7 *8", 56),
    ("   7  *     8  ", 56),
    ("\t7\t*\t8\t", 56),
    ("0 / 1", 0),
    ("1 / 1", 1),
    ("2 / 2", 1),
    ("3 / 2", 1),
    ("4 / 2", 2),
    ("1 % 1", 0),
    ("1 % 2", 1),
    ("5 % 3", 2),
    ("0 + 0", 0),
    ("1 + 0", 1),
    ("1 + 3", 4),
    ("0 - 0", 0),
    ("1 - 0", 1),
    ("0 - 1", -1),
    ("1 - 3", -2),
    ("3 - 1", 2),
    ("0x0 >> 0", 0x0),
    ("0x1 >> 0", 0x1),
    ("0x1 >> 1", 0x0),
    ("0xf0 >> 4", 0xF),
    ("0x0 << 4", 0),
    ("0x1 << 0", 1),
    ("0xf << 4", 0xF0),
    ("0 & 0", 0),
    ("1 & 0", 0),
    ("1 & 1", 1),
    ("1 & 2", 0),
    ("1 ^ 1", 0),
    ("1 ^ 0", 1),
    ("1 ^ 3", 2),
    ("0 | 0", 0),
    ("0 | 1", 1),
    ("1 | 1", 1),
    ("1 | 2", 3),
    ("1 | 2 | 4", 7),
    ("1 & 1 * 4", 0),
    ("(1 & 1) * 4", 4),
    ("4 * 1 + 1", 5),
    ("-42", -42),
    ("42 + (-42)", 0),
    ("A + 5", 13),
    ("21 - B", 8),
    ("A + B", 21),
    ("~1", -2),
    ("~(A + 5)", ~13),
    ("10l", 10),
    ("10ll", 10),
    ("10ull", 10),
    ("010ULL", 8),
    ("0Xf0 >> 4", 0xF),
    ("0x1B", 0x1B),
    ("0x1b", 0x1B),
]


class Consts:
    consts = {  # noqa: RUF012
        "A": 8,
        "B": 13,
    }


def id_fn(val: Any) -> str | None:
    if isinstance(val, (str,)):
        return val
    return None


@pytest.mark.parametrize(("expression", "answer"), testdata, ids=id_fn)
def test_expression(expression: str, answer: int) -> None:
    parser = Expression(expression)
    assert parser.evaluate(Consts()) == answer


@pytest.mark.parametrize(
    ("expression", "exception", "message"),
    [
        ("0b", ExpressionTokenizerError, "Invalid binary or hex notation"),
        ("0x", ExpressionTokenizerError, "Invalid binary or hex notation"),
        ("$", ExpressionTokenizerError, "Tokenizer does not recognize following token '\\$'"),
        ("-", ExpressionParserError, "Invalid expression: not enough operands"),
        ("(", ExpressionParserError, "Invalid expression"),
        (")", ExpressionParserError, "Invalid expression"),
        (" ", ExpressionParserError, "Invalid expression"),
        ("()", ExpressionParserError, "Parser expected an expression, instead received empty parenthesis. Index: 1"),
        ("0()", ExpressionParserError, "Parser expected sizeof or an arethmethic operator instead got: '0'"),
        ("sizeof)", ExpressionParserError, "Invalid sizeof operation"),
        ("sizeof(0 +)", ExpressionParserError, "Invalid sizeof operation"),
    ],
)
def test_expression_failure(expression: str, exception: type, message: str) -> None:
    with pytest.raises(exception, match=message):
        Expression(expression).evaluate(Consts())


def test_sizeof(cs: cstruct) -> None:
    d = """
    struct test {
        char    a[sizeof(uint32)];
    };

    struct test2 {
        char    a[sizeof(test) * 2];
    };
    """
    cs.load(d)

    assert len(cs.test) == 4
    assert len(cs.test2) == 8

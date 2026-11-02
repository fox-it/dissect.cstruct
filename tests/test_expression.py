from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from dissect.cstruct.exception import ExpressionParserError, LexerError, ResolveError
from dissect.cstruct.expression import SOURCE_GLOBALS, Expression

if TYPE_CHECKING:
    from collections.abc import Callable

    from dissect.cstruct.cstruct import cstruct


@pytest.fixture
def cs_with_consts(cs: cstruct) -> cstruct:
    cs.consts["A"] = 8
    cs.consts["B"] = 13
    return cs


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
    ("(1 + 2)", 3),
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
    ("-~1", 2),
    ("~(A + 5)", ~13),
    ("10l", 10),
    ("10ll", 10),
    ("10ull", 10),
    ("010ULL", 8),
    ("0Xf0 >> 4", 0xF),
    ("0x1B", 0x1B),
    ("0x1b", 0x1B),
]


def id_fn(val: Any) -> str | None:
    if isinstance(val, (str,)):
        return val
    return None


@pytest.mark.parametrize(("expression", "answer"), testdata, ids=id_fn)
def test_expression(cs_with_consts: cstruct, expression: str, answer: int) -> None:
    parser = Expression(expression)
    assert parser.evaluate(cs_with_consts) == answer


@pytest.mark.parametrize(
    ("expression", "exception", "message"),
    [
        pytest.param(
            "0b",
            LexerError,
            "invalid binary literal",
            id="empty-binary-literal",
        ),
        pytest.param(
            "0x",
            LexerError,
            "invalid hexadecimal literal",
            id="empty-hex-literal",
        ),
        pytest.param(
            "$",
            LexerError,
            "unexpected character '\\$'",
            id="unexpected-character",
        ),
        pytest.param(
            "-",
            ExpressionParserError,
            "Invalid expression: not enough operands",
            id="not-enough-operands",
        ),
        pytest.param(
            "(",
            ExpressionParserError,
            "Mismatched parentheses",
            id="open-parenthesis",
        ),
        pytest.param(
            ")",
            ExpressionParserError,
            "Mismatched parentheses",
            id="close-parenthesis",
        ),
        pytest.param(
            " ",
            ExpressionParserError,
            "Invalid expression",
            id="empty-expression",
        ),
        pytest.param(
            "()",
            ExpressionParserError,
            "Parser expected an expression, instead received empty parenthesis",
            id="empty-parenthesis",
        ),
        pytest.param(
            "0()",
            ExpressionParserError,
            "Parser expected sizeof or an arethmethic operator instead got: '0'",
            id="invalid-sizeof-usage",
        ),
        pytest.param(
            "sizeof)",
            ExpressionParserError,
            "expected \\(, got \\)",
            id="missing-parenthesis",
        ),
        pytest.param(
            "sizeof(",
            ExpressionParserError,
            "expected \\), got end of input",
            id="unterminated-parenthesis",
        ),
        pytest.param(
            "sizeof(0 +)",
            ResolveError,
            "Unknown type 0 \\+",
            id="invalid-sizeof-expression",
        ),
        pytest.param(
            "UNKNOWN",
            ExpressionParserError,
            "Unknown identifier: 'UNKNOWN'",
            id="unknown-identifier",
        ),
        pytest.param(
            "UNKNOWN.UNKNOWN",
            ExpressionParserError,
            "Unknown identifier: 'UNKNOWN.UNKNOWN'",
            id="unknown-identifier",
        ),
        pytest.param(
            "1 2",
            ExpressionParserError,
            "Invalid expression: too many operands",
            id="too-many-operands",
        ),
        pytest.param(
            "1 + + 2",
            ExpressionParserError,
            "Invalid expression: not enough operands",
            id="double-binary-operator",
        ),
    ],
)
def test_expression_failure(cs_with_consts: cstruct, expression: str, exception: type, message: str) -> None:
    with pytest.raises(exception, match=message):
        Expression(expression).evaluate(cs_with_consts)


def test_sizeof(cs: cstruct) -> None:
    """Tests that the size of types is correctly calculated."""
    cdef = """
    struct test {
        char    a[sizeof(uint32)];
    };

    struct test2 {
        char    a[sizeof(test) * 2];
    };
    """
    cs.load(cdef)

    assert len(cs.test) == 4
    assert len(cs.test2) == 8


def test_offsetof(cs: cstruct) -> None:
    """Tests that the offset of struct members is correctly calculated."""
    cdef = """
    struct test {
        uint32  a;
        uint64  b;
        uint16  c;
        uint8   d;
    };
    """
    cs.load(cdef)

    assert Expression("offsetof(test, a)").evaluate(cs) == 0
    assert Expression("offsetof(test, b)").evaluate(cs) == 4
    assert Expression("offsetof(test, c)").evaluate(cs) == 12
    assert Expression("offsetof(test, d)").evaluate(cs) == 14


def test_dotted_identifier(cs: cstruct) -> None:
    """Test dotted member access in expressions."""
    cs.load("""
    enum color : uint8 {
        RED = 1,
        GREEN = 2,
        BLUE = 4
    };
    """)

    assert Expression("color.RED").evaluate(cs) == 1
    assert Expression("color.RED | color.BLUE").evaluate(cs) == 5
    assert Expression("color.GREEN + 10").evaluate(cs) == 12


def test_dotted_identifier_unknown_member(cs: cstruct) -> None:
    """Test error when a member in a dotted expression doesn't exist."""
    cs.load("""
    enum color : uint8 {
        RED = 1
    };
    """)

    with pytest.raises(ExpressionParserError, match="Unknown identifier: 'color\\.NOTAMEMBER'"):
        Expression("color.NOTAMEMBER").evaluate(cs)


def test_dotted_identifier_not_integer(cs: cstruct) -> None:
    """Test error when a dotted expression resolves to a non-integer."""
    cs.consts["mydict"] = {"nested": "hello"}

    with pytest.raises(ExpressionParserError, match="does not resolve to an integer"):
        Expression("mydict.nested").evaluate(cs)


def _expression_function(expr: Expression) -> Callable[[cstruct, dict], int]:
    """Turn the source code of an expression into a function with the same arguments as ``evaluate``."""
    return eval(f"lambda cs, context: {expr.source()}", SOURCE_GLOBALS)


def test_expression_source(cs: cstruct) -> None:
    """Test that the source code of an expression calculates the same value as evaluating it."""
    cdef = """
    #define X 4
    struct test {
        uint32 a;
        uint16 b;
    };
    """
    cs.load(cdef)

    cases = [
        ("a - 8", {"a": 100}),
        ("(a & 1) * 16", {"a": 3}),
        ("a * 2 + b * (3 + 4) >> 1", {"a": 5, "b": 10}),
        ("sizeof(test) * X - -1", {}),
        ("offsetof(test, b) + ~X % 3", {}),
        ("a.b | 0x10 ^ 1 << 2", {"a": {"b": 3}}),
        ("a / 3", {"a": cs.uint32(10)}),
        ("1 + 2", {}),
    ]

    for source, context in cases:
        expr = Expression(source)
        assert _expression_function(expr)(cs, context) == expr.evaluate(cs, context)


@pytest.mark.parametrize(
    ("source", "context"),
    [
        ("unknown + 1", {}),
        ("a.c", {"a": {"b": 1}}),
        ("a", {"a": b"bytes"}),
        ("a / 0", {"a": 1}),
    ],
)
def test_expression_source_errors(cs: cstruct, source: str, context: dict) -> None:
    """Test that the source code of an expression raises the same errors as evaluating it."""
    expr = Expression(source)
    with pytest.raises(Exception) as expected:  # noqa: PT011
        expr.evaluate(cs, context)

    with pytest.raises(expected.type) as excinfo:
        _expression_function(expr)(cs, context)
    assert str(excinfo.value) == str(expected.value)


@pytest.mark.parametrize("source", ["(1 + 2", "1 + 2)", "1 +", "()", "1 (2)"])
def test_expression_source_invalid(cs: cstruct, source: str) -> None:
    """Test that getting the source code of an invalid expression raises the same error as evaluating it."""
    with pytest.raises(ExpressionParserError) as expected:
        Expression(source).evaluate(cs)

    with pytest.raises(ExpressionParserError) as excinfo:
        Expression(source).source()
    assert str(excinfo.value) == str(expected.value)


@pytest.mark.parametrize(
    ("expression", "source"),
    [
        # Precedence and associativity of the operators
        ("1 + 2 * 3", "(1 + (2 * 3))"),
        ("(1 + 2) * 3", "((1 + 2) * 3)"),
        ("a - b - c", "((a - b) - c)"),
        ("a / b / c", "((a // b) // c)"),
        ("a * 2 + b * (3 + 4) >> 1", "(((a * 2) + (b * (3 + 4))) >> 1)"),
        ("a | b ^ c & 1 << 2", "(a | (b ^ (c & (1 << 2))))"),
        ("((a))", "a"),
        # Unary operators
        ("-a * ~b", "((-a) * (~b))"),
        ("- -a", "(-(-a))"),
        ("~(a + 1) % 8", "((~(a + 1)) % 8)"),
        # Numbers in other bases
        ("0x10 + 0b101 - 0o7", "((16 + 5) - 7)"),
        # Functions, and identifiers that are resolved from the context
        ("sizeof(test) * X - -1", "((_sizeof(cs, 'test') * _identifier(cs, context, 'X', 1)) - (-1))"),
        ("offsetof(test, b) + a", "(_offsetof(cs, 'test', 'b') + a)"),
        ("hdr.size * 4", "(_identifier(cs, context, 'hdr.size', 1) * 4)"),
    ],
)
def test_expression_source_code(cs: cstruct, expression: str, source: str) -> None:
    """Test the exact source code of expressions with different operators, numbers and identifiers."""
    cdef = """
    #define X 4
    struct test {
        uint32  a;
        uint16  b;
    };
    """
    cs.load(cdef)
    expr = Expression(expression)

    # The identifiers a, b and c are local variables, everything else is resolved from the context
    variables = {"a": 100, "b": 7, "c": 3}
    assert expr.source({name: name for name in variables}) == source

    context = {**variables, "hdr": {"size": 5}}
    assert eval(source, {**SOURCE_GLOBALS, "cs": cs, "context": context, **variables}) == expr.evaluate(cs, context)


def test_expression_source_context() -> None:
    """Test that identifiers are resolved from the context with the given name, with their line number."""
    expected = "(_identifier(cs, values, 'X', 1) + _identifier(cs, values, 'b', 2))"
    assert Expression("X +\nb").source(context="values") == expected

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from dissect.cstruct.cstruct import cstruct
from dissect.cstruct.exception import (
    DefinitionError,
    ExpressionParserError,
    LexerError,
    ResolveError,
    UnknownIdentifierError,
)
from dissect.cstruct.expression import SOURCE_GLOBALS, Expression
from tests.util import verify_compiled

if TYPE_CHECKING:
    from collections.abc import Callable


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
            "^Invalid expression: not enough operands$",
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
            "Parser expected sizeof or an arithmethic operator instead got: '0'",
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
            "expected a type name, got end of input",
            id="unterminated-parenthesis",
        ),
        pytest.param(
            "sizeof(0 +)",
            ExpressionParserError,
            "^expected a type name, got 0$",
            id="invalid-sizeof-expression",
        ),
        pytest.param(
            "sizeof(uint8 +)",
            ExpressionParserError,
            "^expected \\), got \\+$",
            id="sizeof-type-name-and-operator",
        ),
        pytest.param(
            "sizeof(uint8[])",
            ExpressionParserError,
            "^expected an array size$",
            id="sizeof-array-without-size",
        ),
        pytest.param(
            "offsetof(test, 0)",
            ExpressionParserError,
            "^expected a field name, got 0$",
            id="offsetof-invalid-field-name",
        ),
        pytest.param(
            "UNKNOWN +",
            ExpressionParserError,
            "Invalid expression: not enough operands",
            id="unknown-identifier-before-error",
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
def test_expression_failure(expression: str, exception: type, message: str) -> None:
    """Test that an invalid expression raises an error when it's created, before it's evaluated."""
    with pytest.raises(exception, match=message):
        Expression(expression)


@pytest.mark.parametrize(
    ("expression", "exception", "message"),
    [
        pytest.param(
            "sizeof(nope)",
            ResolveError,
            "^Unknown type nope$",
            id="unknown-sizeof-type",
        ),
        pytest.param(
            "offsetof(uint8, a)",
            DefinitionError,
            "^Type 'uint8' is not a structure$",
            id="offsetof-not-a-structure",
        ),
        pytest.param(
            "UNKNOWN",
            UnknownIdentifierError,
            "Unknown identifier: 'UNKNOWN'",
            id="unknown-identifier",
        ),
        pytest.param(
            "UNKNOWN.UNKNOWN",
            UnknownIdentifierError,
            "Unknown identifier: 'UNKNOWN.UNKNOWN'",
            id="unknown-identifier",
        ),
    ],
)
def test_expression_evaluate_failure(cs_with_consts: cstruct, expression: str, exception: type, message: str) -> None:
    """Test that a valid expression that refers to something unknown or unsuitable raises an error when evaluated."""
    parser = Expression(expression)

    with pytest.raises(exception, match=message):
        parser.evaluate(cs_with_consts)


def test_sizeof(cs: cstruct, compiled: bool) -> None:
    """Tests that the size of types is correctly calculated."""
    cdef = """
    struct test {
        char    a[sizeof(uint32)];
    };

    struct test2 {
        char    a[sizeof(test) * 2];
    };

    struct test3 {
        uint8   n;
        char    a[n * sizeof(struct test2[2])];
    };

    struct test4 {
        int8    n;
        uint16  a[n];
        char    b[4 - sizeof(uint16[n])];
    };
    """
    cs.load(cdef, compiled=compiled)

    assert verify_compiled(cs.test3, compiled)
    assert verify_compiled(cs.test4, compiled)

    assert len(cs.test) == 4
    assert len(cs.test2) == 8
    assert cs.test3(b"\x02" + b"a" * 32).a == b"a" * 32

    test4 = cs.test4(b"\x01abcd")
    assert test4.a == [0x6261]
    assert test4.b == b"cd"

    # A negative count from the data is 0, like for the field before it
    test4 = cs.test4(b"\xffabcd")
    assert test4.a == []
    assert test4.b == b"abcd"


# The sizes of gcc on a 64-bit platform, with and without __attribute__((packed))
@pytest.mark.parametrize(
    ("type_name", "aligned", "packed"),
    [
        ("struct test", 8, 6),
        ("unsigned long long", 8, 8),
        ("uint16[3]", 6, 6),
        ("uint8[2][3]", 6, 6),
        ("struct test[2]", 16, 12),
        ("uint32 *", 8, 8),
        ("uint8 **", 8, 8),
        ("uint8 *[2]", 16, 16),
        ("struct test *[3]", 24, 24),
    ],
)
def test_sizeof_type_name(type_name: str, aligned: int, packed: int) -> None:
    """Test that sizeof accepts a type name like the type of a field, with the size that C gives it."""
    for align, size in ((True, aligned), (False, packed)):
        cs = cstruct(pointer="uint64").load("struct test { uint32 a; uint16 b; };", align=align)
        assert Expression(f"sizeof({type_name})").evaluate(cs) == size


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

    with pytest.raises(DefinitionError, match=r"^Structure 'test' does not have a field named 'e'$"):
        Expression("offsetof(test, e)").evaluate(cs)


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

    with pytest.raises(UnknownIdentifierError, match="Unknown identifier: 'color\\.NOTAMEMBER'"):
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
        ("sizeof(test) * X - -1", "((_sizeof(cs.resolve('test')) * _identifier(cs, context, 'X')) - (-1))"),
        ("offsetof(test, b) + a", "(_offsetof(cs.resolve('test'), 'b') + a)"),
        # Type names like the type of a field, with sizes that are calculated too
        ("sizeof(struct test *[a + 1])", "_sizeof(_resolve_type(cs, 'test', 1, [(a + 1)]))"),
        (
            "sizeof(unsigned int[X][b])",
            "_sizeof(_resolve_type(cs, 'unsigned int', 0, [_identifier(cs, context, 'X'), b]))",
        ),
        ("hdr.size * 4", "(_identifier(cs, context, 'hdr.size') * 4)"),
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
    """Test that identifiers are resolved from the context with the given name."""
    expected = "(_identifier(cs, values, 'X') + _identifier(cs, values, 'b'))"
    assert Expression("X + b").source(context="values") == expected

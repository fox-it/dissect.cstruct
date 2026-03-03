from __future__ import annotations

import pytest

from dissect.cstruct.exceptions import LexerError
from dissect.cstruct.lexer import TokenType, tokenize


@pytest.mark.parametrize(
    ("src", "types", "values"),
    [
        # Whitespace
        ("", [], []),
        (" ", [], []),
        ("\t", [], []),
        ("\n", [], []),
        ("   \t\n  ", [], []),
        # Numbers and symbols
        ("0", [TokenType.NUMBER], ["0"]),
        ("1234", [TokenType.NUMBER], ["1234"]),
        ("42u", [TokenType.NUMBER], ["42"]),
        ("42U", [TokenType.NUMBER], ["42"]),
        ("100l", [TokenType.NUMBER], ["100"]),
        ("100L", [TokenType.NUMBER], ["100"]),
        ("100ll", [TokenType.NUMBER], ["100"]),
        ("100ull", [TokenType.NUMBER], ["100"]),
        ("100ULL", [TokenType.NUMBER], ["100"]),
        ("0xff", [TokenType.NUMBER], ["0xff"]),
        ("0XFF", [TokenType.NUMBER], ["0XFF"]),
        ("0b1010", [TokenType.NUMBER], ["0b1010"]),
        ("0B1100", [TokenType.NUMBER], ["0B1100"]),
        ("0755", [TokenType.NUMBER], ["0o755"]),
        ("3.14", [TokenType.NUMBER], ["3.14"]),
        ("1.", [TokenType.NUMBER], ["1."]),
        ("{", [TokenType.LBRACE], ["{"]),
        ("}", [TokenType.RBRACE], ["}"]),
        ("[", [TokenType.LBRACKET], ["["]),
        ("]", [TokenType.RBRACKET], ["]"]),
        ("(", [TokenType.LPAREN], ["("]),
        (")", [TokenType.RPAREN], [")"]),
        (";", [TokenType.SEMICOLON], [";"]),
        (",", [TokenType.COMMA], [","]),
        (":", [TokenType.COLON], [":"]),
        ("*", [TokenType.STAR], ["*"]),
        ("=", [TokenType.EQUALS], ["="]),
        ("+", [TokenType.PLUS], ["+"]),
        ("-", [TokenType.UNARY_MINUS], ["-"]),
        ("/", [TokenType.SLASH], ["/"]),
        ("%", [TokenType.PERCENT], ["%"]),
        ("&", [TokenType.AMPERSAND], ["&"]),
        ("|", [TokenType.PIPE], ["|"]),
        ("^", [TokenType.CARET], ["^"]),
        ("~", [TokenType.TILDE], ["~"]),
        ("<<", [TokenType.LSHIFT], ["<<"]),
        (">>", [TokenType.RSHIFT], [">>"]),
        ("a << b", [TokenType.IDENTIFIER, TokenType.LSHIFT, TokenType.IDENTIFIER], ["a", "<<", "b"]),
        ("x >> 2", [TokenType.IDENTIFIER, TokenType.RSHIFT, TokenType.NUMBER], ["x", ">>", "2"]),
        ("-1", [TokenType.UNARY_MINUS, TokenType.NUMBER], ["-", "1"]),
        ("1 - 1", [TokenType.NUMBER, TokenType.MINUS, TokenType.NUMBER], ["1", "-", "1"]),
        # Preprocessor directives
        ("#define", [TokenType.PP_DEFINE], ["define"]),
        ("#undef", [TokenType.PP_UNDEF], ["undef"]),
        ("#ifdef", [TokenType.PP_IFDEF], ["ifdef"]),
        ("#ifndef", [TokenType.PP_IFNDEF], ["ifndef"]),
        ("#else", [TokenType.PP_ELSE], ["else"]),
        ("#endif", [TokenType.PP_ENDIF], ["endif"]),
        ('#include "foo.h"', [TokenType.PP_INCLUDE, TokenType.STRING], ["include", "foo.h"]),
        ("#include <stdint.h>", [TokenType.PP_INCLUDE, TokenType.STRING], ["include", "<stdint.h>"]),
        ("#[]", [TokenType.PP_FLAGS], [""]),
        ("#[compiled=True]", [TokenType.PP_FLAGS], ["compiled=True"]),
        # Strings
        ('"hello world"', [TokenType.STRING], ["hello world"]),
        ('"line1\nline2"', [TokenType.STRING], ["line1\nline2"]),
        ('"tab\tseparated"', [TokenType.STRING], ["tab\tseparated"]),
        ('"quote: \'"', [TokenType.STRING], ["quote: '"]),
        ("'single quoted'", [TokenType.STRING], ["single quoted"]),
        ("'escaped \\'quote\\''", [TokenType.STRING], ["escaped \\'quote\\'"]),
        ('""', [TokenType.STRING], [""]),
        ("''", [TokenType.STRING], [""]),
        # Bytes
        ("b'abc'", [TokenType.BYTES], ["b'abc'"]),
        ('B"hello"', [TokenType.BYTES], ["b'hello'"]),
        # Identifiers
        ("b_var", [TokenType.IDENTIFIER], ["b_var"]),
        ("hello", [TokenType.IDENTIFIER], ["hello"]),
        ("_my_var", [TokenType.IDENTIFIER], ["_my_var"]),
        ("UINT32", [TokenType.IDENTIFIER], ["UINT32"]),
        ("uint32_t", [TokenType.IDENTIFIER], ["uint32_t"]),
        # Lookup
        ("$my_lookup = {1: 'a', 2: 'b'}", [TokenType.LOOKUP], ["$my_lookup = {1: 'a', 2: 'b'}"]),
        ("$tbl = {\n    1: 'x',\n    2: 'y'\n}", [TokenType.LOOKUP], ["$tbl = {\n    1: 'x',\n    2: 'y'\n}"]),
        # Combination
        (
            "uint32_t bit0:1;",
            [TokenType.IDENTIFIER, TokenType.IDENTIFIER, TokenType.COLON, TokenType.NUMBER, TokenType.SEMICOLON],
            ["uint32_t", "bit0", ":", "1", ";"],
        ),
        (
            "field[69]",
            [TokenType.IDENTIFIER, TokenType.LBRACKET, TokenType.NUMBER, TokenType.RBRACKET],
            ["field", "[", "69", "]"],
        ),
        (
            "A = 0, B = 1",
            [
                TokenType.IDENTIFIER,
                TokenType.EQUALS,
                TokenType.NUMBER,
                TokenType.COMMA,
                TokenType.IDENTIFIER,
                TokenType.EQUALS,
                TokenType.NUMBER,
            ],
            ["A", "=", "0", ",", "B", "=", "1"],
        ),
    ],
)
def test_token(src: str, types: list[TokenType], values: list[str]) -> None:
    """Test that various source strings produce the expected token types and values."""
    tokens = tokenize(src)
    assert len(tokens) == len(types) + 1  # +1 for the final EOF token
    assert tokens[-1].type == TokenType.EOF

    for token, type_, value in zip(tokens, types, values, strict=False):
        assert token.type == type_
        assert token.value == value


@pytest.mark.parametrize(
    ("src", "match"),
    [
        ("0b", "invalid binary literal"),
        ("0x", "invalid hexadecimal literal"),
        ('"unterminated', "unexpected end of input"),
        ("'unterminated", "unexpected end of input"),
        ("#foobar", "unknown preprocessor directive"),
        ("#include", "unexpected end of input"),
        ("#include <missing_end", "unexpected end of input"),
        ('#include "missing_end', "unexpected end of input"),
        ("@", "unexpected character"),
        ("`", "unexpected character"),
    ],
)
def test_error(src: str, match: str) -> None:
    """Test that various invalid inputs raise a LexerError with the expected message."""
    with pytest.raises(LexerError, match=match):
        tokenize(src)


def test_line_and_column_tracking() -> None:
    """Test that the lexer correctly tracks line and column numbers."""
    src = "a\n  b\nc"
    tokens = tokenize(src)
    assert tokens[0].type == TokenType.IDENTIFIER
    assert tokens[0].value == "a"
    assert tokens[0].line == 1
    assert tokens[0].column == 1

    assert tokens[1].type == TokenType.IDENTIFIER
    assert tokens[1].value == "b"
    assert tokens[1].line == 2
    assert tokens[1].column == 3

    assert tokens[2].type == TokenType.IDENTIFIER
    assert tokens[2].value == "c"
    assert tokens[2].line == 3
    assert tokens[2].column == 1

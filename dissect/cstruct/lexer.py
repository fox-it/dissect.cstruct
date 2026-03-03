from __future__ import annotations

import enum
import re
from typing import TYPE_CHECKING

from dissect.cstruct.exceptions import LexerError

if TYPE_CHECKING:
    from collections.abc import Callable


class TokenType(enum.Enum):
    # Identifiers & literals
    IDENTIFIER = "IDENTIFIER"
    NUMBER = "NUMBER"
    STRING = "STRING"
    BYTES = "BYTES"

    # Punctuation
    LBRACE = "{"
    RBRACE = "}"
    LBRACKET = "["
    RBRACKET = "]"
    LPAREN = "("
    RPAREN = ")"
    SEMICOLON = ";"
    COMMA = ","
    COLON = ":"
    STAR = "*"
    EQUALS = "="

    # Keywords
    STRUCT = "STRUCT"
    UNION = "UNION"
    ENUM = "ENUM"
    FLAG = "FLAG"
    TYPEDEF = "TYPEDEF"
    SIZEOF = "SIZEOF"
    OFFSETOF = "OFFSETOF"

    # Operators
    PLUS = "+"
    MINUS = "-"
    UNARY_MINUS = "-u"
    SLASH = "/"
    PERCENT = "%"
    AMPERSAND = "&"
    PIPE = "|"
    CARET = "^"
    TILDE = "~"
    LSHIFT = "<<"
    RSHIFT = ">>"

    # Preprocessor
    PP_DEFINE = "PP_DEFINE"
    PP_UNDEF = "PP_UNDEF"
    PP_IFDEF = "PP_IFDEF"
    PP_IFNDEF = "PP_IFNDEF"
    PP_ELSE = "PP_ELSE"
    PP_ENDIF = "PP_ENDIF"
    PP_INCLUDE = "PP_INCLUDE"
    PP_FLAGS = "PP_FLAGS"

    # Special
    LOOKUP = "LOOKUP"
    EOF = "EOF"


class Token:
    __slots__ = ("column", "line", "type", "value")

    def __init__(self, type: TokenType, value: str, line: int, column: int = 0):
        self.type = type
        self.value = value
        self.line = line
        self.column = column

    def __repr__(self) -> str:
        return f"<Token.{self.type.name} value={self.value!r} line={self.line}>"


_PP_KEYWORDS = {
    "define": TokenType.PP_DEFINE,
    "undef": TokenType.PP_UNDEF,
    "ifdef": TokenType.PP_IFDEF,
    "ifndef": TokenType.PP_IFNDEF,
    "else": TokenType.PP_ELSE,
    "endif": TokenType.PP_ENDIF,
    "include": TokenType.PP_INCLUDE,
}

_C_KEYWORDS = {
    "sizeof": TokenType.SIZEOF,
    "offsetof": TokenType.OFFSETOF,
    "struct": TokenType.STRUCT,
    "union": TokenType.UNION,
    "enum": TokenType.ENUM,
    "flag": TokenType.FLAG,
    "typedef": TokenType.TYPEDEF,
}

_IDENTIFIER_TYPES = set(_C_KEYWORDS.values()) | {TokenType.IDENTIFIER}

_SINGLE_CHARS = {
    "{": TokenType.LBRACE,
    "}": TokenType.RBRACE,
    "[": TokenType.LBRACKET,
    "]": TokenType.RBRACKET,
    "(": TokenType.LPAREN,
    ")": TokenType.RPAREN,
    ";": TokenType.SEMICOLON,
    ",": TokenType.COMMA,
    ":": TokenType.COLON,
    "*": TokenType.STAR,
    "=": TokenType.EQUALS,
    "+": TokenType.PLUS,
    "-": TokenType.MINUS,
    "/": TokenType.SLASH,
    "%": TokenType.PERCENT,
    "&": TokenType.AMPERSAND,
    "|": TokenType.PIPE,
    "^": TokenType.CARET,
    "~": TokenType.TILDE,
}

_RE_IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_RE_WHITESPACE = re.compile(r"[ \t\r\n]+")


def tokenize(data: str) -> list[Token]:
    """Convenience function to tokenize input data."""
    return Lexer(data).tokenize()


class Lexer:
    """Lexer compatible with C-like syntax for struct definitions and preprocessor directives."""

    def __init__(self, data: str):
        self.data = data
        self._pos = 0
        self._line = 1
        self._column = 1
        self._tokens: list[Token] = []

    def reset(self) -> None:
        """Reset the lexer state for a new input."""
        self._pos = 0
        self._line = 1
        self._column = 1
        self._tokens = []

    @property
    def eof(self) -> bool:
        """Whether the end of the input has been reached."""
        return self._pos >= len(self.data)

    def _assert_not_eof(self) -> None:
        """Raise an error if EOF is reached."""
        if self.eof:
            raise self._error("unexpected end of input")

    def _current(self) -> str:
        """Return the current character without consuming it. Raises an error if EOF is reached."""
        self._assert_not_eof()
        return self.data[self._pos]

    def _get(self, start: int, end: int | None = None) -> str:
        """Get a slice of the input data from ``start`` to ``end``."""
        if end is not None:
            return self.data[start:end]
        return self.data[start]

    def _peek(self, offset: int = 1) -> str | None:
        """Peek at the character at the given offset without consuming it. Returns ``None`` if EOF is reached."""
        return None if (idx := self._pos + offset) >= len(self.data) else self._get(idx)

    def _take(self, num: int = 1) -> str:
        """Consume and return the next ``num`` characters, updating line and column counters."""
        end = self._pos + num
        if end > len(self.data):
            self._pos = len(self.data)
            self._assert_not_eof()

        if num == 1:
            result = self.data[self._pos]
            self._pos = end
            if result == "\n":
                self._line += 1
                self._column = 1
            else:
                self._column += 1
            return result

        result = self.data[self._pos : end]
        self._pos = end

        if num_newlines := result.count("\n"):
            self._line += num_newlines
            self._column = len(result) - result.rfind("\n")
        else:
            self._column += num

        return result

    def _expect(self, *chars: str) -> None:
        """Consume the expected characters or raise an error."""
        if self._current() not in chars:
            actual = "end of input" if self.eof else repr(self._current())
            expected = " or ".join(repr(c) for c in chars)
            raise self._error(f"expected {expected}, got {actual}")

        return self._take()

    def _error(self, msg: str, *, line: int | None = None) -> LexerError:
        return LexerError(f"line {line if line is not None else self._line}: {msg}")

    def _emit(self, type: TokenType, value: str, line: int, column: int = 0) -> None:
        """Emit a token with the given type and value at the specified line and column."""
        self._tokens.append(Token(type, value, line, column))

    def _read_until(self, condition: str | Callable[[str], bool], *, or_eof: bool = True) -> str:
        """Read until the current character matches the condition.

        Args:
            condition: Characters to match, or a function that returns ``True`` to stop.
            or_eof: If True, also stop if EOF is reached. If False, EOF will not stop the read and will raise an error.
        """
        start = self._pos
        while True:
            if self.eof:
                if not or_eof:
                    self._assert_not_eof()
                break

            ch = self.data[self._pos]
            if isinstance(condition, str):
                if ch in condition:
                    break
            else:
                if condition(ch):
                    break

            self._pos += 1

        end = self._pos
        self._pos = start
        return self._take(end - start)

    def _read_while(self, condition: str | Callable[[str], bool], *, or_eof: bool = True) -> str:
        """Read while the current character matches the condition.

        Args:
            condition: Characters to match, or a function that returns ``True`` to continue.
            or_eof: If True, also stop if EOF is reached. If False, EOF will not stop the read and will raise an error.
        """
        start = self._pos
        while True:
            if self.eof:
                if not or_eof:
                    self._assert_not_eof()
                break

            ch = self.data[self._pos]
            if isinstance(condition, str):
                if ch not in condition:
                    break
            else:
                if not condition(ch):
                    break

            self._pos += 1

        end = self._pos
        self._pos = start
        return self._take(end - start)

    def _skip_whitespace(self) -> None:
        """Skip whitespace characters."""
        if match := _RE_WHITESPACE.match(self.data, self._pos):
            self._take(match.end() - self._pos)

    def _read_identifier(self) -> str:
        """Read an identifier starting with a letter or underscore, followed by letters, digits, or underscores."""
        if match := _RE_IDENTIFIER.match(self.data, self._pos):
            return self._take(match.end() - self._pos)
        return ""

    def _read_number(self) -> str:
        """Read a numeric literal, supporting decimal, hex (0x), octal (0), binary (0b), and C-style suffixes."""
        start = self._pos
        is_float = False

        if self._current() == "0" and self._peek() in ("x", "X", "b", "B"):
            self._expect("0")  # Consume leading 0
            suffix = self._take().lower()

            if suffix == "x" and not self._read_while("0123456789abcdefABCDEF"):
                raise self._error("invalid hexadecimal literal")

            if suffix == "b" and not self._read_while("01"):
                raise self._error("invalid binary literal")

        else:
            # Consume decimal/octal digits
            self._read_while("0123456789")

            # Decimal point for float literals
            if self._peek(0) == ".":
                is_float = True
                self._take()
                self._read_while("0123456789")

        raw = self._get(start, self._pos)

        if not is_float:
            # Strip C-style suffixes (ULL, ull, ul, u, l, ll, etc.)
            self._read_while("uUlL")

            # Convert octal: leading 0 without 0x/0b → insert 'o'
            if len(raw) > 1 and raw[0] == "0" and raw[1].lower() not in ("x", "b"):
                raw = raw[0] + "o" + raw[1:]

        return raw

    def _read_string(self) -> str:
        """Read a quoted string."""
        quote = self._expect('"', "'")  # Consume opening quote
        start = self._pos

        while not self.eof:
            ch = self.data[self._pos]
            if ch == "\\":
                if self._pos + 1 < len(self.data):
                    self._pos += 2
                else:
                    self._pos += 1
                continue

            if ch == quote:
                break

            self._pos += 1

        end = self._pos
        self._pos = start
        result = self._take(end - start)
        self._expect(quote)  # Consume closing quote

        return result

    def _read_angle_string(self) -> str:
        """Read an angle-bracket string for ``#include <...>``."""
        self._expect("<")  # Consume `<`
        value = self._read_until(">", or_eof=False)
        self._expect(">")  # Consume closing `>`
        return f"<{value}>"

    def _read_preprocessor(self) -> None:
        """Read a preprocessor directive starting with ``#``."""
        line = self._line
        col = self._column
        self._expect("#")  # Consume `#`

        # Check for `#[flags]`
        if self._current() == "[":
            self._expect("[")  # Consume `[`
            value = self._read_until("]")

            self._assert_not_eof()
            self._expect("]")  # Consume `]`

            self._emit(TokenType.PP_FLAGS, value, line, col)
            return

        # Read the keyword after #
        self._skip_whitespace()
        keyword = self._read_identifier()

        if (token_type := _PP_KEYWORDS.get(keyword)) is None:
            raise self._error(f"unknown preprocessor directive '#{keyword}'", line=line)

        self._emit(token_type, keyword, line, col)

        if token_type == TokenType.PP_INCLUDE:
            # Read include path — either "..." or <...>
            self._skip_whitespace()

            ch = self._current()
            if ch == '"' or ch == "'":
                value = self._read_string()
            elif ch == "<":
                value = self._read_angle_string()
            else:
                raise self._error("expected include path after '#include'", line=line)

            self._emit(TokenType.STRING, value, line)

    def _read_lookup(self) -> None:
        """Read a lookup definition: ``$name = { dict }``."""
        line = self._line
        col = self._column
        start = self._pos

        self._expect("$")  # Consume `$`

        # Read until end of the {...} block
        brace_depth = 0
        while not self.eof:
            ch = self._current()
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    self._expect("}")  # Consume final `}`
                    break
            self._take()

        value = self._get(start, self._pos)
        self._emit(TokenType.LOOKUP, value.strip(), line, col)

    def tokenize(self) -> list[Token]:
        """Tokenize the input data and return a list of tokens."""
        while not self.eof:
            self._skip_whitespace()
            if self.eof:
                break

            ch = self._current()

            # Skip comments
            if ch == "/":
                peek = self._peek()

                if peek == "*":
                    self._take(2)  # Consume /*
                    end = self.data.find("*/", self._pos)
                    if end != -1:
                        self._take(end - self._pos + 2)
                    else:
                        self._take(len(self.data) - self._pos)
                    continue

                if peek == "/":
                    self._take(2)  # Consume //
                    end = self.data.find("\n", self._pos)
                    if end != -1:
                        self._take(end - self._pos)
                    else:
                        self._take(len(self.data) - self._pos)
                    continue

            line = self._line
            col = self._column

            if ch == "#":
                # C-style preprocessor directive
                self._read_preprocessor()

            elif ch in ('"', "'"):
                self._emit(TokenType.STRING, self._read_string(), line, col)

            elif ch in ("b", "B") and self._peek() in ("'", '"'):
                # Binary string literal like `b"..."` or `b'...'`
                self._take()  # Consume `b`
                self._emit(TokenType.BYTES, f"b'{self._read_string()}'", line, col)

            elif ch.isdigit():
                self._emit(TokenType.NUMBER, self._read_number(), line, col)

            elif ch.isalpha() or ch == "_":
                ident = self._read_identifier()
                token_type = _C_KEYWORDS.get(ident, TokenType.IDENTIFIER)
                self._emit(token_type, ident, line, col)

            elif ch == "<" and self._peek() == "<":
                self._emit(TokenType.LSHIFT, self._take(2), line, col)

            elif ch == ">" and self._peek() == ">":
                self._emit(TokenType.RSHIFT, self._take(2), line, col)

            elif ch == "-" and (
                self._pos == 0
                or self._tokens[-1].type not in (TokenType.IDENTIFIER, TokenType.NUMBER, TokenType.RPAREN)
            ):
                self._emit(TokenType.UNARY_MINUS, self._take(), line, col)

            elif ch in _SINGLE_CHARS:
                self._emit(_SINGLE_CHARS[ch], self._take(), line, col)

            elif ch == "$":
                # Custom lookup definition
                self._read_lookup()

            else:
                raise self._error(f"unexpected character {ch!r}", line=line)

        self._emit(TokenType.EOF, "", self._line, self._column)
        return self._tokens


class TokenCursor:
    """Shared token cursor helpers for parsers using ``Token`` streams."""

    def __init__(self, tokens: list[Token] | None = None):
        self._tokens: list[Token] = tokens or []
        self._pos = 0

    def _reset_tokens(self, tokens: list[Token]) -> None:
        """Replace the current token stream and reset position."""
        self._tokens = tokens
        self._pos = 0

    def _reset_cursor(self) -> None:
        """Reset only the cursor position while keeping the current tokens."""
        self._pos = 0

    def _assert_not_eof(self) -> None:
        """Raise an error if EOF is reached."""
        if self._tokens[self._pos].type == TokenType.EOF:
            raise self._error("unexpected end of input", token=self._tokens[self._pos])

    def _previous(self) -> Token:
        """Return the previous token without consuming it."""
        return self._tokens[self._pos - 1] if self._pos > 0 else Token(TokenType.EOF, "", 0)

    def _current(self) -> Token:
        """Return the current token without consuming it."""
        return self._tokens[self._pos]

    def _peek(self, offset: int = 1) -> Token:
        """Peek at a token at the given offset without consuming it. Returns EOF on overflow."""
        idx = self._pos + offset
        return self._tokens[-1] if idx >= len(self._tokens) else self._tokens[idx]

    def _take(self) -> Token:
        """Consume and return the current token."""
        token = self._current()
        if token.type != TokenType.EOF:
            self._pos += 1
        return token

    def _expect(self, *types: TokenType) -> Token:
        """Consume and return the current token if it matches, otherwise raise an error."""
        token = self._current()
        if token.type not in types:
            actual = "end of input" if token.type == TokenType.EOF else token.value
            expected = " or ".join(t.value for t in types)
            expected = f"one of {expected}" if len(types) > 1 else expected
            raise self._error(f"expected {expected}, got {actual}")
        return self._take()

    def _collect_until(self, *terminators: TokenType) -> str:
        """Collect token values until one of the terminators is reached, tracking nesting."""
        terminators_set = set(terminators)
        start = self._current()
        parts: list[str] = []
        depth = 0

        while (token := self._current()).type != TokenType.EOF:
            if depth == 0 and token.type in terminators_set:
                break

            if token.type in (TokenType.LPAREN, TokenType.LBRACKET):
                depth += 1
            elif token.type in (TokenType.RPAREN, TokenType.RBRACKET):
                depth -= 1
                if depth < 0:
                    raise self._error("unmatched closing bracket", token=token)

            parts.append(token.value)
            self._pos += 1

        if depth > 0:
            raise self._error("unclosed opening bracket", token=start)

        return " ".join(parts)

    def _error(self, msg: str, *, token: Token | None = None) -> Exception:
        """Subclasses should override to return an appropriate exception."""
        raise NotImplementedError

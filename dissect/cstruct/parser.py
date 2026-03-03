from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING

from dissect.cstruct import compiler
from dissect.cstruct.exceptions import (
    ExpressionParserError,
    ParserError,
)
from dissect.cstruct.expression import Expression
from dissect.cstruct.lexer import _IDENTIFIER_TYPES, Token, TokenCursor, TokenType, tokenize
from dissect.cstruct.types import BaseArray, BaseType, Enum, Field, Flag, Structure

if TYPE_CHECKING:
    from dissect.cstruct import cstruct


class Parser(TokenCursor):
    """Base class for definition parsers.

    Args:
        cs: An instance of cstruct.
    """

    def __init__(self, cs: cstruct):
        super().__init__()
        self.cs = cs

    def parse(self, data: str) -> None:
        """This function should parse definitions to cstruct types.

        Args:
            data: Data to parse definitions from.
        """
        raise NotImplementedError


def _join_line_continuations(string: str) -> str:
    # Join lines ending with backslash
    return re.sub(r"\\\n", "", string)


class CStyleParser(Parser):
    """Recursive descent parser for C-like structure definitions.

    Args:
        cs: An instance of cstruct.
        compiled: Whether structs should be compiled or not.
        align: Whether to use aligned struct reads.
    """

    def __init__(self, cs: cstruct, compiled: bool = True, align: bool = False):
        super().__init__(cs)
        self.compiled = compiled
        self.align = align

        self._flags: list[str] = []
        self._conditional_stack: list[tuple[Token, bool]] = []

    def reset(self) -> None:
        """Reset the parser state for a new input."""
        self._reset_tokens([])
        self._flags = []
        self._conditional_stack = []

    def parse(self, data: str) -> None:
        """Parse C-like definitions from the input data."""
        self.reset()

        data = _join_line_continuations(data)

        # Tokenize and preprocess the input, then parse top-level definitions
        self._reset_tokens(tokenize(data))
        preprocessed_tokens = self._preprocess()
        self.reset()

        self._reset_tokens(preprocessed_tokens)
        self._parse()

    def _match(self, *types: TokenType) -> Token | None:
        """Consume and return the current token if it matches any of the given types, otherwise return None."""
        if self._current().type in types:
            return self._take()
        return None

    def _at(self, *types: TokenType) -> bool:
        """Return whether the current token matches any of the given types."""
        return self._tokens[self._pos].type in types

    def _at_value(self, value: str) -> bool:
        """Return whether the current token is an identifier with the given value."""
        token = self._tokens[self._pos]
        return token.type == TokenType.IDENTIFIER and token.value == value

    def _error(self, msg: str, *, token: Token | None = None) -> ParserError:
        return ParserError(f"line {(token if token is not None else self._tokens[self._pos]).line}: {msg}")

    def _preprocess(self) -> list[Token]:
        """Handle preprocessor directives and return a new list of tokens with directives processed."""
        result = []

        while self._tokens[self._pos].type != TokenType.EOF:
            token = self._tokens[self._pos]

            # Always handle conditional directives first (even in false branches)
            if token.type in (TokenType.PP_IFDEF, TokenType.PP_IFNDEF, TokenType.PP_ELSE, TokenType.PP_ENDIF):
                self._handle_conditional()
                continue

            # If we're in a false conditional branch, skip this token
            if self._conditional_stack and not self._conditional_stack[-1][1]:
                self._pos += 1
                continue

            if token.type == TokenType.PP_DEFINE:
                self._parse_define()
            elif token.type == TokenType.PP_UNDEF:
                self._parse_undef()
            elif token.type == TokenType.PP_INCLUDE:
                self._parse_include()
            else:
                # Not a preprocessor directive, just add it to the result
                result.append(token)
                self._pos += 1

        # Append EOF token
        result.append(self._tokens[self._pos])
        self._pos += 1

        if self._conditional_stack:
            raise self._error("unclosed conditional statement", token=self._conditional_stack[-1][0])

        return result

    def _parse(self) -> None:
        """Parse top-level definitions from the token stream."""
        while (token := self._current()).type != TokenType.EOF:
            if token.type == TokenType.PP_FLAGS:
                self._parse_config_flags()
            elif token.type == TokenType.LOOKUP:
                self._parse_lookup()
            elif token.type == TokenType.TYPEDEF:
                self._parse_typedef()
            elif token.type in (TokenType.STRUCT, TokenType.UNION):
                self._parse_struct_or_union()

                # Skip variable declarations after struct/union definitions
                while not self._at(TokenType.SEMICOLON, TokenType.EOF):
                    self._pos += 1

                self._expect(TokenType.SEMICOLON)
            elif token.type in (TokenType.ENUM, TokenType.FLAG):
                type_ = self._parse_enum_or_flag()

                # If it's an anonymous enum/flag, add its members to the constants for convenience
                if not type_.__name__:
                    self.cs.consts.update(type_.__members__)

                self._expect(TokenType.SEMICOLON)
            else:
                raise self._error(f"unexpected token {token.value!r}")

    # Preprocessor directives

    def _parse_define(self) -> None:
        """Parse a define directive and add the constant."""
        self._expect(TokenType.PP_DEFINE)

        name_token = self._expect(TokenType.IDENTIFIER)

        # Collect all tokens on the same line as the #define
        parts = []
        while (token := self._current()).type != TokenType.EOF and token.line == name_token.line:
            parts.append(self._take().value)

        value = " ".join(parts).strip()
        try:
            # Lazy mode, try to evaluate as a Python literal first (for simple constants)
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass

        # If it's still a string, try to evaluate it as an expression in the context of current constants
        if isinstance(value, str):
            try:
                value = Expression(value).evaluate(self.cs)
            except ExpressionParserError:
                # If evaluation fails, just keep it as a string (e.g. for macro-like constants)
                pass

        self.cs.consts[name_token.value] = value

    def _parse_undef(self) -> None:
        """Parse an undef directive and remove the constant."""
        self._expect(TokenType.PP_UNDEF)

        name_token = self._expect(TokenType.IDENTIFIER)
        if name_token.value in self.cs.consts:
            del self.cs.consts[name_token.value]
        else:
            raise self._error(f"constant {name_token.value!r} not defined", token=name_token)

    def _parse_include(self) -> None:
        """Parse an include directive and add the included file to the includes list."""
        self._expect(TokenType.PP_INCLUDE)
        self.cs.includes.append(self._expect(TokenType.STRING).value)

    def _parse_config_flags(self) -> None:
        """Parse configuration flags from a directive like ``#[flag1, flag2, ...]``."""
        self._flags.extend(self._expect(TokenType.PP_FLAGS).value.split(","))

    def _handle_conditional(self) -> None:
        """Handle conditional directives: ``#ifdef``, ``#ifndef``, ``#else``, ``#endif``."""
        if (token := self._take()).type not in (
            TokenType.PP_IFDEF,
            TokenType.PP_IFNDEF,
            TokenType.PP_ELSE,
            TokenType.PP_ENDIF,
        ):
            raise self._error("expected conditional directive")

        if token.type == TokenType.PP_IFDEF:
            name = self._expect(TokenType.IDENTIFIER).value
            if self._conditional_stack and not self._conditional_stack[-1][1]:
                # Parent is false, so this child is always false
                self._conditional_stack.append((token, False))
            else:
                self._conditional_stack.append((token, name in self.cs.consts))

        elif token.type == TokenType.PP_IFNDEF:
            name = self._expect(TokenType.IDENTIFIER).value
            if self._conditional_stack and not self._conditional_stack[-1][1]:
                self._conditional_stack.append((token, False))
            else:
                self._conditional_stack.append((token, name not in self.cs.consts))

        elif token.type == TokenType.PP_ELSE:
            if not self._conditional_stack:
                raise self._error("#else without matching #ifdef/#ifndef", token=token)

            # Only flip if parent is true (or there's no parent)
            parent_active = len(self._conditional_stack) < 2 or self._conditional_stack[-2][1]
            if parent_active:
                self._conditional_stack[-1] = (self._conditional_stack[-1][0], not self._conditional_stack[-1][1])

        elif token.type == TokenType.PP_ENDIF:
            if not self._conditional_stack:
                raise self._error("#endif without matching #ifdef/#ifndef", token=token)
            self._conditional_stack.pop()

    # Type definitions

    def _parse_typedef(self) -> None:
        """Parse a typedef definition."""
        self._expect(TokenType.TYPEDEF)

        base_type = self._parse_type_spec()

        # Parse one or more typedef names with modifiers (pointers, arrays)
        while self._at(TokenType.IDENTIFIER, TokenType.STAR):
            type_, name, bits = self._parse_field_name(base_type)
            if bits is not None:
                raise self._error("typedefs cannot have bitfields")

            # For convenience, we assign the typedef name to anonymous structs/unions
            if issubclass(base_type, Structure) and base_type.__anonymous__:
                base_type.__anonymous__ = False
                base_type.__name__ = name
                base_type.__qualname__ = name

            self.cs.add_type(name, type_)

            if not self._match(TokenType.COMMA):
                break

        self._match(TokenType.SEMICOLON)

    def _parse_struct_or_union(self) -> type[Structure]:
        """Parse a struct or union definition.

        If ``register`` is ``True``, the struct will be registered with its name (which is required).
        Otherwise, the struct will not be registered and can only be used as an inline type for fields.
        """
        start_token = self._expect(TokenType.STRUCT, TokenType.UNION)

        is_union = start_token.type == TokenType.UNION
        factory = self.cs._make_union if is_union else self.cs._make_struct

        type = None
        name = None

        if not self._at(TokenType.LBRACE):
            if not self._at(TokenType.IDENTIFIER):
                raise self._error("expected struct name or '{'", token=start_token)

            name = self._take().value

            # struct name { ... }
            if self._at(TokenType.LBRACE):
                # Named struct/union, empty pre-register for self-referencing
                type = factory(name, [], align=self.align)
                if self.compiled and "nocompile" not in self._flags:
                    type = compiler.compile(type)
                self.cs.add_type(name, type)
            else:
                # struct typename ... (type reference)
                return self.cs.resolve(name)

        # Parse body
        self._expect(TokenType.LBRACE)
        fields = self._parse_field_list()
        self._expect(TokenType.RBRACE)

        if type is None:
            is_anonymous = name is None
            name = name or self.cs._next_anonymous()

            type = factory(name, fields, align=self.align, anonymous=is_anonymous)
            if self.compiled and "nocompile" not in self._flags:
                type = compiler.compile(type)
        else:
            type.__fields__.extend(fields)
            type.commit()

        self._flags.clear()
        return type

    def _parse_enum_or_flag(self) -> type[Enum | Flag]:
        """Parse an enum or flag definition."""
        start_token = self._expect(TokenType.ENUM, TokenType.FLAG)

        is_flag = start_token.type == TokenType.FLAG

        name = None
        if self._at(TokenType.IDENTIFIER):
            name = self._take().value

        # Optional base type
        base_type_str = "uint32"
        if self._match(TokenType.COLON):
            parts = []
            while (token := self._match(TokenType.IDENTIFIER)) is not None:
                parts.append(token.value)
            base_type_str = " ".join(parts)

        self._expect(TokenType.LBRACE)

        next_value = 1 if is_flag else 0
        values: dict[str, int] = {}

        while not self._at(TokenType.RBRACE):
            self._assert_not_eof()

            member_name = self._expect(TokenType.IDENTIFIER).value

            if self._match(TokenType.EQUALS):
                expression = self._collect_until(TokenType.COMMA, TokenType.RBRACE)
                value = Expression(expression).evaluate(self.cs, values)
            else:
                value = next_value

            if is_flag:
                high_bit = value.bit_length() - 1
                next_value = 2 ** (high_bit + 1)
            else:
                next_value = value + 1

            values[member_name] = value
            self._match(TokenType.COMMA)  # optional trailing comma

        self._expect(TokenType.RBRACE)

        factory = self.cs._make_flag if is_flag else self.cs._make_enum
        type_ = factory(name or "", self.cs.resolve(base_type_str), values)

        if name is not None:
            # Register the enum/flag type if it has a name
            # Anonymous enums/flags are handled in the top level parse loop
            self.cs.add_type(type_.__name__, type_)

        return type_

    # Field parsing

    def _parse_field_list(self) -> list[Field]:
        """Parse a list of fields inside a struct/union body until the closing brace."""
        fields: list[Field] = []

        while not self._at(TokenType.RBRACE):
            self._assert_not_eof()

            fields.append(self._parse_field())

            # Handle multiple fields declared in the same line, e.g., `int x, y, z;` or `struct { ... } a, b;`
            while self._match(TokenType.COMMA):
                type_, name, bits = self._parse_field_name(fields[-1].type)
                fields.append(Field(name, type_, bits))

            self._expect(TokenType.SEMICOLON)

        return fields

    def _parse_field(self) -> Field:
        """Parse a single field declaration."""

        # Regular field: `type name`
        type_ = self._parse_type_spec()

        # Handle the case where a semicolon follows immediately (e.g., anonymous struct/unions)
        if self._at(TokenType.SEMICOLON):
            return Field(None, type_, None)

        type_, name, bits = self._parse_field_name(type_)
        return Field(name, type_, bits)

    def _parse_field_name(self, base_type: type[BaseType]) -> tuple[type[BaseType], str, int | None]:
        """Parses ``'*'* IDENTIFIER ('[' expr? ']')* (':' NUMBER)?``."""
        type_ = base_type

        # Pointer stars
        while self._match(TokenType.STAR):
            type_ = self.cs._make_pointer(type_)

        # Field name
        name = self._expect(*_IDENTIFIER_TYPES).value

        # Array dimensions
        type_ = self._parse_array_dimensions(type_)

        # Bitfield
        bits = None
        if self._match(TokenType.COLON):
            bits = int(self._expect(TokenType.NUMBER).value, 0)

        return type_, name.strip(), bits

    def _parse_array_dimensions(self, base_type: type[BaseType]) -> type[BaseType]:
        """Parse array dimensions following a field name, e.g., ``field[10][20]``."""
        dimensions: list[int | Expression] = []

        while self._match(TokenType.LBRACKET):
            if self._at(TokenType.RBRACKET):
                dimensions.append(None)
            else:
                expression = self._collect_until(TokenType.RBRACKET)
                count = Expression(expression)
                try:
                    count = count.evaluate(self.cs)
                except Exception:
                    pass
                dimensions.append(count)
            self._expect(TokenType.RBRACKET)

        type_ = base_type
        for count in reversed(dimensions):
            if issubclass(type_, BaseArray) and count is None:
                raise ParserError("Depth required for multi-dimensional array")
            type_ = self.cs._make_array(type_, count)

        return type_

    # Type resolution

    def _parse_type_spec(self) -> type[BaseType]:
        """Parse a type specifier, handling multi-word types like ``unsigned long long``.

        Uses lookahead to disambiguate type words from field names: if the next identifier is followed by a
        field delimiter (any of ``;[:,}``) it is the field name, not part of the type — unless the current accumulated
        parts don't form a valid type yet.
        """
        first = self._current()

        # Handle struct/union/enum/flag inline definitions as type specifiers
        if first.type in (TokenType.STRUCT, TokenType.UNION):
            return self._parse_struct_or_union()

        if first.type in (TokenType.ENUM, TokenType.FLAG):
            return self._parse_enum_or_flag()

        # Otherwise, accumulate identifiers for the type specifier until we hit a non-identifier or a field delimiter
        parts = [self._expect(TokenType.IDENTIFIER).value]

        while self._at(TokenType.IDENTIFIER):
            next_after = self._peek(1)

            if next_after.type in (
                TokenType.SEMICOLON,
                TokenType.LBRACKET,
                TokenType.COLON,
                TokenType.COMMA,
                TokenType.RBRACE,
            ):
                # This identifier is followed by a field delimiter, it should be the field name,
                # UNLESS the current parts don't form a valid type yet.
                if " ".join(parts) in self.cs.typedefs:
                    break

                # Current parts don't resolve, consume and hope this completes the type name
                # (will error on resolve if not).
                parts.append(self._take().value)
            elif next_after.type == TokenType.STAR:
                # Field name starts with * (pointer). This identifier is the last type word, consume it and then stop.
                parts.append(self._take().value)
                break
            elif next_after.type == TokenType.IDENTIFIER:
                # More identifiers follow, consume this one as part of the type.
                parts.append(self._take().value)
            else:
                break

        return self.cs.resolve(" ".join(parts))

    # Custom lookup definitions

    def _parse_lookup(self) -> None:
        """Parse a lookup definition."""
        value = self._take().value

        # Parse $name = { dict }
        # Find the name and dict parts
        dollar_rest = value.lstrip("$")
        name, _, lookup = dollar_rest.partition("=")

        d = ast.literal_eval(lookup.strip())
        self.cs.lookups[name.strip()] = {self.cs.consts[k]: v for k, v in d.items()}

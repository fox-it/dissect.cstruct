from __future__ import annotations

import builtins


class Error(Exception):
    """Base class for all exceptions."""


class DefinitionError(Error, ValueError):
    """A type definition is invalid."""


class LexerError(DefinitionError):
    """The type definition can't be tokenized."""


class ParserError(DefinitionError):
    """The type definition can't be parsed."""


class ResolveError(DefinitionError):
    """The type definition can't be resolved."""


class ExpressionParserError(DefinitionError):
    """The expression can't be parsed."""


class UnknownIdentifierError(ExpressionParserError):
    """The identifier is not defined."""


class ReadError(Error, ValueError):
    """The data can't be parsed."""


class NullPointerDereference(ReadError):
    """A pointer is null, but it was dereferenced."""


class WriteError(Error, ValueError):
    """The value can't be written."""


class EOFError(Error, builtins.EOFError):
    """The data ends before the value does."""

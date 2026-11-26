# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Declarative syntax for structures and unions in `dissect.cstruct.declarative`, using classes with type annotations.
- `asdict()` returns the field values of a structure or union as a dict, with nested structures as dicts and arrays as lists. `asjson()` returns them as a JSON string, with bytes as base64 and enum members as numbers. `JSONEncoder` encodes structures as part of other data with `json.dumps()`.
- `sizeof` and `offsetof` in expressions accept a type name like the type of a field, e.g. `sizeof(struct header *[4])`. An argument that isn't a type name raises an `ExpressionParserError` when the expression is created.
- `copy()` method (and `copy.copy()`) to copy a `cstruct` instance with its types, constants and settings. Changes to the copy, such as new definitions or a different endianness, don't affect the original. Enums and flags of a copy are separate classes, so their members don't compare equal to those of the original. Compare against the copied enum, or with the value instead: `c2.Color.RED == cs.Color.RED.value`.

### Changed

- Optimize storage of field sizes.
- Setting the `endian` attribute of a `cstruct` instance accepts the same values as the `endian` argument, e.g. `cs.endian = "big"`, and raises a `ValueError` for an invalid value.
- Rename `_sizes` property of `Structure` to `__sizes__`.
- Rename `_values` property of `Structure` to `__values__`.
- Rename the `signed` attribute of integer and LEB128 types to `__signed__`, like the other attributes of types. The `signed` property is deprecated.
- Added `load` argument to `cstruct` class, allowing direct initialization with a definition (i.e. `cstruct(cdef)` instead of `cstruct().load(cdef)`. Other arguments to `cstruct` are now keyword only.
- Replace `compiler.compile` and the `Compiler` class with `compiler.compile_structure`.
- Improve parsing performance:
  - Compiled structures construct objects directly and inline static nested structures, unions and bit fields.
  - Static unions are compiled too.
  - Structures are compiled on first use, which makes loading definitions faster.
  - Array types are cached, so `cs.uint32[count]` no longer creates a new class on every call.
  - Compiled structures calculate the sizes of dynamic arrays directly, instead of evaluating the expression.
  - Faster paths for parsing primitive types from bytes-like objects, enum and flag lookups and flag operators.
  - Null-terminated strings are read in chunks from seekable streams.
- Improve writing performance:
  - The compiler now generates code for writing structures and unions too! It uses a similar approach, grouping fields and writes where possible.
  - `obj.dumps()` and `obj.write()` no longer create a `functools.partial` on every access. As a result, they no longer accept a `value` argument.
- `dumpstruct` can return a tree of all fields with their offset, size and value, with `output="dict"` or `output="json"`. `dumpstruct` and `hexdump` moved from `dissect.cstruct.util` to `dissect.cstruct.dump`.
- `dumpstruct` shows the fields of every element of an array of structures or unions.
- Errors are subclasses of `dissect.cstruct.Error`: `DefinitionError` for invalid definitions, `ReadError` for data that can't be parsed and `WriteError` for values that can't be written. All three are also subclasses of `ValueError`.
  - A short read raises `dissect.cstruct.exception.EOFError`, which is a subclass of `Error` and of the built-in `EOFError`. This has also been made more consistent in many places, such as `wchar`, which previously raised a `UnicodeDecodeError`.
  - Arithmetic errors in expressions, such as division by zero, now raise a `ReadError`.
  - A value that can't be written raises a `WriteError` with the original error as its cause
  - Invalid definitions raise a `DefinitionError`.
  - A constant expression that can't be calculated during `load`, e.g. a division by zero, raises a `ParserError`.
  - `offsetof` raises a `TypeError` for a type that isn't a structure, instead of an `AttributeError` or an error about a missing field. In an expression, the errors of `sizeof` and `offsetof` raise a `DefinitionError`.
  - Errors that `load` raises include the line of the definition.
  - `ArraySizeError` is removed. A value that is longer than its static array raises a `WriteError`.
  - `write()` raises a `TypeError` for an object that can't be written to, like `read()` does.
- `bytes(obj)` works on instances of all types. It gives the byte representation of the value.
  - For null-terminated arrays, it does not include the null terminator. Use `cls.dumps(obj)` to include the null terminator.
  - For integer types, `bytearray(obj)` gives as many zero bytes as its value, e.g. `bytearray(cs.uint32(5))` gives 5 zero bytes. Use `bytearray(bytes(obj))` instead.
- `char` and `char` arrays no longer accept a string, when they're created or written. Encode the string to bytes first.
- Writing doesn't convert values anymore (e.g. `type.write(value)`, or manually setting an attribute on a structure instance): a `char` doesn't accept an int, and `uint8` arrays don't accept bytes. Convert the value first, e.g. `cs.char(0x41)` or `cs.uint8[2](b"\x01\x02")`, or pass it as an argument when the structure is created.
- Creating a `char`, a `wchar` or an array from a value instead of from data:
  - An int creates a `char` with that byte, e.g. `cs.char(0x41)` is `b"A"`.
  - Arrays of all types with a fixed number of entries add default entries to a value with fewer entries, e.g. `cs.char[4]([0x41])` is `b"A\x00\x00\x00"`, `cs.wchar[4]("A")` is `"A\x00\x00\x00"` and `cs.uint8[4]([1])` and `cs.uleb128[4]([1])` are `[1, 0, 0, 0]`.
  - A value with more entries than the array, or more than one character for a `char` or `wchar`, raises a `ValueError`.
  - Without a value, the result is the default value, e.g. `cs.char()` is `b"\x00"` and `cs.uint8[4]()` is `[0, 0, 0, 0]`.
  - `TypeError` is raised for unsupported values.
- On Python 3.12 and newer, instances of all types support the buffer protocol, so that e.g. `fh.write(obj)` works.
- Values that are given when a structure or union is created are converted to the types of their fields, like the type does. E.g. in `struct test { uint16 values[2]; }`, `cs.test(values=[1, 2]).values` is a `uint16[2]` and `cs.test(values=b"\x01\x00\x02\x00").values` is `[1, 2]`.
  - Values that are set as attributes aren't converted, e.g. `cs.test().values = [1, 2]`. For performance reasons this is impractical.

### Deprecated

- `obj.dumps()` and `obj.write(fh)` on instances. Use `cls.dumps(obj)` and `cls.write(fh, obj)` instead.

### Fixed

- `dumpstruct` colors the right bytes of structures with padding and unions.
- Structures and unions no longer share nested structures and arrays between their default values.
- Unions can be created with default values and read if they have doubly nested structures or nested unions.
- Writing a `bytearray` to a `char` array no longer modifies the `bytearray`.
- Writing a structure correctly returns the amount of bytes written, including padding and bit fields.
- Writing a structure raises a `WriteError` for missing attributes and for values of a nested structure field that aren't a structure, instead of writing default values.
- A surrogate pair takes up two entries of a `wchar` array, so writing it no longer writes more bytes than the size of the array.
- A `wchar` string can hold a lone surrogate, instead of raising an error for the whole structure when reading or writing it. Bytes are written back as they were stored.
- Writing more than a single character to a `char` or `wchar` raises a `WriteError`, instead of writing all of it and moving the fields after it. An empty value is padded.
- A plain integer can be written to an enum or flag field, including a bit field.
- `dumpstruct` shows the fields of a structure in a union in a union, instead of only its `repr`.
- Writing a value that doesn't fit in its bit field raises a `WriteError`, instead of changing the fields next to it.
- Bit fields of a type that isn't an integer, `char`, enum or flag raise a `DefinitionError` when they're defined, instead of an error or wrong bytes when they're read or written.
- An `Expression` is parsed when it's created. An invalid array size that refers to a field, e.g. `char a[n +]`, raises a `ParserError` during `load`, instead of an `ExpressionParserError` on every read.
- `offsetof` gives the offsets of C for the fields of a union and the fields of an anonymous nested structure or union, instead of an error or the offset in the nested type.
- An empty expression raises "not enough operands" instead of "too many operands".
- Writing an array with a fixed number of entries of a dynamic size, e.g. `uleb128 a[4]` or an array of structures with a dynamic size, pads it to its number of entries or raises a `WriteError` if it's too long, instead of writing as many entries as the value has.

## [4.5] - 20-05-2025

### Added

- Introduce experimental tool `cstruct-stubgen` to generate type stubs for cstruct definitions.

### Fixed

- Generated classes are now hashable.
- Suppress spurious `TypeError: Dynamic size` errors when using cstruct interactively.

## [4.4] - 03-10-2025

### Fixed

- Resolve documentation warnings.

### Changed

- Use the Ruff linter.

## [4.3] - 11-18-2024

### Fixed

- All cstruct types are now correctly default-initialized using the `__default__` member.

## [4.2] - 10-10-2024

### Fixed

- The string representation of enums now outputs the name of the constants.

## [4.1] - 10-09-2024

### Fixed

- Declaring an array of a nested struct type now works as intended.

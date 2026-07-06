# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Declarative syntax for structures and unions in `dissect.cstruct.declarative`, using classes with type annotations.

### Changed

- Optimize storage of field sizes.
- Rename `_sizes` property of `Structure` to `__sizes__`.
- Rename `_values` property of `Structure` to `__values__`.
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

### Fixed

- `dumpstruct` colors the right bytes of structures with padding and unions.
- Structures and unions no longer share nested structures and arrays between their default values.
- Unions can be created with default values and read if they have doubly nested structures or nested unions.
- Writing a `bytearray` to a `char` array no longer modifies the `bytearray`.
- Writing a structure correctly returns the amount of bytes written, including padding and bit fields.
- Writing a structure raises an `AttributeError` for missing attributes and for values of a nested structure field that aren't a structure, instead of writing default values.
- A surrogate pair takes up two entries of a `wchar` array, so writing it no longer writes more bytes than the size of the array.
- A `wchar` string can hold a lone surrogate, instead of raising an error for the whole structure when reading or writing it. Bytes are written back as they were stored.
- Writing more than a single character to a `char` or `wchar` raises a `ValueError`, instead of writing all of it and moving the fields after it. An empty value is padded.

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

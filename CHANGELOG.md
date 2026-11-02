# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

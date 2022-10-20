# dissect.cstruct

A Dissect module implementing a parser for C-like structures. Structure parsing in Python made easy. With cstruct, you
can write C-like structures and use them to parse binary data, either as file-like objects or bytestrings.

Parsing binary data with cstruct feels familiar and easy. No need to learn a new syntax or the quirks of a new parsing
library before you can start parsing data. The syntax isn't strict C but it's compatible with most common structure
definitions. You can often use structure definitions from open-source C projects and use them out of the box with little
to no changes. Need to parse an EXT4 super block? Just copy the structure definition from the Linux kernel source code.
Need to parse some custom file format? Write up a simple structure and immediately start parsing data, tweaking the
structure as you go.

By design cstruct is incredibly simple. No complex syntax, filters, pre- or post-processing steps. Just structure
parsing. For more information, please see [the documentation](https://docs.dissect.tools/en/latest/projects/dissect.cstruct/index.html).

## Installation

`dissect.cstruct` is available on [PyPI](https://pypi.org/project/dissect.cstruct/).

```bash
pip install dissect.cstruct
```

This module is also automatically installed if you install the `dissect` package.

## Build and test instructions

This project uses `tox` to build source and wheel distributions. Run the following command from the root folder to build
these:

```bash
tox -e build
```

The build artifacts can be found in the `dist/` directory.

`tox` is also used to run linting and unit tests in a self-contained environment. To run both linting and unit tests
using the default installed Python version, run:

```bash
tox
```

For a more elaborate explanation on how to build and test the project, please see [the
documentation](https://docs.dissect.tools/en/latest/contributing/developing.html#building-testing).

## Contributing

The Dissect project encourages any contribution to the codebase. To make your contribution fit into the project, please
refer to [the style guide](https://docs.dissect.tools/en/latest/contributing/style-guide.html).

## Usage
All you need to do is instantiate a new cstruct instance and load some structure definitions in there. After that you can start using them from your Python code.

```python
from dissect import cstruct

# Default endianness is LE, but can be configured using a kwarg or setting the 'endian' attribute
# e.g. cstruct.cstruct(endian='>') or cparser.endian = '>'
cparser = cstruct.cstruct()
cparser.load("""
#define SOME_CONSTANT   5

enum Example : uint16 {
    A, B = 0x5, C
};

struct some_struct {
    uint8   field_1;
    char    field_2[SOME_CONSTANT];
    char    field_3[field_1 & 1 * 5];  // Some random expression to calculate array length
    Example field_4[2];
};
""")

data = b'\x01helloworld\x00\x00\x06\x00'
result = cparser.some_struct(data)  # Also accepts file-like objects
assert result.field_1 == 0x01
assert result.field_2 == b'hello'
assert result.field_3 == b'world'
assert result.field_4 == [cparser.Example.A, cparser.Example.C]

assert cparser.Example.A == 0
assert cparser.Example.C == 6
assert cparser.Example(5) == cparser.Example.B

assert result.dumps() == data

# You can also instantiate structures from Python by using kwargs
# Note that array sizes are not enforced
instance = cparser.some_struct(field_1=5, field_2='lorem', field_3='ipsum', field_4=[cparser.Example.B, cparser.Example.A])
assert instance.dumps() == b'\x05loremipsum\x05\x00\x00\x00'
```

By default, all structures are compiled into classes that provide optimised performance. You can disable this by passing a `compiled=False` keyword argument to the `.load()` call. You can also inspect the resulting source code by accessing the source attribute of the structure: `print(cparser.some_struct.source)`.

More examples can be found in the `examples` directory.

## Features
### Structure parsing
Write simple C-like structures and use them to parse binary data, as can be seen in the examples.

### Type parsing
Aside from loading structure definitions, any of the supported types can be used individually for parsing data. For example, the following is all supported:

```python
from dissect import cstruct
cs = cstruct.cstruct()
# Default endianness is LE, but can be configured using a kwarg or setting the attribute
# e.g. cstruct.cstruct(endian='>') or cs.endian = '>'
assert cs.uint32(b'\x05\x00\x00\x00') == 5
assert cs.uint24[2](b'\x01\x00\x00\x02\x00\x00') == [1, 2]  # You can also parse arrays using list indexing
assert cs.char[None](b'hello world!\x00') == b'hello world!'  # A list index of None means null terminated
```

### Unions and nested structures
Unions and nested structures are supported, both anonymous and named.

```python
cdef = """
struct test_union {
    char magic[4];
    union {
        struct {
            uint32 a;
            uint32 b;
        } a;
        struct {
            char   b[8];
        } b;
    } c;
};

struct test_anonymous {
    char magic[4];
    struct {
        uint32 a;
        uint32 b;
    };
    struct {
        char   c[8];
    };
};
"""
c = cstruct.cstruct()
c.load(cdef)

assert len(c.test_union) == 12

a = c.test_union(b'ohaideadbeef')
assert a.magic == b'ohai'
assert a.c.a.a == 0x64616564
assert a.c.a.b == 0x66656562
assert a.c.b.b == b'deadbeef'

assert a.dumps() == b'ohaideadbeef'

b = c.test_anonymous(b'ohai\x39\x05\x00\x00\x28\x23\x00\x00deadbeef')
assert b.magic == b'ohai'
assert b.a == 1337
assert b.b == 9000
assert b.c == b'deadbeef'
```

### Parse bit fields
Bit fields are supported as part of structures. They are properly aligned to their boundaries.

```python
bitdef = """
struct test {
    uint16  a:1;
    uint16  b:1;  # Read 2 bits from an uint16
    uint32  c;    # The next field is properly aligned
    uint16  d:2;
    uint16  e:3;
};
"""
bitfields = cstruct.cstruct()
bitfields.load(bitdef)

d = b'\x03\x00\xff\x00\x00\x00\x1f\x00'
a = bitfields.test(d)

assert a.a == 0b1
assert a.b == 0b1
assert a.c == 0xff
assert a.d == 0b11
assert a.e == 0b111
assert a.dumps() == d
```

### Enums
The API to access enum members and their values is similar to that of the native Enum type in Python 3. Functionally, it's best comparable to the IntEnum type.

### Custom types
You can implement your own types by subclassing `BaseType` or `RawType`, and adding them to your cstruct instance with `addtype(name, type)`

### Custom definition parsers
Don't like the C-like definition syntax? Write your own syntax parser!

## Copyright and license

Dissect is released as open source by Fox-IT (<https://www.fox-it.com>) part of NCC Group Plc
(<https://www.nccgroup.com>).

Developed by the Dissect Team (<dissect@fox-it.com>) and made available at <https://github.com/fox-it/dissect>.

License terms: AGPL3 (<https://www.gnu.org/licenses/agpl-3.0.html>). For more information, see the LICENSE file.

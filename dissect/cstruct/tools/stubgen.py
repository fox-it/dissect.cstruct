from __future__ import annotations

import argparse
import importlib
import importlib.util
import logging
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from dissect.cstruct import types
from dissect.cstruct.cstruct import cstruct

if TYPE_CHECKING:
    from types import ModuleType

log = logging.getLogger(__name__)


def load_module(path: Path, base: Path) -> ModuleType | None:
    module = None
    try:
        relative_path = path.relative_to(base)
        module_tuple = (*relative_path.parent.parts, relative_path.stem)
        spec = importlib.util.spec_from_file_location(".".join(module_tuple), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        log.warning("Unable to import %s", path, exc_info=True)
        log.debug("Error while trying to import module %s", path, exc_info=e)

    return module


def generate_file_stub(path: Path, base: Path) -> str:
    tmp_module = load_module(path, base)
    if tmp_module is None or not hasattr(tmp_module, "cstruct"):
        return ""

    imports = [
        "# Generated by cstruct-stubgen",
        "from typing import overload, BinaryIO",
        "",
        "from typing_extensions import TypeAlias",
        "",
        "import dissect.cstruct as __cs__",
        "",
        "",
    ]
    body = []

    for name, obj in tmp_module.__dict__.items():
        if isinstance(obj, cstruct):
            stub = generate_cstruct_stub(obj, module_prefix="__cs__.", cls_name=f"_{name}")
            body.append(stub)
            body.append(f"{name}: _{name}")

    if not body:
        return ""

    return "\n".join(imports + body + [""])


def generate_cstruct_stub(cs: cstruct, module_prefix: str = "", cls_name: str = "") -> str:
    cls_name = cls_name or "cstruct"

    empty_cs = cstruct()

    cs_prefix = f"{cls_name}."
    header = [f"class {cls_name}({module_prefix}cstruct):"]
    body = []
    indent = " " * 4

    # Constants first
    for name, value in cs.consts.items():
        if name in empty_cs.consts:
            continue
        body.append(textwrap.indent(f"{name}: {type(value).__name__} = ...", prefix=indent))

    defined_names = set()

    # Then typedefs
    for name, typedef in cs.typedefs.items():
        if name in empty_cs.typedefs:
            continue

        if typedef.__name__ in defined_names:
            # Create an alias to the type if we have already seen it before.
            stub = f"{name}: {typedef.__name__}"

        elif issubclass(typedef, types.Enum):
            stub = generate_enum_stub(typedef, cs_prefix=cs_prefix, module_prefix=module_prefix)
        elif issubclass(typedef, types.Structure):
            stub = generate_structure_stub(typedef, cs_prefix=cs_prefix, module_prefix=module_prefix)
        elif issubclass(typedef, types.BaseType):
            stub = generate_generic_stub(typedef, cs_prefix=cs_prefix, module_prefix=module_prefix)
        elif isinstance(typedef, str):
            stub = f"{name}: TypeAlias = {typedef}"
        else:
            raise TypeError(f"Unknown typedef: {typedef}")

        defined_names.add(typedef.__name__)

        body.append(textwrap.indent(stub, prefix=indent))

    if not body:
        body.append(textwrap.indent("...", prefix=indent))

    return "\n".join(header + body)


def generate_typehint(
    type_: type[types.BaseType],
    prefix: str = "",
    module_prefix: str = "",
) -> str:
    if issubclass(type_, types.CharArray):
        return f"{module_prefix}CharArray"
    if issubclass(type_, types.WcharArray):
        return f"{module_prefix}WcharArray"
    if issubclass(type_, types.Pointer):
        return f"{module_prefix}Pointer[{generate_typehint(type_.type, prefix, module_prefix)}]"
    if issubclass(type_, types.Array):
        return f"{module_prefix}Array[{generate_typehint(type_.type, prefix, module_prefix)}]"
    return f"{prefix}{type_.__name__}"


def generate_generic_stub(
    type_: type[types.BaseType],
    name_prefix: str = "",
    cs_prefix: str = "",
    module_prefix: str = "",
) -> str:
    return f"class {name_prefix}{type_.__name__}({module_prefix}{type_.__base__.__name__}): ..."


def generate_enum_stub(
    enum: type[types.Enum],
    name_prefix: str = "",
    cs_prefix: str = "",
    module_prefix: str = "",
) -> str:
    result = [f"class {name_prefix}{enum.__name__}({module_prefix}{enum.__base__.__name__}):"]
    result.extend(f"    {key} = ..." for key in enum.__members__)

    return "\n".join(result)


def generate_structure_stub(
    structure: type[types.Structure],
    name_prefix: str = "",
    cs_prefix: str = "",
    module_prefix: str = "",
) -> str:
    result = [f"class {name_prefix}{structure.__name__}({module_prefix}{structure.__base__.__name__}):"]

    indent = " " * 4

    args = ["self"]
    for field_name, field in structure.fields.items():
        type_name = field.type.__name__
        inlined = False

        # If it's a structure and not globally defined, add an inline stub for it
        nested_type = field.type
        while issubclass(nested_type, types.BaseArray):
            nested_type = nested_type.type

        if issubclass(nested_type, types.Structure) and type_name not in structure.cs.typedefs:
            inlined = True
            inline_stub = generate_structure_stub(nested_type, cs_prefix=cs_prefix, module_prefix=module_prefix)

            result.append(textwrap.indent(inline_stub, prefix=indent))

        type_hint = generate_typehint(field.type, "" if inlined else f"{cs_prefix}", module_prefix)
        result.append(f"    {field_name}: {type_hint}")

        args.append(f"{field_name}: {type_hint} | None = ...")

    result.append(textwrap.indent("@overload", prefix=indent))
    result.append(textwrap.indent(f"def __init__({', '.join(args)}): ...", prefix=" " * 4))
    result.append(textwrap.indent("@overload", prefix=indent))
    result.append(
        textwrap.indent("def __init__(self, fh: bytes | memoryview | bytearray | BinaryIO, /): ...", prefix=indent)
    )
    return "\n".join(result)


def setup_logger(verbosity: int) -> None:
    level = logging.INFO
    if verbosity >= 1:
        level = logging.DEBUG

    logging.basicConfig(level=level)


def main() -> None:
    parser = argparse.ArgumentParser("cstruct-stubify", description="Create .pyi stub files for cstruct definitions")
    parser.add_argument("path", type=Path, help="path to the file or directory to create stubs for")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    setup_logger(args.verbose)

    path: Path = args.path
    for file in path.rglob("*.py") if path.is_dir() else [path]:
        if file.is_file() and file.suffix == ".py":
            stub = generate_file_stub(file, path)
            if not stub:
                continue

            stub_file = file.with_suffix(".pyi")
            log.info("Writing stub of file %s to %s", file, stub_file.name)
            stub_file.write_text(stub)


if __name__ == "__main__":
    main()

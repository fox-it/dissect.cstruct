from __future__ import annotations

import importlib
import importlib.util
import logging
from argparse import ArgumentParser
from pathlib import Path
from textwrap import indent
from types import ModuleType
from typing import TYPE_CHECKING, Any

import dissect.cstruct.types as types
from dissect.cstruct import cstruct

if TYPE_CHECKING:
    from collections.abc import Iterable


log = logging.getLogger(__name__)


def load_module(path: Path, base_path: Path) -> ModuleType | None:
    module = None
    try:
        relative_path = path.relative_to(base_path)
        module_tuple = (*relative_path.parent.parts, relative_path.stem)
        spec = importlib.util.spec_from_file_location(".".join(module_tuple), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        log.warning("Unable to import %s", path)
        log.debug("Error while trying to import module %s", path, exc_info=e)

    return module


def to_type(_type: type | Any) -> type:
    if not isinstance(_type, type):
        _type = type(_type)
    return _type


def stubify_file(path: Path, base_path: Path) -> str:
    tmp_module = load_module(path, base_path)
    if tmp_module is None:
        return ""

    if not hasattr(tmp_module, "cstruct"):
        return ""

    all_types = types.__all__.copy()
    all_types.sort()
    all_types.append("")

    cstruct_types = indent(",\n".join(all_types), prefix=" " * 4)
    result = [
        "from __future__ import annotations\n",
        "from typing import overload, BinaryIO\n",
        "from typing_extensions import TypeAlias\n",
        "from dissect.cstruct import cstruct",
        f"from dissect.cstruct.types import (\n{cstruct_types})\n",
    ]

    prev_entries = len(result)

    for name, variable in tmp_module.__dict__.items():
        if name.startswith("__"):
            continue

        if isinstance(variable, cstruct):
            result.append(stubify_cstruct(variable, name))

    if prev_entries == len(result):
        return ""

    # Empty line at the end of the file
    result.append("")
    return "\n".join(result)


def stubify_cstruct(c_structure: cstruct, name: str = "", ignore_type_defs: Iterable[str] | None = None) -> str:
    ignore_type_defs = ignore_type_defs or []

    result = []
    indentation = ""
    if name:
        result.append(f"class {name}(cstruct):")
        indentation = " " * 4
        c_structure.__type_def_name__ = name

    prev_length = len(result)
    for const, value in c_structure.consts.items():
        result.append(indent(f"{const}: {type(value).__name__} = ...", prefix=indentation))

    if type_defs := stubify_typedefs(c_structure, ignore_type_defs, indentation):
        result.append(type_defs)

    if prev_length == len(result):
        # an empty definition, add elipses
        result.append(indent("...", prefix=indentation))

    return "\n".join(result)


def stubify_typedefs(c_structure: cstruct, ignore_type_defs: Iterable[str] | None = None, indentation: str = "") -> str:
    ignore_type_defs = ignore_type_defs or []

    result = []
    for name, type_def in c_structure.typedefs.items():
        if name in ignore_type_defs:
            continue

        if isinstance(type_def, types.MetaType) and (text := type_def.to_type_stub(name)):
            result.append(indent(text, prefix=indentation))

    return "\n".join(result)


def setup_logger(verbosity: int) -> None:
    level = logging.INFO
    if verbosity >= 1:
        level = logging.DEBUG

    logging.basicConfig(level=level)


def main() -> None:
    description = """
        Create stub files for cstruct definitions.

        These stub files are in a `.pyi` format and provides type information to cstruct definitions.
    """

    parser = ArgumentParser("stubify", description=description)
    parser.add_argument("path", type=Path)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    setup_logger(args.verbose)

    file_path: Path = args.path

    iterator = file_path.rglob("*.py")
    if file_path.is_file():
        iterator = [file_path]

    for file in iterator:
        if file.is_file() and file.suffix == ".py":
            stub = stubify_file(file, file_path)
            if not stub:
                continue

            with file.with_suffix(".pyi").open("wt") as output_file:
                log.info("Writing stub of file %s to %s", file, output_file.name)
                output_file.write(stub)


if __name__ == "__main__":
    main()

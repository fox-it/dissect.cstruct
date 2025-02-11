from __future__ import annotations

import importlib
import importlib.util
import logging
from argparse import ArgumentParser
from pathlib import Path
from textwrap import indent
from types import ModuleType
from typing import Iterable

import dissect.cstruct.types as types
from dissect.cstruct import cstruct

log = logging.getLogger(__name__)


def load_module(path: Path, base_path: Path) -> ModuleType | None:
    module = None
    try:
        relative_path = path.relative_to(base_path)
        module_tuple = (*relative_path.parent.parts, relative_path.stem)
        spec = importlib.util.spec_from_file_location(".".join(module_tuple), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        log.error("Unable to import %s", path)
        log.debug("Error while trying to import module %s", path, exc_info=e)


def stubify_file(path: Path, base_path: Path) -> str:
    tmp_module = load_module(path, base_path)
    if tmp_module is None:
        return ""

    if not hasattr(tmp_module, "cstruct"):
        return ""

    all_types = types.__all__.copy()
    all_types.sort()

    cstruct_types = ", ".join(all_types)
    result = [
        "from __future__ import annotations\n",
        "from typing_extensions import TypeAlias",
        "from dissect.cstruct import cstruct",
        f"from dissect.cstruct.types import {cstruct_types}\n",
    ]

    empty_cstruct = cstruct()

    result.append(stubify_typedefs(empty_cstruct))
    prev_entries = len(result)

    for name, variable in tmp_module.__dict__.items():
        if name.startswith("__"):
            continue

        if isinstance(variable, cstruct):
            result.append(stubify_cstruct(variable, name, empty_cstruct.typedefs.keys()))

    if prev_entries == len(result):
        return ""

    return "\n".join(result)


def stubify_cstruct(c_structure: cstruct, name: str = "", ignore_type_defs: Iterable[str] | None = None) -> str:
    ignore_type_defs = ignore_type_defs or []

    result = []
    indentation = ""
    if name:
        result.append(f"class {name}(cstruct):")
        indentation = " " * 4

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
        if file.is_file() and ".py" == file.suffix:
            stub = stubify_file(file, file_path)
            if not stub:
                continue

            with file.with_suffix(".pyi").open("wt") as output_file:
                log.info("Writing stub of file %s to %s", file, output_file.name)
                output_file.write(stub)


if __name__ == "__main__":
    main()

from __future__ import annotations

import importlib
import importlib.util
import io
import logging
from argparse import ArgumentParser
from pathlib import Path
from textwrap import indent
from types import ModuleType

import dissect.cstruct.types as types
from dissect.cstruct import cstruct

log = logging.getLogger(__name__)


def load_module(path: Path, base_path: Path) -> ModuleType:
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

    buffer = io.StringIO()
    all_types = types.__all__.copy()
    all_types.sort()

    cstruct_types = ", ".join(all_types)
    buffer.write("from __future__ import annotations\n\n")
    buffer.write("from dissect.cstruct import cstruct\n")
    buffer.write(f"from dissect.cstruct.types import {cstruct_types}\n\n")

    empty_cstruct = cstruct()

    buffer.write(stubify_typedefs(empty_cstruct))
    buffer.write("\n")

    prev_offset = buffer.tell()

    for name, variable in tmp_module.__dict__.items():
        if name.startswith("__"):
            continue

        if isinstance(variable, cstruct):
            buffer.write(stubify_cstruct(variable, name, empty_cstruct.typedefs.keys()))

    output = buffer.getvalue()
    if buffer.tell() == prev_offset:
        output = ""

    buffer.close()

    return output


def stubify_cstruct(c_structure: cstruct, name: str = "", ignore_type_defs: list[str] | None = None) -> str:
    ignore_type_defs = ignore_type_defs or []

    buffer = io.StringIO()
    indentation = ""
    if name:
        buffer.write(f"class {name}(cstruct):\n")
        indentation = " " * 4

    prev_offset = buffer.tell()
    for const, value in c_structure.consts.items():
        buffer.write(indent(f"{const}: {type(value).__name__}=...\n", prefix=indentation))

    buffer.write(stubify_typedefs(c_structure, ignore_type_defs, indentation))

    if prev_offset == buffer.tell():
        buffer.write(indent("...", prefix=indentation))

    output_value = buffer.getvalue()
    buffer.close()
    return output_value


def stubify_typedefs(c_structure: cstruct, ignore_type_defs: list[str] = None, indentation: str = "") -> str:
    ignore_type_defs = ignore_type_defs or []
    buffer = io.StringIO()
    for name, type_def in c_structure.typedefs.items():
        if name in ignore_type_defs:
            continue
        if isinstance(type_def, types.MetaType) and (text := type_def.to_stub(name)):
            buffer.write(indent(text, prefix=indentation))
            buffer.write("\n")

    output = buffer.getvalue()
    buffer.close()
    return output


def setup_logger(verbosity: int) -> None:
    if verbosity == 0:
        log.setLevel(level=logging.WARNING)
    elif verbosity == 1:
        log.setLevel(level=logging.INFO)
    elif verbosity > 1:
        log.setLevel(level=logging.DEBUG)


def main() -> None:
    description = """
        Create stub files for cstruct definitions.
    
        These stub files are in a `.pyi` format and provides `type` information to cstruct definitions.
        This in turn gives a developer insight into the elements inside the definition and 
        parameter completion when dealing with cstructs.
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
                log.info("Writing stub of file %s to %s", file, output_file)
                output_file.write(stub)


if __name__ == "__main__":
    main()

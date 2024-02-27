# Searches and creates a stub of a cstruct definitions
import importlib
import importlib.util
import io
import logging
from argparse import ArgumentParser
from pathlib import Path

from dissect.cstruct import cstruct

log = logging.getLogger(__name__)


def load_module(path: Path, base_path: Path):
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


def stubify_file(path: Path, base_path: Path):
    buffer = io.StringIO()

    buffer.write("from dissect.cstruct.types import *\n")
    prev_offset = buffer.tell()

    tmp_module = load_module(path, base_path)
    if tmp_module is None:
        return ""

    for name, variable in tmp_module.__dict__.items():
        if name.startswith("__"):
            continue

        if isinstance(variable, cstruct):
            if variable._module != tmp_module.__name__:
                continue
            buffer.write(variable.to_stub(name))

    output = buffer.getvalue()
    if buffer.tell() == prev_offset:
        output = ""

    buffer.close()

    return output


def setup_logger(verbosity: int) -> None:
    if verbosity == 0:
        log.setLevel(level=logging.WARNING)
    elif verbosity == 1:
        log.setLevel(level=logging.INFO)
    elif verbosity > 1:
        log.setLevel(level=logging.DEBUG)


def main():
    parser = ArgumentParser("stubify")
    parser.add_argument("path", type=Path)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    setup_logger(args.verbose)

    file_path: Path = args.path

    iterator = file_path.rglob("*.py")
    if file_path.is_file():
        iterator = [file_path]

    for file in iterator:
        if file.is_file() and ".py" in file.suffixes:
            stub = stubify_file(file, file_path)
            if not stub:
                continue

            with file.with_suffix(".pyi").open("wt") as output_file:
                output_file.write(stub)


if __name__ == "__main__":
    main()

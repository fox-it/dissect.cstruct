# Searches and creates a stub of a cstruct definitions
from argparse import ArgumentParser
from importlib import import_module
from pathlib import Path


def stubify_file(path: Path):
    ...


def main():
    parser = ArgumentParser("stubify")
    parser.add_argument("path", type=Path, required=True)
    args = parser.parse_args()

    file_path: Path = args.path

    for file in file_path.glob("*.py"):
        if file.is_file() and ".py" in file.suffixes:
            stubify_file(file)


if __name__ == "__main__":
    main()

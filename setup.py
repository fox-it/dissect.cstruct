from setuptools import setup

with open("README.md") as fh:
    long_description = fh.read()

setup(
    name="dissect.cstruct",
    author="Fox-IT",
    description="Structure parsing in Python made easy.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="cstruct struct dissect structure binary pack packer unpack unpacker parser parsing",
    url="https://github.com/fox-it/dissect.cstruct",
    packages=["dissect.cstruct", "dissect.cstruct.types"],
)

from setuptools import find_packages, setup

setup(
    name="dissect.cstruct",
    packages=list(map(lambda v: "dissect." + v, find_packages("dissect"))),
)

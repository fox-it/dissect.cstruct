import pytest

from dissect.cstruct.cstruct import cstruct


@pytest.fixture
def cs() -> cstruct:
    return cstruct()


@pytest.fixture(params=[True, False])
def compiled(request: pytest.FixtureRequest) -> bool:
    return request.param

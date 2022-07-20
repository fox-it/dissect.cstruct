import pytest


@pytest.fixture(params=[True, False])
def compiled(request):
    return request.param

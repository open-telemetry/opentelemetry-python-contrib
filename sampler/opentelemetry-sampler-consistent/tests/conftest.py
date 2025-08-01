import random

import pytest


@pytest.fixture(autouse=True)
def random_seed():
    # We use random numbers a lot, make sure they are always the same.
    random.seed(0)

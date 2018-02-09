from . import scarcelinked

import pytest

ONE_MILLION = 10 ** 6


@pytest.mark.parametrize('left,right,expected', [
    (b'', b'', []),
    (b'abc', b'def', [(0, 3)]),
    (b'abc', b'bbq', [(0, 1), (2, 3)]),
])
def test_diff_bytes(left, right, expected):
    spans = scarcelinked.diff_bytes(left, right)
    assert spans == expected

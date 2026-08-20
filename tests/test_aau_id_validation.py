import pytest

from utils.validation import normalize_aau_undergraduate_id


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [("UGR/0000/16", "UGR/0000/16"), (" ugr/1234/09 ", "UGR/1234/09")],
)
def test_normalizes_valid_aau_undergraduate_ids(input_value, expected):
    assert normalize_aau_undergraduate_id(input_value) == expected


@pytest.mark.parametrize(
    "input_value",
    ["UGR/123/16", "UGR/12345/16", "UGR/1234/1", "PGR/1234/16", "UGR-1234-16"],
)
def test_rejects_malformed_aau_undergraduate_ids(input_value):
    with pytest.raises(ValueError, match="UGR/NNNN/YY"):
        normalize_aau_undergraduate_id(input_value)

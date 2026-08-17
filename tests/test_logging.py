import logging

from utils.logging import CorrelationIdFilter, get_correlation_id, set_correlation_id


def test_correlation_id_filter_attaches_id():
    set_correlation_id("test-cid")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    filter_ = CorrelationIdFilter()

    assert filter_.filter(record) is True
    assert getattr(record, "correlation_id") == "test-cid"
    assert get_correlation_id() == "test-cid"

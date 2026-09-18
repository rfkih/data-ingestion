import pytest

from idx_mcp.guard import GuardError, check_fill, check_status_change

ALLOWED = [("paper", "issued"), ("paper", "closed"), ("test_x", "issued"), ("live", "draft"), ("live", "cancelled")]


@pytest.mark.parametrize("book,status", ALLOWED)
def test_agent_allowed(book, status):
    check_status_change(book, status)


@pytest.mark.parametrize("status", ["issued", "closed"])
def test_agent_cannot_issue_or_close_live(status):
    with pytest.raises(GuardError, match="two-key"):
        check_status_change("live", status)
    check_status_change("live", status, actor="operator")      # the operator may


def test_live_fills_are_refused():
    check_fill("paper")
    check_fill("test_x")
    with pytest.raises(GuardError, match="live fills"):
        check_fill("live")

import pytest

from app.core.errors import ProblemError
from app.db.models import REQUEST_STATUSES, BlockRequest
from app.services.request_service import TRANSITIONS, transition

ALLOWED = [
    ("draft", "submitted"),
    ("submitted", "scheduled"),
    ("scheduled", "published"),
    ("published", "completed"),
    ("draft", "cancelled"),
    ("submitted", "cancelled"),
    ("scheduled", "cancelled"),
    ("submitted", "rejected"),
]


@pytest.mark.parametrize(("start", "end"), ALLOWED)
def test_allowed_transitions(start, end):
    request = BlockRequest(status=start)
    transition(request, end)
    assert request.status == end


def test_every_other_transition_is_refused():
    allowed = set(ALLOWED)
    for start in REQUEST_STATUSES:
        for end in REQUEST_STATUSES:
            if (start, end) in allowed:
                continue
            request = BlockRequest(status=start)
            with pytest.raises(ProblemError) as err:
                transition(request, end)
            assert (err.value.status, err.value.code) == (409, "invalid_transition")
            assert request.status == start


def test_table_matches_the_spec_exactly():
    pairs = {(a, b) for a, targets in TRANSITIONS.items() for b in targets}
    assert pairs == set(ALLOWED)


@pytest.mark.parametrize("terminal", ["completed", "cancelled", "rejected"])
def test_terminal_states_have_no_exits(terminal):
    assert terminal not in TRANSITIONS

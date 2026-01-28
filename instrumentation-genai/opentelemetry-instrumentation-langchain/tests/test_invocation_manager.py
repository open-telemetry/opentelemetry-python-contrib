# tests/test_invocation_manager.py
import uuid
from unittest import mock

import pytest

from opentelemetry.instrumentation.langchain.invocation_manager import (
    _InvocationManager,
)
from opentelemetry.util.genai.types import GenAIInvocation


@pytest.fixture
def invocation_manager():
    return _InvocationManager()


@pytest.fixture
def mock_invocation():
    return mock.Mock(spec=GenAIInvocation)


def test_add_invocation_state_without_parent(
    invocation_manager, mock_invocation
):
    run_id = uuid.uuid4()
    invocation_manager.add_invocation_state(
        run_id=run_id,
        parent_run_id=None,
        invocation=mock_invocation,
    )

    assert invocation_manager.get_invocation(run_id) == mock_invocation
    assert len(invocation_manager._invocations) == 1
    assert invocation_manager._invocations[run_id].children == []


def test_add_invocation_state_with_parent(invocation_manager, mock_invocation):
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    parent_invocation = mock.Mock(spec=GenAIInvocation)
    child_invocation = mock.Mock(spec=GenAIInvocation)

    # Add parent first
    invocation_manager.add_invocation_state(
        run_id=parent_id,
        parent_run_id=None,
        invocation=parent_invocation,
    )

    # Then add child with parent reference
    invocation_manager.add_invocation_state(
        run_id=child_id,
        parent_run_id=parent_id,
        invocation=child_invocation,
    )

    # Check that parent has child in its children list
    assert child_id in invocation_manager._invocations[parent_id].children
    assert invocation_manager.get_invocation(child_id) == child_invocation
    assert invocation_manager.get_invocation(parent_id) == parent_invocation


def test_add_invocation_state_with_nonexistent_parent(
    invocation_manager, mock_invocation
):
    run_id = uuid.uuid4()
    nonexistent_parent_id = uuid.uuid4()

    # Adding with a parent that doesn't exist should still add the child without error
    invocation_manager.add_invocation_state(
        run_id=run_id,
        parent_run_id=nonexistent_parent_id,
        invocation=mock_invocation,
    )

    assert invocation_manager.get_invocation(run_id) == mock_invocation
    assert len(invocation_manager._invocations) == 1


def test_get_nonexistent_invocation(invocation_manager):
    nonexistent_id = uuid.uuid4()
    assert invocation_manager.get_invocation(nonexistent_id) is None


def test_delete_invocation_state(invocation_manager, mock_invocation):
    run_id = uuid.uuid4()
    invocation_manager.add_invocation_state(
        run_id=run_id,
        parent_run_id=None,
        invocation=mock_invocation,
    )

    # Verify it was added
    assert invocation_manager.get_invocation(run_id) == mock_invocation

    # Delete it
    invocation_manager.delete_invocation_state(run_id)

    # Verify it was removed
    assert run_id not in invocation_manager._invocations


def test_delete_invocation_state_with_children(invocation_manager):
    parent_id = uuid.uuid4()
    child1_id = uuid.uuid4()
    child2_id = uuid.uuid4()

    parent_invocation = mock.Mock(spec=GenAIInvocation)
    child1_invocation = mock.Mock(spec=GenAIInvocation)
    child2_invocation = mock.Mock(spec=GenAIInvocation)

    # Add parent and children
    invocation_manager.add_invocation_state(
        run_id=parent_id,
        parent_run_id=None,
        invocation=parent_invocation,
    )
    invocation_manager.add_invocation_state(
        run_id=child1_id,
        parent_run_id=parent_id,
        invocation=child1_invocation,
    )
    invocation_manager.add_invocation_state(
        run_id=child2_id,
        parent_run_id=parent_id,
        invocation=child2_invocation,
    )

    # Verify initial state
    assert len(invocation_manager._invocations) == 3
    assert len(invocation_manager._invocations[parent_id].children) == 2

    # Delete parent
    invocation_manager.delete_invocation_state(parent_id)

    # Verify parent and all children were removed
    assert parent_id not in invocation_manager._invocations
    assert child1_id not in invocation_manager._invocations
    assert child2_id not in invocation_manager._invocations
    assert len(invocation_manager._invocations) == 0

"""Circuit breaker unit tests for inference fault tolerance.

The circuit breaker implements the state machine:
- CLOSED: accepting requests, increment failure_count on error
- OPEN: rejecting all requests, auto-transition to HALF_OPEN after timeout
- HALF_OPEN: testing recovery, one success → CLOSED, any failure → OPEN again

Tests verify state transitions, threshold enforcement, timeout logic, and
the recovery path from OPEN to HALF_OPEN to CLOSED.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

import pytest

from blackheart_inference.services.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerState,
)


def test_circuit_breaker_starts_closed() -> None:
    """Initial state is CLOSED with zero failures."""
    cb = CircuitBreaker(signal_id="test_signal")
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


def test_circuit_breaker_opens_after_threshold() -> None:
    """Circuit opens after failure_threshold failures."""
    cb = CircuitBreaker(signal_id="test_signal", failure_threshold=3)

    # Record 2 failures — still closed
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 2

    # Third failure triggers open
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN
    assert cb.failure_count == 3


def test_circuit_breaker_resets_on_success() -> None:
    """Success in CLOSED state resets failure count."""
    cb = CircuitBreaker(signal_id="test_signal", failure_threshold=3)

    # Record failures then a success
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2

    cb.record_success()
    assert cb.failure_count == 0
    assert cb.state == CircuitBreakerState.CLOSED


def test_circuit_breaker_allows_recovery() -> None:
    """Circuit transitions OPEN -> HALF_OPEN after timeout, then CLOSED on success."""
    cb = CircuitBreaker(
        signal_id="test_signal",
        failure_threshold=2,
        recovery_timeout_secs=1,
    )

    # Open the circuit
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    # Immediately check — still OPEN
    assert cb.state == CircuitBreakerState.OPEN

    # Wait for timeout
    time.sleep(1.1)

    # Now state should auto-transition to HALF_OPEN
    assert cb.state == CircuitBreakerState.HALF_OPEN

    # Success in HALF_OPEN → CLOSED
    cb.record_success()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


def test_circuit_breaker_can_be_reset() -> None:
    """Explicit reset() returns to CLOSED with zero failures."""
    cb = CircuitBreaker(signal_id="test_signal")

    # Create some state
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2

    # Reset
    cb.reset()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.failure_count == 0


def test_circuit_breaker_is_available_closed_and_half_open() -> None:
    """is_available() returns True for CLOSED and HALF_OPEN, False for OPEN."""
    cb = CircuitBreaker(signal_id="test_signal", failure_threshold=1)

    # CLOSED is available
    assert cb.is_available() is True

    # Open the circuit
    cb.record_failure()
    assert cb.is_available() is False

    # Wait for timeout
    time.sleep(0.5)
    cb = CircuitBreaker(
        signal_id="test_signal",
        failure_threshold=1,
        recovery_timeout_secs=0.1,
    )
    cb.record_failure()
    assert cb.is_available() is False
    time.sleep(0.15)
    # Auto-transition to HALF_OPEN
    assert cb.state == CircuitBreakerState.HALF_OPEN
    assert cb.is_available() is True


def test_circuit_breaker_failure_in_half_open_reopens() -> None:
    """Failure in HALF_OPEN transitions back to OPEN."""
    cb = CircuitBreaker(
        signal_id="test_signal",
        failure_threshold=1,
        recovery_timeout_secs=0.1,
    )

    # Open the circuit
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

    # Wait for timeout to enter HALF_OPEN
    time.sleep(0.15)
    assert cb.state == CircuitBreakerState.HALF_OPEN

    # Failure in HALF_OPEN → OPEN
    cb.record_failure()
    assert cb.state == CircuitBreakerState.OPEN

from study_assistant.interfaces.api.login_throttle import FailedLoginThrottle


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_locks_out_only_after_the_limit() -> None:
    throttle = FailedLoginThrottle(3, 60, clock=Clock())
    for _ in range(2):
        throttle.record_failure("a")
    assert throttle.retry_after("a") is None
    throttle.record_failure("a")
    assert throttle.retry_after("a") == 60


def test_clients_are_counted_separately() -> None:
    throttle = FailedLoginThrottle(1, 60, clock=Clock())
    throttle.record_failure("a")
    assert throttle.retry_after("a") == 60
    assert throttle.retry_after("b") is None


def test_lockout_ends_with_the_window() -> None:
    clock = Clock()
    throttle = FailedLoginThrottle(1, 60, clock=clock)
    throttle.record_failure("a")
    clock.now += 59.5
    assert throttle.retry_after("a") == 1
    clock.now += 0.5
    assert throttle.retry_after("a") is None


def test_failures_after_the_window_start_a_new_count() -> None:
    clock = Clock()
    throttle = FailedLoginThrottle(2, 60, clock=clock)
    throttle.record_failure("a")
    clock.now += 61
    throttle.record_failure("a")
    assert throttle.retry_after("a") is None


def test_failures_do_not_extend_the_window() -> None:
    clock = Clock()
    throttle = FailedLoginThrottle(1, 60, clock=clock)
    throttle.record_failure("a")
    clock.now += 30
    throttle.record_failure("a")
    assert throttle.retry_after("a") == 30


def test_clear_forgets_failures() -> None:
    throttle = FailedLoginThrottle(2, 60, clock=Clock())
    throttle.record_failure("a")
    throttle.clear("a")
    throttle.record_failure("a")
    assert throttle.retry_after("a") is None


def test_memory_is_bounded_by_dropping_the_oldest_client() -> None:
    throttle = FailedLoginThrottle(1, 60, clock=Clock(), max_clients=2)
    for client in ("a", "b", "c"):
        throttle.record_failure(client)
    assert throttle.retry_after("a") is None
    assert throttle.retry_after("b") == 60
    assert throttle.retry_after("c") == 60

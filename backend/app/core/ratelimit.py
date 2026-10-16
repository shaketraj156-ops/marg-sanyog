"""Login protection: a per-address rate limit and a temporary lockout after repeated failures.

State is kept in memory (one API process, no Redis). Both checks are keyed so that an email that
does not exist behaves exactly like one that does: the response never reveals which accounts exist.
"""
import math
import threading
import time
from collections import deque
from collections.abc import Callable

from app.core.errors import ProblemError


class LoginGuard:
    def __init__(
        self,
        max_failures: int = 5,
        lockout_seconds: float = 900,
        per_minute: int = 10,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self.per_minute = per_minute
        self._clock = clock
        self._lock = threading.Lock()
        self._attempts: dict[str, deque[float]] = {}  # address -> times of recent attempts
        self._failures: dict[str, tuple[int, float]] = {}  # email -> (count, time of the last one)
        self._locked_until: dict[str, float] = {}  # email -> when the lockout ends

    @staticmethod
    def _retry_after(seconds: float) -> int:
        return max(1, math.ceil(seconds))

    def check(self, email: str, address: str) -> None:
        """Call before trying a password. Raises 429 when rate limited or locked out."""
        now = self._clock()
        with self._lock:
            if len(self._attempts) > 10_000:
                self._forget_old(now)
            recent = self._attempts.setdefault(address, deque())
            while recent and recent[0] <= now - 60:
                recent.popleft()
            if len(recent) >= self.per_minute:
                wait = self._retry_after(recent[0] + 60 - now)
                raise ProblemError(
                    429,
                    "rate_limited",
                    f"Too many login attempts from this address. Try again in {wait} seconds.",
                    {"Retry-After": str(wait)},
                )
            recent.append(now)

            until = self._locked_until.get(email)
            if until is not None:
                if until > now:
                    wait = self._retry_after(until - now)
                    raise ProblemError(
                        429,
                        "too_many_attempts",
                        f"Too many failed attempts. Try again in {wait} seconds.",
                        {"Retry-After": str(wait)},
                    )
                del self._locked_until[email]  # the lockout is over: start counting afresh
                self._failures.pop(email, None)

    def record_failure(self, email: str) -> None:
        now = self._clock()
        with self._lock:
            count, last = self._failures.get(email, (0, now))
            if now - last > self.lockout_seconds:
                count = 0  # old failures are forgiven
            count += 1
            self._failures[email] = (count, now)
            if count >= self.max_failures:
                self._locked_until[email] = now + self.lockout_seconds

    def record_success(self, email: str) -> None:
        with self._lock:
            self._failures.pop(email, None)
            self._locked_until.pop(email, None)

    def _forget_old(self, now: float) -> None:
        self._attempts = {a: q for a, q in self._attempts.items() if q and q[-1] > now - 60}
        self._failures = {
            e: v for e, v in self._failures.items() if now - v[1] <= self.lockout_seconds
        }
        self._locked_until = {e: t for e, t in self._locked_until.items() if t > now}

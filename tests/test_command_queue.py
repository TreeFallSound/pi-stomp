"""Unit tests for the wifi CommandQueue — exercised without a real WifiManager."""

import threading
import time
from dataclasses import dataclass, field

import pytest

from modalapi.wifi import Command, CommandQueue


@dataclass
class _Ctx:
    """Stand-in for WifiManager. Counts calls; records call order."""
    lock: threading.Lock = field(default_factory=threading.Lock)
    started: list = field(default_factory=list)
    finished: list = field(default_factory=list)


@dataclass
class SleepCmd(Command[str]):
    name: str
    delay: float = 0.05

    def run(self, ctx: _Ctx) -> str:
        with ctx.lock:
            ctx.started.append(self.name)
        time.sleep(self.delay)
        with ctx.lock:
            ctx.finished.append(self.name)
        return self.name

    def key(self) -> str:
        return f"sleep:{self.name}"


@dataclass
class BoomCmd(Command[None]):
    def run(self, ctx: _Ctx) -> None:
        raise RuntimeError("boom")

    def key(self) -> str:
        return "boom"


def _drain(q: CommandQueue, results: list, expected: int, timeout: float = 2.0) -> None:
    """Poll the queue until `expected` results are delivered or timeout."""
    deadline = time.time() + timeout
    while len(results) < expected and time.time() < deadline:
        q.poll()
        time.sleep(0.005)
    q.poll()


@pytest.fixture
def ctx() -> _Ctx:
    return _Ctx()


@pytest.fixture
def queue(ctx):
    q = CommandQueue(ctx)
    yield q
    q.shutdown()


def test_serialization(queue, ctx):
    """Two submissions execute in submitted order, never overlapping."""
    results: list = []
    queue.submit(SleepCmd("A"), results.append)
    queue.submit(SleepCmd("B"), results.append)
    _drain(queue, results, 2)
    assert results == ["A", "B"]
    assert ctx.started == ["A", "B"]
    assert ctx.finished == ["A", "B"]


def test_dedup_drops_duplicate_key(queue, ctx):
    """Second submit with same key returns False and never runs."""
    results: list = []
    accepted1 = queue.submit(SleepCmd("X"), results.append)
    accepted2 = queue.submit(SleepCmd("X"), results.append)
    assert accepted1 is True
    assert accepted2 is False
    _drain(queue, results, 1)
    assert results == ["X"]
    assert ctx.started.count("X") == 1


def test_dedup_clears_after_completion(queue, ctx):
    """After a command finishes, the same key can be submitted again."""
    results: list = []
    queue.submit(SleepCmd("Y"), results.append)
    _drain(queue, results, 1)
    accepted = queue.submit(SleepCmd("Y"), results.append)
    assert accepted is True
    _drain(queue, results, 2)
    assert results == ["Y", "Y"]


def test_pending_op_count(queue, ctx):
    """submit() bumps; submit_scan() does not. Counter returns to 0 after drain."""
    results: list = []
    queue.submit(SleepCmd("A", delay=0.1), results.append)
    queue.submit(SleepCmd("B", delay=0.1), results.append)
    time.sleep(0.01)
    assert queue.pending_op_count() >= 1
    _drain(queue, results, 2)
    assert queue.pending_op_count() == 0


def test_scan_does_not_bump_pending(queue, ctx):
    """submit_scan keeps pending_op_count at 0 even while in-flight."""
    results: list = []
    queue.submit_scan(SleepCmd("scan", delay=0.05), results.append)
    time.sleep(0.01)
    assert queue.pending_op_count() == 0
    _drain(queue, results, 1)
    assert queue.pending_op_count() == 0


def test_exception_is_delivered_as_result(queue, ctx):
    """If run() raises, the callback gets the exception object, not a re-raise."""
    results: list = []
    queue.submit(BoomCmd(), results.append)
    _drain(queue, results, 1)
    assert len(results) == 1
    assert isinstance(results[0], RuntimeError)


def test_poll_main_thread_only(queue, ctx):
    """poll() asserts it's on the main thread."""
    err: list = []

    def call_poll():
        try:
            queue.poll()
        except AssertionError as e:
            err.append(e)

    t = threading.Thread(target=call_poll)
    t.start()
    t.join()
    assert len(err) == 1


def test_shutdown_joins_worker(ctx):
    """shutdown() returns promptly even with no work pending."""
    q = CommandQueue(ctx)
    q.shutdown()
    assert not q._worker.is_alive()

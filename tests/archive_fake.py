"""Test double for ArchiveJob — no thread, no subprocess, state driven by hand."""

from contextlib import contextmanager
from unittest.mock import patch

from modalapi.archive import JobState


class FakeArchiveJob:
    def __init__(self, argv: list[str], total_bytes: int = 458_633_729, state: JobState = JobState.RUNNING) -> None:
        self.argv = argv
        self.total_bytes = total_bytes
        self.done_bytes = 0
        self.current_entry = ""
        self.state = state
        self.error = ""
        self.cancelled = False

    def progress(self) -> float:
        return self.done_bytes / self.total_bytes

    def cancel(self) -> None:
        self.cancelled = True
        self.state = JobState.CANCELLED

    def advance(self, fraction: float, entry: str = "") -> None:
        self.done_bytes = int(self.total_bytes * fraction)
        if entry:
            self.current_entry = entry

    def finish(self, state: JobState = JobState.DONE, error: str = "") -> None:
        self.done_bytes = self.total_bytes
        self.state = state
        self.error = error


@contextmanager
def fake_jobs(state: JobState = JobState.RUNNING):
    """Patch both ArchiveJob factories. Yields the list of jobs handed out."""
    created: list[FakeArchiveJob] = []

    def make(*argv):
        job = FakeArchiveJob(list(argv), state=state)
        created.append(job)
        return job

    with (
        patch("modalapi.archive.ArchiveJob.backup", side_effect=make),
        patch("modalapi.archive.ArchiveJob.restore", side_effect=make),
    ):
        yield created

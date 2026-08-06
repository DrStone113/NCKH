"""Tests for ``ScopedSession`` — the per-statement DB session facade.

Regression context: every DB consumer in the chat stack shared one
``AsyncSession``. That session cannot serve overlapping awaits, and the chat
stack produces plenty of them (a task per incoming WebSocket message, the
background rolling-summary update, parallel tool dispatch). The first overlap
raised ``another operation is in progress`` and left the session permanently
broken, so ``_load_recent_turns`` returned nothing and the model — unable to
see its own earlier suggestions — invented dish names instead of calling
``suggest_dish``.

These tests use a fake session factory so they exercise the facade's contract
without needing a live Postgres.
"""

from __future__ import annotations

import asyncio

import pytest

from db.database import ScopedSession


class _FakeResult:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        self.rowcount = rowcount if rowcount is not None else len(rows)

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    """Records its own lifecycle and rejects concurrent use, like asyncpg."""

    def __init__(self, log, rows):
        self._log = log
        self._rows = rows
        self._busy = False
        self.committed = 0
        self.closed = False

    async def execute(self, statement, params=None):
        if self._busy:
            raise AssertionError("concurrent use of a single session")
        self._busy = True
        try:
            self._log.append(("execute", str(statement), params))
            await asyncio.sleep(0)  # yield so overlap would be observable
            return _FakeResult(self._rows)
        finally:
            self._busy = False

    async def commit(self):
        self.committed += 1

    async def close(self):
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
        return False


class _FakeFactory:
    def __init__(self, rows=()):
        self.log: list[tuple] = []
        self.created: list[_FakeSession] = []
        self._rows = list(rows)

    def __call__(self):
        session = _FakeSession(self.log, self._rows)
        self.created.append(session)
        return session


@pytest.mark.asyncio
async def test_each_execute_uses_a_fresh_session():
    factory = _FakeFactory()
    scoped = ScopedSession(session_factory=factory)

    await scoped.execute("SELECT 1")
    await scoped.execute("SELECT 2")

    assert len(factory.created) == 2
    assert all(s.closed for s in factory.created)


@pytest.mark.asyncio
async def test_concurrent_executes_do_not_share_a_session():
    """The whole point of the facade: overlapping callers must not collide."""
    factory = _FakeFactory()
    scoped = ScopedSession(session_factory=factory)

    await asyncio.gather(*[scoped.execute(f"SELECT {i}") for i in range(8)])

    # A shared session would have raised AssertionError inside _FakeSession.
    assert len(factory.created) == 8


@pytest.mark.asyncio
async def test_execute_commits_each_statement():
    factory = _FakeFactory()
    scoped = ScopedSession(session_factory=factory)

    await scoped.execute("INSERT INTO t VALUES (1)")

    assert factory.created[0].committed == 1


@pytest.mark.asyncio
async def test_params_are_forwarded_only_when_provided():
    factory = _FakeFactory()
    scoped = ScopedSession(session_factory=factory)

    await scoped.execute("SELECT :a", {"a": 1})
    await scoped.execute("SELECT 1")

    assert factory.log[0][2] == {"a": 1}
    assert factory.log[1][2] is None


@pytest.mark.asyncio
async def test_rows_survive_session_close():
    """Rows must be buffered: a closed session cannot stream a cursor."""
    factory = _FakeFactory(rows=[("a", 1), ("b", 2)])
    scoped = ScopedSession(session_factory=factory)

    result = await scoped.execute("SELECT name, n FROM t")

    assert factory.created[0].closed
    assert result.fetchall() == [("a", 1), ("b", 2)]
    assert result.all() == [("a", 1), ("b", 2)]
    assert result.first() == ("a", 1)
    assert result.scalar() == "a"
    assert list(result) == [("a", 1), ("b", 2)]


@pytest.mark.asyncio
async def test_empty_result_accessors_are_safe():
    factory = _FakeFactory(rows=[])
    scoped = ScopedSession(session_factory=factory)

    result = await scoped.execute("SELECT 1 WHERE false")

    assert result.all() == []
    assert result.first() is None
    assert result.fetchone() is None
    assert result.scalar() is None


@pytest.mark.asyncio
async def test_commit_and_rollback_are_noops():
    """Call sites still invoke them; per-statement commits make them redundant."""
    factory = _FakeFactory()
    scoped = ScopedSession(session_factory=factory)

    await scoped.commit()
    await scoped.rollback()
    await scoped.close()

    assert factory.created == []

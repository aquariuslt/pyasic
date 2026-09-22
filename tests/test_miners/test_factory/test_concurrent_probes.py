import asyncio

import pytest

from pyasic.miners.factory import _cancel_tasks, concurrent_get_first_result


async def _raise_probe_error():
    raise RuntimeError("probe exploded")


async def _answer_much_later():
    # long enough that it cannot finish before the failing probe, short enough
    # that a run which stops cancelling waits seconds rather than a minute
    await asyncio.sleep(5)


def test_cancelling_a_task_that_already_failed_keeps_its_exception():
    async def run():
        task = asyncio.create_task(_raise_probe_error())
        await asyncio.sleep(0)  # let it finish with its exception

        await _cancel_tasks([task])

        return task

    task = asyncio.run(run())

    assert isinstance(task.exception(), RuntimeError)


def test_a_probe_that_raises_cancels_the_probes_still_waiting():
    async def run():
        # the failing probe finishes at once, so it is the first answer the
        # loop sees; the other one is still waiting when it does
        failing = asyncio.create_task(_raise_probe_error())
        pending = asyncio.create_task(_answer_much_later())
        with pytest.raises(RuntimeError):
            await concurrent_get_first_result(
                [failing, pending], lambda answer: answer is not None
            )
        return pending

    pending = asyncio.run(run())

    assert pending.cancelled()

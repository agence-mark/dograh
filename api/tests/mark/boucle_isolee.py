"""[.mark] Run a coroutine from a synchronous test without touching global state.

🔴 Why this exists: the first CI run on our branches (2026-09-16) stopped on an
UPSTREAM test, ``tests/test_add_call_disposition_code.py``, with
``RuntimeError: There is no current event loop in thread 'MainThread'``.

The test passes on its own. It failed because two of OUR tests ran before it
and called ``asyncio.run()``. On exit, ``asyncio.run()`` calls
``set_event_loop(None)``, so it leaves the main thread with no current loop;
the upstream test then calls ``asyncio.get_event_loop()``, which raises under
Python 3.13 when no loop is set.

⛔ The defect was already in production (both calls date from 08/09 and 10/09).
Nobody saw it because the CI had never run on this fork.

The fault is shared -- their test leans on a deprecated implicit loop, ours
reset a process-wide setting -- but the fix belongs on OUR side: it is our test
that changes something it does not own, and patching their file would cost a
conflict at every upstream merge.

``test_aucun_asyncio_run_dans_nos_tests`` keeps it from coming back.
"""

import asyncio


def executer_sans_toucher_la_boucle_courante(coroutine):
    """Run ``coroutine`` to completion on a private loop, then close it.

    ⛔ Unlike ``asyncio.run()``, this never calls ``set_event_loop``: whatever
    loop the thread had before (or the absence of one) is exactly what it has
    after. That is the whole point.
    """
    boucle = asyncio.new_event_loop()
    try:
        return boucle.run_until_complete(coroutine)
    finally:
        boucle.run_until_complete(boucle.shutdown_asyncgens())
        boucle.close()

"""[.mark] Run a coroutine from a synchronous test without touching global state.

``asyncio.run()`` calls ``set_event_loop(None)`` on exit: it changes a
process-wide setting that every later test inherits. This helper runs the
coroutine on a private loop and never calls ``set_event_loop``, so the thread
leaves exactly as it came.

🔑 Context, and it is worth getting right (2026-09-16). The first CI runs on our
branches stopped on an upstream test, ``tests/test_add_call_disposition_code.py``,
with "There is no current event loop". Our ``asyncio.run()`` calls were first
taken for THE cause; bisecting and instrumenting in the exact CI conditions
showed they were only ONE trigger among several (pytest-asyncio removes the
loop too). ⛔ The root cause was that upstream test calling
``asyncio.get_event_loop()`` from synchronous code, which depends on whatever
state earlier tests leave behind. It was fixed there, in one line.

This helper stays because not altering process-wide state is right on its own.
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

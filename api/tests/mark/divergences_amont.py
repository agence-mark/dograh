"""[.mark] The upstream tests we make fail ON PURPOSE, and why.

A fork that diverges from upstream has two honest options for the tests that
encode the behaviour it changed: delete them, or declare them. ⛔ Deleting is
the bad one -- it is silent, it hides the divergence from whoever merges the
next upstream release, and it removes the only place where the reason is
written down.

So they are declared here, and ``conftest.py`` marks them ``xfail``.

🔑 **``strict=True`` is the point of this file.** A declared divergence that
starts PASSING again is reported as a failure (``XPASS``), not quietly ignored.
That happens the day upstream changes its mind, or the day one of our patches
is lost in a merge -- and both are things we want to be told about, loudly.
It is the same invariant in both directions: the test must fail for the reason
we wrote, and it must stop failing the moment that reason disappears.

⛔ **Do not add a test here to make CI green.** The only thing that belongs in
this file is a behaviour Evan decided, written down elsewhere as a decision.
Anything else is a bug being papered over, and the next reader has no way to
tell the two apart.
"""

# Keyed by the test FILE (relative to ``api/``), then by the test FUNCTION name.
# ⛔ Deliberately not keyed by full parametrised id: those ids carry the values
# under test, so they churn on every upstream edit. Both functions below fail
# on ALL of their parameter sets -- checked, 2026-09-16 -- so the function name
# is exact here and does not swallow a passing case by accident.
DIVERGENCES_ASSUMEES = {
    "tests/test_deepgram_endpoint_service_factory.py": {
        "test_unset_endpoint_falls_back_to_the_default_host": (
            "[.mark] Decision d'Evan du 16/09/2026 : une adresse Deepgram VIDE "
            "replie sur l'Europe, la ou l'amont replie sur son endpoint "
            "mondial. Sans ce repli, une configuration enregistree avant "
            "l'ouverture du champ enverrait l'audio de l'appelant aux "
            "Etats-Unis en silence. Voir Labo-agent-vocal/reference/17-decisions.md"
        ),
        "test_endpoint_is_offered_in_the_configuration_schema": (
            "[.mark] Decision d'Evan du 16/09/2026 : le champ d'adresse est "
            "bien offert et librement saisissable comme chez l'amont, mais son "
            "DEFAUT est l'endpoint europeen et non l'endpoint mondial. Les "
            "trois autres assertions de ce test (menu des regions, saisie "
            "libre) sont, elles, satisfaites."
        ),
    },
}

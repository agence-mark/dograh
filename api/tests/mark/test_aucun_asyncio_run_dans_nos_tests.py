"""[.mark] None of OUR tests may call ``asyncio.run()``.

🔴 Born from the first CI run on our branches, 2026-09-16: two of our tests
called ``asyncio.run()``, which leaves the main thread with no current event
loop on exit, and an upstream test run after them
(``tests/test_add_call_disposition_code.py``) then failed on
``asyncio.get_event_loop()``. The defect had been in production since 08/09 and
nobody saw it, because the CI had never run on this fork.

⛔ Why a test and not a rule written somewhere: the failure is an ORDER effect.
The offending test passes, the victim passes on its own, and only the full
suite run in collection order shows anything. Nobody would catch the next one
by reading a diff.

⛔ The call is looked up in the syntax tree, not by text search: this very
file, and ``boucle_isolee.py``, NAME ``asyncio.run()`` in prose, and a text
search would either fail on them or be tempted into an exception list.

Scope: ``tests/mark/`` only, which is ours. Upstream tests are theirs to fix.
"""

import ast
from pathlib import Path

NOS_TESTS = Path(__file__).resolve().parent


def _appels_a_asyncio_run(chemin: Path) -> list[int]:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    lignes = []
    for noeud in ast.walk(arbre):
        if (
            isinstance(noeud, ast.Call)
            and isinstance(noeud.func, ast.Attribute)
            and noeud.func.attr == "run"
            and isinstance(noeud.func.value, ast.Name)
            and noeud.func.value.id == "asyncio"
        ):
            lignes.append(noeud.lineno)
    return lignes


def test_aucun_asyncio_run_dans_nos_tests():
    fautifs = {
        chemin.name: lignes
        for chemin in sorted(NOS_TESTS.glob("*.py"))
        if (lignes := _appels_a_asyncio_run(chemin))
    }

    assert not fautifs, (
        "asyncio.run() laisse le thread principal sans boucle et fait tomber un "
        "test d'amont lance apres. Utiliser "
        "tests.mark.boucle_isolee.executer_sans_toucher_la_boucle_courante. "
        f"Trouve dans : {fautifs}"
    )


def test_le_garde_voit_bien_un_appel():
    """⛔ Un garde qui ne rougit jamais ne garde rien : on le prouve rouge."""
    import tempfile

    with tempfile.TemporaryDirectory() as dossier:
        faux = Path(dossier) / "faux.py"
        faux.write_text(
            "import asyncio\n\nasync def f():\n    pass\n\nasyncio.run(f())\n",
            encoding="utf-8",
        )
        assert _appels_a_asyncio_run(faux) == [6]

        mention = Path(dossier) / "mention.py"
        mention.write_text(
            '"""On ne doit pas appeler asyncio.run() ici."""\n', encoding="utf-8"
        )
        assert _appels_a_asyncio_run(mention) == []

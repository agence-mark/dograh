"""[.mark] Revue serveur, mineur 10 : le versement au démarrage ne s'éternise pas et ne se joue pas en parallèle.

| Test | Ce qu'il prouve |
|---|---|
| un seul à la fois | tant qu'une connexion tient le verrou du versement, une autre réplique ne le prend pas ; libéré, elle le prend |
| délai du script | le script de démarrage borne le versement par ``timeout`` |
| passer son tour | une réplique sans le verrou ne verse rien et sort sans erreur |
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy import text

from api.db import db_client
from api.scripts.mark import verser as script

RACINE = Path(__file__).resolve().parents[3]


async def test_une_seule_replique_verse_a_la_fois(test_engine):
    async with script.sous_verrou(test_engine) as premiere:
        assert premiere is True
        async with script.sous_verrou(test_engine) as seconde:
            assert seconde is False  # une autre connexion tient le verrou
    async with script.sous_verrou(test_engine) as apres:
        assert apres is True  # libéré à la sortie


async def test_une_replique_sans_verrou_passe_son_tour(test_engine):
    async with test_engine.connect() as autre:
        await autre.execute(text("SELECT pg_advisory_lock(:k)"), {"k": script.CLE_DU_VERROU})
        try:
            with patch.object(db_client, "engine", test_engine), patch.object(script, "_verser", AsyncMock(return_value=0)) as verse:
                assert await script._principal() == 0
            verse.assert_not_called()
        finally:
            await autre.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": script.CLE_DU_VERROU})


def test_le_script_de_demarrage_borne_le_versement_par_un_delai():
    sh = (RACINE / "scripts" / "start_services_docker.sh").read_text(encoding="utf-8")
    assert 'timeout "${VERSEMENT_DELAI_S:-300}" python -m api.scripts.mark.verser' in sh

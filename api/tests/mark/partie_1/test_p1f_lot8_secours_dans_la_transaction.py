"""[.mark] Plan final Partie 1, lot 8b-2 (audit 8b-1b, mineur 2) : l'échelle de secours est appelée dans la transaction de la marque du filet (``rattrapage._une_retenue``). Une erreur SQL du
ticket, attrapée en Python, laissait la transaction en échec : la marque défaite, l'alerte redite au restaurant à chaque passage (chaque minute). Le ticket s'écrit dans son propre point
de reprise : son échec est dit au bilan (« echec »), la marque et le reste de la transaction tiennent.

| Test | Ce qu'il prouve |
|---|---|
| ticket en erreur SQL | le bilan dit « echec », la transaction continue, ce qui était écrit avant (la marque) est gardé à la fin |
"""

from __future__ import annotations

import uuid

from api.db.bases_clients import restauration_liaison as liaison_db
from api.services.restauration.envois_et_sms.secours import secours_de_la_commande


async def test_une_erreur_sql_du_ticket_ne_defait_pas_la_marque(faire_monde, monkeypatch):
    """Client (commande retenue, son appel jamais fini) / le filet marque la ligne puis alerte : l'insertion du ticket échoue / avant : la marque est défaite avec la transaction et
    le restaurant reçoit le même message chaque minute / après : le ticket est « echec » au bilan, la marque reste, l'alerte part une fois."""
    monde = await faire_monde("casa-italia")
    c = monde.c

    async def une_imprimante(*_a, **_k):
        return {"id": 1}

    async def ticket_en_erreur_sql(connexion, *_a, **_k):
        await connexion.execute("SELECT 1/0")  # une erreur du serveur, comme une contrainte ou une table absente

    monkeypatch.setattr(liaison_db, "imprimante", une_imprimante)
    monkeypatch.setattr(liaison_db, "creer_le_ticket", ticket_en_erreur_sql)
    await c.execute("CREATE TEMP TABLE marque_du_filet (numero text)")
    async with c.transaction():
        await c.execute("INSERT INTO marque_du_filet VALUES ('posee')")
        bilan = await secours_de_la_commande(c, None, monde.a, {"numero": str(uuid.uuid4()), "numero_court": "T1", "lignes": []}, "appel jamais terminé")
        assert bilan["ticket"] == "echec", bilan
        assert await c.fetchval("SELECT count(*) FROM marque_du_filet") == 1  # la transaction n'est pas en échec : elle répond encore
    assert await c.fetchval("SELECT count(*) FROM marque_du_filet") == 1, "la marque est gardée à la fin"

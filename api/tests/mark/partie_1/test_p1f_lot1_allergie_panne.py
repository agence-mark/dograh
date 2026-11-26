"""[.mark] Plan final Partie 1, lot 1 (n° 71 et 155) : la panne d'un fait d'allergie se voit, et l'enregistrement reste bloqué.

Avant : ``poser_les_faits_de_l_allergie`` finissait en ``except Exception: pass`` : la personne n'entendait rien de son allergie et personne ne le savait.
Règle : une panne part au journal d'erreur ; l'allergie reste « à donner » (le préalable bloquant tient l'enregistrement) ; rien ne lève.
"""

from __future__ import annotations

from loguru import logger

from api.services.actions_communes import du as DU
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as ALLERGIE

PANIER = {"lignes": [{"n": 1, "nom": "Regina", "quantite": 1}], "conversation": {"tour_de_l_appel": 2}, "notes_du_greffier": {"allergie": "noix"}}


def _un_panier():
    p = {**PANIER, "lignes": [dict(l) for l in PANIER["lignes"]]}
    p[ALLERGIE.CLE_NOTES_DU_GREFFIER] = {"allergie": "noix"}
    return p


def _pile_au_journal(record) -> bool:
    """La pile est au journal : dans ``record["exception"]``, ou collée au message après sa première ligne quand le filtre de la production
    (``enrich_log_record``, posé à l'import de ``api.app`` hors test) l'y a mise, numéros masqués."""
    return record["exception"] is not None or "Traceback" in "\n".join(record["message"].splitlines()[1:])


async def test_la_panne_d_un_fait_d_allergie_part_au_journal_et_l_allergie_reste_a_donner(monkeypatch):
    async def en_panne(source, p, *a):
        raise RuntimeError("la carte ne répond pas")

    monkeypatch.setattr(ALLERGIE, "faits_de_l_allergie", en_panne)
    messages = []
    sortie = logger.add(lambda m: messages.append(m.record), level="ERROR")
    try:
        p, retour = _un_panier(), {"statut": "FAIT", "faits": {}}
        await ALLERGIE.poser_les_faits_de_l_allergie(None, None, p, None, retour)
    finally:
        logger.remove(sortie)
    assert messages and "allergie" in messages[0]["message"], messages
    assert _pile_au_journal(messages[0]), "la pile de la panne doit être au journal"
    assert ALLERGIE.allergie_a_donner(p) == "noix", "l'allergie reste à donner : le préalable bloquant tient l'enregistrement"
    assert "allergie" not in (retour.get("faits") or {}) and DU.CLE_FAITS_A_DIRE not in retour


async def test_sans_panne_rien_ne_part_au_journal_d_erreur(monkeypatch):
    async def faits(source, p, *a):
        return {"allergie": "noix", "articles": [{"article": "Regina", "etat": "inconnu"}]}

    monkeypatch.setattr(ALLERGIE, "faits_de_l_allergie", faits)
    messages = []
    sortie = logger.add(lambda m: messages.append(m.record), level="ERROR")
    try:
        retour = {"statut": "FAIT", "faits": {}}
        await ALLERGIE.poser_les_faits_de_l_allergie(None, None, _un_panier(), None, retour)
    finally:
        logger.remove(sortie)
    assert not messages and retour["faits"]["allergie"]

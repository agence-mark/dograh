"""[.mark] Plan final Partie 1, lot 10 (A5) : le numéro court et la recherche d'une commande suivent le JOUR DE SERVICE, pas minuit.

Scénario (kebab ouvert jusqu'à 2 h) : une commande à 23 h 50 est « C1 » ; à 0 h 15 la suivante est « C2 » (et non un second « C1 » : deux commandes du même numéro dans la
même soirée) ; à 0 h 20, « ma commande 1 » et « ma commande de ce soir au numéro de téléphone » sont retrouvées ; à 6 h 30 un nouveau jour de service commence, le compteur
repart à 1 et la recherche ne ramène plus les commandes d'hier soir. Le jour de service court de 06 h à 06 h (le ``cutoff_time`` de la caisse quand elle le dit).
"""

from __future__ import annotations

from datetime import datetime

from api.db.bases_clients import horloge
from api.db.bases_clients.restauration_commande import statut_commande
from api.tests.mark import test_restauration_classeur_commande as _classeur
from api.tests.mark.test_restauration_classeur_commande import PARIS, TEL, brouillon, enregistrer

commerce = _classeur.commerce


def _a(jour: int, heure: int, minute: int) -> datetime:
    return datetime(2026, 11, jour, heure, minute, tzinfo=PARIS)


async def _ouvrir_la_nuit(commerce) -> None:
    """Le restaurant prend les commandes jeudi jusqu'à 23 h 59 et vendredi dès minuit jusqu'à 7 h (la nuit du kebab) : la fermeture n'est pas le sujet ici."""
    for jour, ouverture, fermeture in ((4, "23:00", "23:59:59"), (5, "00:00", "07:00")):
        await commerce.c.execute("INSERT INTO mark.horaire (site_id, jour, ouverture, fermeture) VALUES ($1, $2, $3::text::time, $4::text::time)", commerce.a, jour, ouverture, fermeture)


async def _commande(commerce, quand: datetime, appel: str) -> str:
    with horloge.remplacer(commerce.base, quand):
        r = await enregistrer(commerce, brouillon(appel_id=appel), jeton=f"relu-{appel}")
    assert r.statut == "ENREGISTREE", r
    return r.faits["numero_court"]


async def test_le_compteur_ne_repart_pas_a_minuit_et_repart_au_debut_du_jour_de_service(commerce):
    await _ouvrir_la_nuit(commerce)
    assert await _commande(commerce, _a(12, 23, 50), "soir") == "C1"
    assert await _commande(commerce, _a(13, 0, 15), "minuit") == "C2"  # avant : « C1 » une seconde fois
    assert await _commande(commerce, _a(13, 6, 30), "matin") == "C1"  # un nouveau jour de service


async def test_ma_commande_est_retrouvee_apres_minuit_par_son_numero_et_par_son_telephone(commerce):
    await _ouvrir_la_nuit(commerce)
    await _commande(commerce, _a(12, 23, 50), "soir")
    await _commande(commerce, _a(13, 0, 15), "minuit")
    with horloge.remplacer(commerce.base, _a(13, 0, 20)):
        par_numero = await statut_commande(commerce.c, commerce.a, numero="C1")
        par_telephone = await statut_commande(commerce.c, commerce.a, telephone=TEL)
    assert par_numero.statut == "OK" and [c["numero_court"] for c in par_numero.faits["commandes"]] == ["C1"]  # ma commande de 23 h 50
    assert sorted(c["numero_court"] for c in par_telephone.faits["commandes"]) == ["C1", "C2"]


async def test_le_matin_la_recherche_ne_ramene_plus_les_commandes_de_la_veille_au_soir(commerce):
    await _ouvrir_la_nuit(commerce)
    await _commande(commerce, _a(12, 23, 50), "soir")
    await _commande(commerce, _a(13, 6, 30), "matin")
    with horloge.remplacer(commerce.base, _a(13, 7, 0)):
        r = await statut_commande(commerce.c, commerce.a, numero="C1")
        t = await statut_commande(commerce.c, commerce.a, telephone=TEL)
    assert len(r.faits["commandes"]) == 1 and len(t.faits["commandes"]) == 1  # celle du matin seule : le jour de service d'hier est fini

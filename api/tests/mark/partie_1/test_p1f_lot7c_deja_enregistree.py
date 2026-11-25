"""[.mark] Lot 7b-C0, P0 : « Votre commande est déjà enregistrée » : UNE place, lue par les deux chemins qui la rendent.

* La fin de la commande (``enregistrement.mener_a_la_fin``) : le panier porte déjà sa commande enregistrée.
* L'anti-doublon de la source (``enregistrer_commande``) : la même commande rejouée rend la première, avec l'heure annoncée (le fait ``quand_dit``).

C6 n° 5 (décision d'Evan 25/11 9 h 30) : ce n'est plus une phrase du code ; c'est un texte de secours (``textes_de_secours.deja_enregistree``) qui ne lit que les faits, jamais dit
à la place du modèle. Le texte est celui d'avant, au caractère près.
"""

from __future__ import annotations

from api.services.commande import panier as P
from api.services.commande import textes_de_secours as TS
from api.services.commande.moteur import enregistrement
from api.services.commande.moteur.socle import Appelant, Reglages
from api.tests.mark import test_restauration_classeur_commande as _classeur
from api.tests.mark.test_restauration_classeur_commande import brouillon, enregistrer

commerce = _classeur.commerce


def test_le_texte_de_secours_lit_les_faits_et_garde_le_texte_d_avant():
    assert TS.deja_enregistree({}) == "Votre commande est déjà enregistrée."
    assert TS.deja_enregistree({"quand_dit": "dix-neuf heures trente"}) == "Votre commande est déjà enregistrée pour dix-neuf heures trente."


async def test_la_fin_de_la_commande_rend_le_texte_de_secours():
    p = {**P.nouveau(), "mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}], "enregistree": {"numero": "A1", "total": 1200}}
    r = await enregistrement._finaliser(None, p, Reglages(), Appelant(None, None))
    assert r.statut == "DEJA_FAIT" and r.suggestion == TS.deja_enregistree({}) == "Votre commande est déjà enregistrée."


async def test_l_anti_doublon_de_la_source_rend_le_fait_et_son_heure(commerce):
    premiere = await enregistrer(commerce, brouillon(appel_id="appel-p0"), jeton="relu-p0")
    seconde = await enregistrer(commerce, brouillon(appel_id="appel-p0"), jeton="relu-p0")
    assert seconde.statut == "DEJA_FAIT" and seconde.faits["numero"] == premiere.faits["numero"], (premiere, seconde)
    assert seconde.faits["quand_dit"] and seconde.suggestion == TS.deja_enregistree(seconde.faits), seconde

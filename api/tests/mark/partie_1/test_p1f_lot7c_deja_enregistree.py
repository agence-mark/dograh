"""[.mark] Lot 7b-C0, P0 : « déjà enregistrée » : UN fait, rendu par les deux chemins qui le rendent.

* La fin de la commande (``enregistrement.mener_a_la_fin``) : le panier porte déjà sa commande enregistrée.
* L'anti-doublon de la source (``enregistrer_commande``) : la même commande rejouée rend la première, avec l'heure annoncée (le fait ``quand_dit``).

C6 n° 5 (décision d'Evan 25/11 9 h 30) : ce n'est plus une phrase du code ; lot 7b-C7 B9 : plus de texte de secours non plus (Evan 25/11 8 h 45 : le code ne compose aucune phrase).
Le modèle le dit d'après le statut ``DEJA_FAIT`` et ses faits (« pas juste une suppression », Evan 25/11 10 h : le texte d'avant ne disait que ce statut et l'heure ``quand_dit``).
"""

from __future__ import annotations

from api.services.commande import panier as P
from api.services.commande.moteur import enregistrement
from api.services.commande.moteur.socle import Appelant, Reglages
from api.tests.mark import test_restauration_classeur_commande as _classeur
from api.tests.mark.test_restauration_classeur_commande import brouillon, enregistrer

commerce = _classeur.commerce


async def test_la_fin_de_la_commande_rend_le_fait_sans_phrase():
    p = {**P.nouveau(), "mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}], "enregistree": {"numero": "A1", "total": 1200}}
    r = await enregistrement._finaliser(None, p, Reglages(), Appelant(None, None))
    assert r.statut == "DEJA_FAIT" and r.suggestion == "" and r.faits["numero"] == "A1", r


async def test_l_anti_doublon_de_la_source_rend_le_fait_et_son_heure(commerce):
    premiere = await enregistrer(commerce, brouillon(appel_id="appel-p0"), jeton="relu-p0")
    seconde = await enregistrer(commerce, brouillon(appel_id="appel-p0"), jeton="relu-p0")
    assert seconde.statut == "DEJA_FAIT" and seconde.faits["numero"] == premiere.faits["numero"], (premiere, seconde)
    assert seconde.faits["quand_dit"] and seconde.suggestion == "", seconde

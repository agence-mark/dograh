"""[.mark] Lot 7b-C0, P0 : « Votre commande est déjà enregistrée » est un fait accompli qui engage (plan § 2) : UNE place, ``phrases_dites_par_le_code``, lue par les deux chemins qui la disent.

* La fin de la commande (``enregistrement.mener_a_la_fin``) : le panier porte déjà sa commande enregistrée.
* L'anti-doublon de la source (``enregistrer_commande``) : la même commande rejouée rend la première, avec l'heure annoncée.

Rien ne change à l'oreille : les deux chemins disent exactement le texte d'avant.
"""

from __future__ import annotations

from api.services.commande import panier as P
from api.services.commande import phrases_dites_par_le_code as PD
from api.services.commande.moteur import enregistrement
from api.services.commande.moteur.socle import Appelant, Reglages
from api.tests.mark import test_restauration_classeur_commande as _classeur
from api.tests.mark.test_restauration_classeur_commande import brouillon, enregistrer

commerce = _classeur.commerce


def test_la_phrase_est_au_registre_comme_fait_accompli_et_dite_comme_avant():
    assert PD.PHRASES["deja_enregistree"].exception == PD.PHRASES["deja_enregistree_pour"].exception == PD.EXCEPTION_FAIT_ACCOMPLI
    assert PD.deja_enregistree(None) == "Votre commande est déjà enregistrée."
    assert PD.deja_enregistree("dix-neuf heures trente") == "Votre commande est déjà enregistrée pour dix-neuf heures trente."


async def test_la_fin_de_la_commande_dit_la_phrase_du_registre():
    p = {**P.nouveau(), "mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}], "enregistree": {"numero": "A1", "total": 1200}}
    r = await enregistrement._finaliser(None, p, Reglages(), Appelant(None, None))
    assert r.statut == "DEJA_FAIT" and r.suggestion == PD.deja_enregistree(None) == "Votre commande est déjà enregistrée."


async def test_l_anti_doublon_de_la_source_dit_la_phrase_du_registre_avec_l_heure(commerce):
    premiere = await enregistrer(commerce, brouillon(appel_id="appel-p0"), jeton="relu-p0")
    seconde = await enregistrer(commerce, brouillon(appel_id="appel-p0"), jeton="relu-p0")
    assert seconde.statut == "DEJA_FAIT" and seconde.faits["numero"] == premiere.faits["numero"], (premiere, seconde)
    quand = seconde.suggestion.removeprefix("Votre commande est déjà enregistrée pour ").removesuffix(".")
    assert seconde.suggestion == PD.deja_enregistree(quand) and quand != seconde.suggestion, seconde.suggestion

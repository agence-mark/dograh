"""[.mark] Lot 7b-C2, la zone, le mode et le créneau voulu (``restauration_commande``) : chaque refus fermé ne porte plus de texte (lot 7b-C7, A3) ; C7 B9 : le catalogue supprimé, ce que disait
le texte d'avant est vérifié dans ses faits. Un fait qui distingue deux refus de même statut et même manque est une valeur simple (``plus_tard_refuse``, ``jusqu_a``, ``trop_tot``)."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

from api.db.bases_clients import horloge
from api.db.bases_clients import restauration_commande as RC
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark import test_base_client as BASE
from api.tests.mark import test_restauration_classeur_commande as CLASSEUR

# Les fixtures du classeur, reprises par affectation (jamais d'import qui ne sert qu'à les enregistrer).
base_essai, base_prete, commerce = BASE.base_essai, BASE.base_prete, CLASSEUR.commerce

PARIS = ZoneInfo("Europe/Paris")


def _verifie(r, statut: str, faits: dict, manque: str | None = None):
    """C7 (A3) : le refus ne porte plus de texte ; B9 : ce que disait le texte d'avant est dans ses faits (ceux qu'il lisait, ou tous quand il était fixe)."""
    assert (r.statut, r.suggestion, r.manque) == (statut, "", manque), r
    assert ({k: r.faits.get(k) for k in faits} if faits else r.faits) == faits, r  # {} : le refus ne porte aucun fait


async def _creneau(commerce, voulue, moment=JEUDI_MIDI, mode="emporter"):
    return await RC.creneau_refuse(commerce.c, commerce.a, mode, voulue, moment, PARIS)


async def _regler(commerce, **colonnes):
    for colonne, valeur in colonnes.items():
        await commerce.c.execute(f"UPDATE mark.resto_reglage_type SET {colonne} = $2 WHERE site_id = $1 AND type = 'emporter'", commerce.a, valeur)


# --- la zone et le minimum --------------------------------------------------------------------------------------------------------------------------


async def test_hors_zone(commerce):
    _, _, r = await RC._zone_de_livraison(commerce.c, commerce.a, 999999, 3000)
    _verifie(r, "HORS_ZONE", {'commune': None})
    assert r.faits == {}


async def test_minimum_non_atteint(commerce):
    _, _, r = await RC._zone_de_livraison(commerce.c, commerce.a, commerce.zones["Proches"], 200)
    _verifie(r, "MINIMUM_NON_ATTEINT", {'minimum': 1500})
    assert r.faits == {"minimum": 1500, "sous_total": 200, "minimum_dit": "quinze euros"}  # F3 (C7 B6) : le montant en lettres, la copie du modèle retire les centimes


# --- le mode ----------------------------------------------------------------------------------------------------------------------------------------


async def test_mode_non_compris_au_chiffrage(commerce):
    r = await RC.chiffrer_panier(commerce.c, commerce.a, "pigeon", [])
    _verifie(r, "ARGUMENT_INVALIDE", {}, "mode")


def test_mode_non_compris_a_la_demande():
    r = RC._manques_de_la_demande({"mode": "pigeon", "lignes": [{}]}, None, JEUDI_MIDI)
    _verifie(r, "ARGUMENT_INVALIDE", {}, "mode")


# --- l'heure voulue ---------------------------------------------------------------------------------------------------------------------------------


async def test_pas_de_commande_pour_plus_tard(commerce):
    r = await _creneau(commerce, JEUDI_MIDI + timedelta(hours=1))
    _verifie(r, "ARGUMENT_INVALIDE", {'plus_tard_refuse': True}, "heure_voulue")
    assert r.faits == {"plus_tard_refuse": True}


async def test_commandes_jusqu_a(commerce):
    await _regler(commerce, planifiee_permise=True, jours_a_l_avance=1)
    r = await _creneau(commerce, JEUDI_MIDI + timedelta(days=3))
    _verifie(r, "ARGUMENT_INVALIDE", {'jusqu_a': 'vendredi treize novembre'}, "heure_voulue")
    assert r.faits == {"jusqu_a": "vendredi treize novembre"}


async def test_trop_tot(commerce):
    await _regler(commerce, planifiee_permise=True, delai_minimal=60)
    r = await _creneau(commerce, JEUDI_MIDI + timedelta(minutes=30))
    _verifie(r, "ARGUMENT_INVALIDE", {'trop_tot': True, 'delai_minimal': 60, 'heure_demandee_dite': 'douze heures trente'}, "heure_voulue")
    assert r.faits == {"trop_tot": True, "delai_minimal": 60, "heure_demandee_dite": "douze heures trente"}


async def test_l_heure_demandee_entre_dans_l_identite_d_un_refus_d_heure(commerce):
    """7b-C4 (correctif A) : « 18 h », « 18 h 30 » puis « 19 h » trop tôt sont trois refus, pas un refus redit (ni issue ni sortie) ; la même heure trois fois reste le même refus
    (le trou 1 de C0). ``plus_tard_refuse`` n'a pas l'heure : toute autre heure du même genre échoue pareil."""
    from api.services.actions_communes import journal_du_dit as J

    await _regler(commerce, planifiee_permise=True, delai_minimal=60)
    heures = [JEUDI_MIDI + timedelta(minutes=m) for m in (15, 30, 45)]
    trois = [J.identite_du_refus(await _creneau(commerce, h)) for h in heures]
    assert len(set(trois)) == 3, trois
    memes = [J.identite_du_refus(await _creneau(commerce, heures[0])) for _ in range(3)]
    assert len(set(memes)) == 1, memes
    await _regler(commerce, planifiee_permise=False)
    refus_plus_tard = {J.identite_du_refus(await _creneau(commerce, JEUDI_MIDI + timedelta(hours=h))) for h in (1, 2, 3)}
    assert len(refus_plus_tard) == 1, refus_plus_tard


async def test_ferme_a_l_heure_voulue_dit_quand_on_rouvre(commerce):
    await _regler(commerce, planifiee_permise=True)
    r = await _creneau(commerce, JEUDI_MIDI + timedelta(hours=4))  # 16 h : entre le midi et le soir
    assert (r.statut, r.manque) == ("FERME", "heure_voulue")
    assert r.suggestion == ""
    assert r.faits["rouvre_dit"] == "dix-huit heures"


async def test_ferme_maintenant_ne_dit_pas_quand(commerce):
    with horloge.remplacer(commerce.base, JEUDI_MIDI.replace(hour=16)):
        r = await _creneau(commerce, None, JEUDI_MIDI.replace(hour=16))
    _verifie(r, "FERME", {'rouvre_dit': None})
    assert "rouvre_dit" not in r.faits


async def test_creneau_complet(commerce, monkeypatch):
    await _regler(commerce, planifiee_permise=True)

    async def libre(*_):
        return JEUDI_MIDI + timedelta(minutes=30)

    monkeypatch.setattr(RC, "creneau_complet", libre)
    r = await _creneau(commerce, JEUDI_MIDI + timedelta(minutes=15))
    _verifie(r, "ARGUMENT_INVALIDE", {'proposition_dite': 'douze heures trente'}, "heure_voulue")
    assert r.faits["raison"] == "creneau_plein" and r.faits["proposition"] == JEUDI_MIDI + timedelta(minutes=30)

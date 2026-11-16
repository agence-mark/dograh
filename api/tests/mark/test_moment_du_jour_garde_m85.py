"""[.mark] M85 (appels 2570 et 2572) : le moment de la journée déjà dit (« demain soir ») n'est jamais oublié.

« Demain soir », puis « huit heures et demie » : le code lit 20 h 30, sans demander « huit heures trente ou vingt heures trente ». Le moment est gardé
dans l'état de l'appel du geste (panier de la commande, état de la réservation) ; un moment contraire dit l'emporte ; sans moment gardé, le doute reste
une question. Sources simulées qui résolvent comme la vraie (``resoudre_la_date``) : aucune base.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest

from api.db.bases_clients import dates_futures as df
from api.services.commande import moteur as commande
from api.services.commande import panier as P
from api.services.commande.resultat import Resultat
from api.services.reservation import moteur as reservation

PARIS = timezone(timedelta(hours=1))
LUNDI_16 = datetime(2026, 11, 16, 12, 0, tzinfo=PARIS)


class Calendrier:
    """Résout comme ``resoudre_la_date`` : le jour, puis l'heure ; la même suite de statuts."""

    def __init__(self):
        self.heures_recues: list[str | None] = []

    async def resoudre_une_date(self, texte, heure):
        self.heures_recues.append(heure)
        jour = df.resoudre_une_date(texte, LUNDI_16)
        if jour.statut != df.RETENU:
            return Resultat("AMBIGU" if jour.statut == df.AMBIGU else "INTROUVABLE", {}, "Pour quel jour ?", "jour")
        faits = {"jour": jour.jour.isoformat(), "jour_dit": df.jour_dit(jour.jour)}
        if not heure:
            return Resultat("INCOMPLETE", faits, "À quelle heure ?", "heure")
        h = df.resoudre_l_heure(heure)
        if h.statut == df.AMBIGU:
            dites = [df.heure_dite(c) for c in h.candidats]
            return Resultat("AMBIGU", faits, f"{' ou '.join(dites)} ?", "heure")
        if h.statut != df.RETENU:
            return Resultat("INCOMPLETE", faits, "À quelle heure exactement ?", "heure")
        voulue = datetime.combine(jour.jour, h.heure, tzinfo=PARIS)
        return Resultat("RETENU", {**faits, "heure_voulue": voulue.isoformat(), "heure_dite": df.heure_dite(h.heure)}, "")


def _heure(r: Resultat) -> time:
    return datetime.fromisoformat(r.faits["heure_voulue"]).time()


# ---- le mécanisme pur


@pytest.mark.parametrize(
    "texte,moment", [("demain soir", "soir"), ("ce soir", "soir"), ("vendredi matin", "matin"), ("samedi midi", "midi"), ("dimanche après-midi", "apres-midi"), ("demain", None)]
)
def test_le_moment_dit_est_reconnu(texte, moment):
    assert df.moment_du_jour(texte) == moment


@pytest.mark.parametrize(
    "moment,heure,attendu",
    [("soir", "huit heures et demie", "huit heures et demie du soir"), ("matin", "huit heures", "huit heures du matin"),
     ("soir", "huit heures du matin", "huit heures du matin"),  # le moment contraire dit l'emporte
     (None, "huit heures", "huit heures"), ("soir", "bientôt", "bientôt"), ("midi", "trois heures", "trois heures de l apres midi"), ("midi", "huit heures", "huit heures")],
)
def test_l_heure_se_lit_avec_le_moment_garde(moment, heure, attendu):
    etat = {df.CLE_DU_MOMENT: {"moment": moment, "jour": "demain"}} if moment else {}
    assert df.heure_avec_le_moment(etat, heure) == attendu


# ---- la commande (appel 2572)


async def test_commande_demain_soir_puis_huit_heures_et_demie_donne_vingt_heures_trente():
    p, source = P.nouveau(), Calendrier()
    premier = await commande.resoudre_une_date(source, p, None, "demain soir")
    assert premier.statut == "INCOMPLETE" and p["moment_du_jour"]["moment"] == "soir"
    r = await commande.resoudre_une_date(source, p, None, "demain", "Huit heures et demie")
    assert r.statut == "RETENU" and _heure(r) == time(20, 30), r


async def test_commande_le_moment_est_gardé_meme_si_le_jour_est_redit_avec_l_heure_seule():
    p, source = P.nouveau(), Calendrier()
    await commande.resoudre_une_date(source, p, None, "demain soir")
    r = await commande.resoudre_une_date(source, p, None, "", "huit heures")
    assert _heure(r) == time(20, 0) if r.statut == "RETENU" else r.statut != "AMBIGU", r


async def test_commande_demain_matin_puis_huit_heures_donne_huit_heures():
    p, source = P.nouveau(), Calendrier()
    await commande.resoudre_une_date(source, p, None, "demain matin")
    r = await commande.resoudre_une_date(source, p, None, "demain", "huit heures")
    assert r.statut == "RETENU" and _heure(r) == time(8, 0), r


async def test_commande_un_moment_contraire_dit_l_emporte():
    p, source = P.nouveau(), Calendrier()
    await commande.resoudre_une_date(source, p, None, "demain soir")
    r = await commande.resoudre_une_date(source, p, None, "demain", "huit heures du matin")
    assert _heure(r) == time(8, 0), r


async def test_commande_sans_moment_gardé_sept_heures_reste_ambigu():
    p, source = P.nouveau(), Calendrier()
    r = await commande.resoudre_une_date(source, p, None, "demain", "sept heures")
    assert r.statut == "AMBIGU", r


async def test_commande_un_autre_jour_dit_sans_moment_efface_le_moment():
    p, source = P.nouveau(), Calendrier()
    await commande.resoudre_une_date(source, p, None, "demain soir")
    r = await commande.resoudre_une_date(source, p, None, "mercredi", "sept heures")
    assert r.statut == "AMBIGU" and not p.get("moment_du_jour"), r


async def test_commande_la_voie_heure_du_lieu_garde_aussi_le_moment():
    p, source = P.nouveau(), Calendrier()
    await commande.heure_du_lieu(source, "demain soir", p)
    r = await commande.heure_du_lieu(source, "huit heures et demie", p)
    assert r.statut == "RETENU" and _heure(r) == time(20, 30), r


# ---- la réservation (appel 2570)


async def test_reservation_vendredi_soir_puis_huit_heures_et_demie_n_est_plus_ambigu():
    etat, source = {}, Calendrier()
    ap = reservation.Appelant(telephone_affiche="+33612345678")
    premier = await reservation._reserver(source, etat, ap, personnes=4, jour="vendredi soir")
    assert premier.statut == "INCOMPLETE" and premier.manque == "heure"
    r = await reservation._reserver(source, etat, ap, heure="huit heures et demie")
    assert r.statut == "INCOMPLETE" and r.manque == "prenom", r  # l'heure est lue sans doute : on passe au nom
    assert source.heures_recues[-1].endswith("du soir")


async def test_reservation_sans_moment_huit_heures_et_demie_reste_ambigu():
    etat, source = {}, Calendrier()
    ap = reservation.Appelant(telephone_affiche="+33612345678")
    r = await reservation._reserver(source, etat, ap, personnes=4, jour="vendredi", heure="huit heures et demie")
    assert r.statut == "AMBIGU", r


async def test_reservation_vendredi_matin_puis_huit_heures():
    etat, source = {}, Calendrier()
    ap = reservation.Appelant(telephone_affiche="+33612345678")
    await reservation._reserver(source, etat, ap, personnes=2, jour="vendredi matin")
    r = await reservation._reserver(source, etat, ap, heure="huit heures")
    assert r.manque == "prenom", r
    assert source.heures_recues[-1].endswith("du matin")

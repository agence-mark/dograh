"""[.mark] Module Restauration, lot 8, étape 3 : les outils de l'agent pour la réservation (connecteur interne ``reservation``).

Vraie base, même salle que ``test_restauration_reservation.py``, jeudi 12 h, appelant dont le numéro s'affiche.

| Test | Ce qu'il prouve |
|---|---|
| connecteur | cinq outils, aucun paramètre ne porte une organisation, une base ni un établissement ; ceux qui écrivent sont déclarés |
| disponibilités | les trois créneaux les plus proches d'une heure, un par heure sans heure, complet dit sans rien inventer |
| réserver | un manque à la fois, rien de dit n'est perdu, relecture, enregistrement seulement sur le « oui » de CETTE relecture |
| relecture | un « oui » sans relecture relit d'abord ; un changement depuis la relecture invalide le « oui » |
| créneau pris | refusé avec les plus proches, rien écrit ; la place est revérifiée à l'enregistrement |
| numéro | affiché : jamais demandé ; masqué : demandé ; invalide refusé |
| modifier, annuler | la réservation de l'appelant ; plusieurs : on demande laquelle ; l'annulation en deux temps ; le portail l'apprend (événements) |
| retrouver | dit le statut lu, jamais celui d'un autre |
| panne | une base absente rend INDISPONIBLE, l'appel continue |
| vocabulaire | aucun mot de restaurant dans le mécanisme commun |
"""

from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.db.bases_clients import horloge
from api.services.integrations.connectors import catalogue
from api.services.reservation import moteur, porte as porte_resa
from api.services.reservation.moteur import Appelant
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.source_reservation import SourceReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_reservation import SAMEDI_20H, TEL, salle  # noqa: F401

OUTILS = ["fiche", "lire"]  # lot 7 (D49) : la fiche et la lecture remplacent les cinq outils


class Appel:
    def __init__(self, salle, *, affiche: str | None = TEL):
        self.salle = salle
        self.source = SourceReservation(salle.c, Lieu(salle.base, salle.a, 1))
        self.etat: dict = {}
        self.appelant = Appelant(affiche, "appel-resa")

    async def reserver(self, **kw):
        return await moteur.reserver(self.source, self.etat, self.appelant, **kw)

    async def confirmee(self, **plus):
        """Une réservation faite jusqu'au bout : samedi 20 h, deux personnes, Alice."""
        dit = {"jour": "samedi", "heure": "20h", "personnes": 2, "prenom": "Alice", **plus}
        assert (await self.reserver(**dit)).manque == "relecture"
        r = await self.reserver(confirmer=True)
        assert r.statut == "ENREGISTREE", r
        return r


def test_le_connecteur_declare_la_fiche_et_la_lecture_sans_identifiant_du_modele():
    c = catalogue.connecteur("reservation")
    assert c is not None and c.interne and c.executer_interne is not None
    assert [a.nom for a in c.actions] == OUTILS
    for action in c.actions:
        noms = {p.nom for p in action.parametres}
        assert not noms & {"organization_id", "organisation", "base", "etablissement", "etablissement_id", "site", "site_id"}, action.nom
    assert sorted(a.nom for a in c.actions if a.ecrit) == ["fiche"]
    assert catalogue.categorie_de(c) == "Nos connecteurs"


# test_disponibilites_les_plus_proches… : supprimé au lot 7 (D49), les disponibilités se lisent par la lecture et la capacité du formulaire (plus de tables, E1 à E4) ; sens repris par partie_1/test_l07_reservation.py::test_disponibilites_completent_le_brouillon, ::test_capacite_du_jour_unique et ::test_sans_table_la_capacite_du_formulaire_donne_des_creneaux


async def test_un_manque_a_la_fois_rien_de_dit_n_est_perdu_puis_relecture_puis_oui(salle):
    a = Appel(salle)
    assert (await a.reserver()).manque == "personnes"
    assert (await a.reserver(personnes=3)).manque == "jour"
    r = await a.reserver(jour="samedi")
    assert (r.statut, r.manque) == ("INCOMPLETE", "heure")
    r = await a.reserver(heure="20h")
    assert r.manque == "prenom"                                  # personnes, jour et heure sont gardés
    r = await a.reserver(prenom="Alice")
    assert (r.statut, r.manque) == ("INCOMPLETE", "relecture")   # le numéro s'affiche : jamais demandé
    # C6 n° 8 (décision d'Evan 25/11 9 h 30) : la relecture est rendue en faits, le modèle la dit ; la question du numéro gardé (M98) est dite par la porte après sa phrase
    assert not r.suggestion and r.faits["personnes"] == 3 and r.faits["quand"] == "samedi quatorze novembre à vingt heures" and r.faits["prenom"] == "Alice", r
    assert r.faits["heure"] == "vingt heures" and r.faits["numero_affiche_dit"]
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 0   # rien d'écrit avant le « oui »
    fait = await a.reserver(confirmer=True)
    assert fait.statut == "ENREGISTREE" and fait.faits["tables"] == ["T3"]
    ligne = await salle.c.fetchrow("SELECT * FROM mark.resto_reservation")
    assert (ligne["telephone"], ligne["prenom"], ligne["couverts"], ligne["cree_par"], ligne["appel_id"]) == (TEL, "Alice", 3, "agent", "appel-resa")
    assert a.etat.get("brouillon") is None                        # la suivante repart de zéro


# test_un_oui_sans_relecture_relit_d_abord… : supprimé au lot 7 (D49), le manque et la relecture de la réservation sont rendus par la fiche ; sens repris par partie_1/test_l07_reservation.py::test_relecture_deja_dite_commune et ::test_le_manque_est_rendu_par_la_fiche


async def test_un_creneau_pris_est_refuse_avec_les_plus_proches_et_la_place_est_revérifiée(salle):
    for n, tel in ((4, "+33600000002"), (2, "+33600000003"), (2, "+33600000004")):       # à 20 h : T3, T1, T2 pris ; T4 (4 à 6) reste libre
        await Appel(salle, affiche=tel).confirmee(personnes=n, prenom="X")
    a = Appel(salle)
    r = await a.reserver(jour="samedi", heure="20h", personnes=2, prenom="Alice")
    assert (r.statut, r.faits["detail"]) == ("REFUSEE", "complet") and r.faits["propositions"]
    assert "Je peux vous proposer" in r.suggestion
    # la place est REVÉRIFIÉE : relue quand c'était libre, prise entre-temps
    b = Appel(salle, affiche="+33600000009")
    assert (await b.reserver(jour="samedi", heure="19h", personnes=6, prenom="Bob")).manque == "relecture"
    await salle.c.execute(
        "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, telephone, prenom, table_ids) "
        "SELECT gen_random_uuid(), $1, $2, 90, 6, '+33600000010', 'Voleur', ARRAY[(SELECT id FROM mark.resto_table WHERE nom = 'T4')]", salle.a, SAMEDI_20H - timedelta(hours=1),
    )
    pris = await b.reserver(confirmer=True)
    assert pris.statut == "REFUSEE" and pris.faits["detail"] == "complet"


async def test_le_numero_qui_s_affiche_n_est_jamais_demande_masque_il_l_est_invalide_refuse(salle):
    masque = Appel(salle, affiche=None)
    r = await masque.reserver(jour="samedi", heure="20h", personnes=2, prenom="Alice")
    assert (r.statut, r.manque) == ("INCOMPLETE", "telephone")
    assert (await masque.reserver(telephone="pas un numéro")).statut == "ARGUMENT_INVALIDE"
    r = await masque.reserver(telephone="06 12 34 56 78")
    assert r.manque == "relecture"
    assert (await masque.reserver(confirmer=True)).statut == "ENREGISTREE"
    assert await salle.c.fetchval("SELECT telephone FROM mark.resto_reservation") == "+33612345678"


# test_la_reservation_faite_dans_cet_appel_se_change… : supprimé au lot 7 (D49) ; sens repris par partie_1/test_l07_reservation.py::test_celle_de_samedi (la réservation de cet appel) et ::test_jour_puis_heure_en_modification


# test_modifier_et_annuler… en deux temps : supprimé au lot 7 (D49) ; sens repris par partie_1/test_l07_reservation.py::test_quatre_annulations_reservation, ::test_jour_puis_heure_en_modification et ::test_nom_pour_retrouver_pas_pour_changer


# test_une_reservation_passee_ne_se_change… : supprimé au lot 7 (D49), ``moteur.retrouver`` n'existe plus (la lecture retrouve) ; sens repris par partie_1/test_l07_reservation.py::test_nom_pour_retrouver_pas_pour_changer et ::test_reservation_existante_conservee


async def test_le_portail_apprend_la_reservation_et_une_base_absente_rend_indisponible(salle, monkeypatch):
    evenements = []

    async def faux_emettre(organisation, etablissement, type_, donnees, **plus):
        evenements.append((organisation, etablissement, type_, donnees))

    monkeypatch.setattr("api.services.restauration.source_reservation.flux.emettre", faux_emettre)
    a = Appel(salle)
    r = await a.confirmee()
    ctx = SimpleNamespace(organization_id=7)
    await a.source.apres_le_geste("reserver", moteur.Resultat("ENREGISTREE", r.faits, ""), ctx)
    await a.source.apres_le_geste("annuler_reservation", moteur.Resultat("OK", r.faits, ""), ctx)
    await a.source.apres_le_geste("reserver", moteur.Resultat("ENREGISTREE", {}, ""), ctx)       # sans numéro : rien
    await a.source.apres_le_geste("reserver", moteur.Resultat("ENREGISTREE", r.faits, ""), SimpleNamespace(organization_id=None))   # sans organisation : rien
    assert evenements == [
        (7, salle.a, "reservation.creee", {"reservation_id": r.faits["numero"]}),
        (7, salle.a, "reservation.changee", {"reservation_id": r.faits["numero"]}),
    ]
    # une organisation sans base rattachée : l'outil rend INDISPONIBLE, l'appel continue
    ctx_sans_base = SimpleNamespace(organization_id=None, fiche={}, appel={}, run_id=None, reglages={})
    retour = await porte_resa.executer(SimpleNamespace(nom="lire"), {"sujet": "disponibilites", "jour": "samedi", "personnes": 2}, ctx_sans_base, 5.0)
    assert retour["faits"]["indisponible"] is True
    # des arguments du modèle qui n'ont pas de sens : refusés, rien ne casse
    ctx_sans_base.fiche = {}
    r = await porte_resa.executer(SimpleNamespace(nom="fiche"), {"personnes": "beaucoup"}, ctx_sans_base, 5.0)
    assert r["faits"]["indisponible"] is True


# Le vocabulaire : jamais un mot de restaurant dans le mécanisme commun (la source du restaurant vit dans ``services/restauration``).
MOTS_DU_METIER = re.compile(
    r"restaura(?!tion)|pizza|burger|cuisine|boisson|repas|couvert|dessert|ticket|caisse|allerg|titre_restaurant|\bchef\b|livraison|emporter|sur_place|\bcarte\b|\bmenu|serveur|\bplat\b|\bsalle",
    re.IGNORECASE,
)


def test_aucun_mot_de_restaurant_dans_le_mecanisme_commun_de_reservation():
    racine = Path(moteur.__file__).resolve().parent
    for fichier in ("__init__", "source", "moteur", "porte"):
        corps = (racine / f"{fichier}.py").read_text(encoding="utf-8")
        assert [m.group(0) for m in MOTS_DU_METIER.finditer(corps)] == [], fichier

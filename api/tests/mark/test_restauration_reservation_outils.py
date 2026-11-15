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

from api.db.bases_clients import horloge
from api.services.integrations.connectors import catalogue
from api.services.reservation import action as action_resa, moteur
from api.services.reservation.moteur import Appelant
from api.services.restauration.appel import Lieu
from api.services.restauration.source_reservation import SourceReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_reservation import SAMEDI_20H, TEL, salle  # noqa: F401

OUTILS = ["disponibilites", "reserver", "modifier_reservation", "annuler_reservation", "retrouver_reservation"]


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


def test_le_connecteur_declare_les_cinq_outils_sans_identifiant_du_modele():
    c = catalogue.connecteur("reservation")
    assert c is not None and c.interne and c.executer_interne is not None
    assert [a.nom for a in c.actions] == OUTILS
    for action in c.actions:
        noms = {p.nom for p in action.parametres}
        assert not noms & {"organization_id", "organisation", "base", "etablissement", "etablissement_id", "site", "site_id"}, action.nom
    assert sorted(a.nom for a in c.actions if a.ecrit) == ["annuler_reservation", "modifier_reservation", "reserver"]
    assert catalogue.categorie_de(c) == "Nos connecteurs"


async def test_disponibilites_les_plus_proches_ou_un_par_heure_complet_sans_rien_inventer(salle):
    a = Appel(salle)
    r = await moteur.disponibilites(a.source, a.etat, "samedi", 2, "21h")
    assert r.statut == "OK" and len(r.faits["creneaux"]) == 3 and r.faits["creneaux"][1]["debut"].hour == 21
    assert r.faits["complet"] is False and r.suggestion.startswith("Il y a de la place à")
    un_par_heure = await moteur.disponibilites(a.source, a.etat, "samedi", 2)
    assert [c["debut"].hour for c in un_par_heure.faits["creneaux"]] == [19, 20, 21]          # le service finit à 22 h : pas de créneau de 90 minutes plus tard
    assert (await moteur.disponibilites(a.source, a.etat, "samedi", None)).manque == "personnes"
    assert (await moteur.disponibilites(a.source, a.etat, None, 2)).manque == "jour"
    # tout est pris
    for i, (n, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):
        pour_tous = Appel(salle, affiche=tel)
        for heure in ("19h", "20h30"):                       # deux réservations de 90 minutes couvrent tout le service
            assert (await pour_tous.reserver(jour="samedi", heure=heure, personnes=n, prenom=f"P{i}")).manque == "relecture"
            assert (await pour_tous.reserver(confirmer=True)).statut == "ENREGISTREE"
    complet = await moteur.disponibilites(a.source, a.etat, "samedi", 2)
    assert (complet.faits["complet"], complet.faits["creneaux"]) == (True, []) and complet.suggestion == "Nous sommes complets ce jour-là."


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
    assert r.suggestion == "Je vous réserve pour trois personnes, samedi 14 novembre à 20 h, au nom de Alice. C'est bon ?"
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 0   # rien d'écrit avant le « oui »
    fait = await a.reserver(confirmer=True)
    assert fait.statut == "ENREGISTREE" and fait.faits["tables"] == ["T3"]
    ligne = await salle.c.fetchrow("SELECT * FROM mark.resto_reservation")
    assert (ligne["telephone"], ligne["prenom"], ligne["couverts"], ligne["cree_par"], ligne["appel_id"]) == (TEL, "Alice", 3, "agent", "appel-resa")
    assert a.etat.get("brouillon") is None                        # la suivante repart de zéro


async def test_un_oui_sans_relecture_relit_d_abord_un_changement_invalide_le_oui(salle):
    a = Appel(salle)
    r = await a.reserver(jour="samedi", heure="20h", personnes=2, prenom="Alice", confirmer=True)    # le modèle dit « confirmer » trop tôt
    assert r.manque == "relecture" and await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 0
    # un changement depuis la relecture : le « oui » ne vaut plus
    r = await a.reserver(personnes=4, confirmer=True)
    assert r.manque == "relecture" and "quatre personnes" in r.suggestion
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 0
    assert (await a.reserver(confirmer=True)).statut == "ENREGISTREE"
    # le même appel qui recommence la même demande : le même numéro
    assert (await a.reserver(jour="samedi", heure="20h", personnes=4, prenom="Alice")).manque == "relecture"
    deja = await a.reserver(confirmer=True)
    assert deja.statut == "DEJA_FAIT" and await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation") == 1


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


async def test_modifier_et_annuler_la_reservation_de_l_appelant_en_deux_temps_plusieurs_on_demande_laquelle(salle):
    a = Appel(salle)
    r1 = await a.confirmee()
    suivant = Appel(salle)
    # la réservation se retrouve par le numéro qui s'affiche ; un changement se relit avant de s'écrire
    r = await moteur.modifier(suivant.source, suivant.etat, suivant.appelant, personnes=4)
    assert (r.statut, r.manque) == ("INCOMPLETE", "relecture") and "C'est bon ?" in r.suggestion
    assert (await salle.c.fetchval("SELECT couverts FROM mark.resto_reservation")) == 2
    fait = await moteur.modifier(suivant.source, suivant.etat, suivant.appelant, personnes=4, confirmer=True)
    assert (fait.statut, fait.faits["couverts"]) == ("OK", 4)
    # une heure seule garde le jour ; un jour seul redemande l'heure
    assert (await moteur.modifier(suivant.source, suivant.etat, suivant.appelant, jour="dimanche")).manque == "heure"
    assert (await moteur.modifier(suivant.source, suivant.etat, suivant.appelant, heure="21h")).manque == "relecture"
    assert (await moteur.modifier(suivant.source, suivant.etat, suivant.appelant, heure="21h", confirmer=True)).faits["debut"].astimezone(SAMEDI_20H.tzinfo).hour == 21
    # une seconde réservation : on demande laquelle, jamais au hasard
    await Appel(salle).confirmee(jour="dimanche", prenom="Alice")
    deux = await moteur.annuler(suivant.source, suivant.etat, suivant.appelant)
    assert (deux.statut, deux.manque) == ("AMBIGU", "reference") and len(deux.faits["candidats"]) == 2
    numero = deux.faits["candidats"][0]["numero"]
    # l'annulation en deux temps : demander, puis le « oui » pour CETTE réservation
    demande = await moteur.annuler(suivant.source, suivant.etat, suivant.appelant, reference=numero)
    assert (demande.statut, demande.manque) == ("INCOMPLETE", "confirmation") and demande.suggestion.startswith("Vous voulez annuler")
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation WHERE statut = 'confirmee'") == 2
    direct = Appel(salle)
    assert (await moteur.annuler(direct.source, direct.etat, direct.appelant, reference=numero, confirmer=True)).manque == "confirmation"   # « oui » sans demande : demande d'abord
    fait = await moteur.annuler(suivant.source, suivant.etat, suivant.appelant, reference=numero, confirmer=True)
    assert (fait.statut, fait.suggestion) == ("OK", "C'est annulé.")
    assert (await moteur.annuler(suivant.source, suivant.etat, suivant.appelant, reference=numero, confirmer=True)).statut == "INTROUVABLE"   # déjà annulée : plus rien à annuler
    assert await salle.c.fetchval("SELECT count(*) FROM mark.resto_reservation WHERE statut = 'confirmee'") == 1
    _ = r1


async def test_une_reservation_passee_ne_se_change_ni_ne_s_annule_et_retrouver_dit_le_vrai(salle):
    a = Appel(salle)
    await a.confirmee()
    dit = await moteur.retrouver(a.source, a.etat, a.appelant)
    assert dit.statut == "OK" and dit.suggestion == "Vous avez une réservation samedi 14 novembre à 20 h pour deux personnes."
    autre = Appel(salle, affiche="+33699999999")
    assert (await moteur.retrouver(autre.source, autre.etat, autre.appelant)).statut == "INTROUVABLE"       # jamais celle d'un autre
    assert (await moteur.retrouver(autre.source, autre.etat, autre.appelant, prenom="Alice", jour="samedi")).statut == "OK"   # par nom et jour
    with horloge.remplacer(salle.base, SAMEDI_20H + timedelta(minutes=10)):
        assert (await moteur.annuler(a.source, a.etat, a.appelant)).statut == "INTROUVABLE"                # passée : plus « à venir »
    assert JEUDI_MIDI < SAMEDI_20H


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
    retour = await action_resa.executer(SimpleNamespace(nom="disponibilites"), {"jour": "samedi", "personnes": 2}, ctx_sans_base, 5.0)
    assert retour["statut"] == "INDISPONIBLE" and retour["suggestion"] == action_resa.PHRASE_DE_PANNE
    # des arguments du modèle qui n'ont pas de sens : refusés, rien ne casse
    ctx_sans_base.fiche = {}
    r = await action_resa.executer(SimpleNamespace(nom="reserver"), {"personnes": "beaucoup"}, ctx_sans_base, 5.0)
    assert r["statut"] == "INDISPONIBLE"


# Le vocabulaire : jamais un mot de restaurant dans le mécanisme commun (la source du restaurant vit dans ``services/restauration``).
MOTS_DU_METIER = re.compile(
    r"restaura(?!tion)|pizza|burger|cuisine|boisson|repas|couvert|dessert|ticket|caisse|allerg|titre_restaurant|\bchef\b|livraison|emporter|sur_place|\bcarte\b|\bmenu|serveur|\bplat\b|\bsalle",
    re.IGNORECASE,
)


def test_aucun_mot_de_restaurant_dans_le_mecanisme_commun_de_reservation():
    racine = Path(moteur.__file__).resolve().parent
    for fichier in ("__init__", "source", "moteur", "action"):
        corps = (racine / f"{fichier}.py").read_text(encoding="utf-8")
        assert [m.group(0) for m in MOTS_DU_METIER.finditer(corps)] == [], fichier

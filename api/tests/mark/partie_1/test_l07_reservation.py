"""[.mark] Chantier Partie 1, lot 7 : la réservation sur le même contrat que la commande (fiche à cases, porte, règles R01 à R06, B03, B07, B08).

Chaque test passe par la vraie porte (R1) sur la vraie base (la salle de ``test_restauration_reservation.py``, jeudi 12 h, samedi = le 14 novembre) ;
aucun test n'appelle un fournisseur de modèle. Les règles du banc final (``banc-b13/reservation_b13.py``) sont recopiées, jamais réinventées.
"""

from __future__ import annotations

from api.services.actions_communes.du import CLE_DU
from api.services.actions_communes import conversation as CONV
from api.services.gabarits.restauration.textes import banc as B

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from api.db.bases_clients.restauration_reservation import capacite_du_jour, creer_reservation
from api.services.actions_communes.enveloppe import RAISONS_DU_METIER
from api.services.gabarits.restauration.textes import TEMOIN
from api.services.integrations.connectors.actions.reservation import RESERVATION
from api.services.integrations.connectors.outil import _propriete
from api.services.reservation import contrat, moteur
from api.services.reservation import phrases_du_manque as PM
from api.services.workflow import cases_selon_l_etat as CS
from api.tests.mark.partie_1.porte_essai_reservation import TEL, EssaiReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_reservation import PARIS, SAMEDI_20H, salle  # noqa: F401

RACINE = Path(__file__).resolve().parents[3]
DONNEES = Path(__file__).parent / "donnees"
MOTS = "une table pour quatre samedi à vingt heures au nom d'Alice"


# --------------------------------------------------------------------------- aides


def _normal(x):
    if isinstance(x, dict):
        return {k: (sorted(v) if k == "required" else _normal(v)) for k, v in x.items()}
    if isinstance(x, list):
        return [_normal(v) for v in x]
    return x


def _etats_de_reservation():
    for carte, etats in B.rendus()["cartes"].items():
        for e in etats:
            if e["etape"] == "reservation":
                yield carte, e


async def _reservee(essai: EssaiReservation, **plus):
    """Une réservation faite jusqu'au bout : samedi 20 h, Alice (quatre personnes), par la fiche et son « oui »."""
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice", **plus)
    assert r["question"]["type"] == "recapitulatif", r
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    return r


# --------------------------------------------------------------------------- L07-01 : rien de ce qui marche n'est chamboulé (D18)


def rejouer(identifiants: list[str]) -> int:
    """Rejoue ces tests dans un sous-processus ; le code de sortie de pytest (0 : tous verts)."""
    if not identifiants:
        return 0
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-W", "ignore", *identifiants], cwd=RACINE.parent, capture_output=True, text=True)
    return p.returncode


def test_reservation_existante_conservee():
    attendus = json.loads((DONNEES / "reservation_existante.json").read_text(encoding="utf-8"))["verts_a_la_base"]
    assert attendus, "la liste des tests de la réservation verts à la base est vide"
    assert rejouer(attendus) == 0, "un test de la réservation vert avant le lot 7 est rouge (D18)"


def test_le_rejeu_voit_un_rouge():
    """R7 : l'outil de rejeu est éprouvé sur un cas rouge connu avant d'être cru."""
    assert rejouer(["api/tests/mark/partie_1/test_l07_reservation.py::test_ce_test_n_existe_pas"]) != 0


# --------------------------------------------------------------------------- L07-02 : la fiche de la réservation égale celle du banc


def test_schema_fiche_reservation_egal_au_banc():
    action = RESERVATION.action("fiche")
    lecture = RESERVATION.action("lire")
    assert [a.nom for a in RESERVATION.actions] == ["fiche", "lire"]  # les cinq outils d'avant n'existent plus
    vues = list(_etats_de_reservation())
    assert len(vues) >= 18  # les états types sur deux cartes
    for carte, e in vues:
        fiche = next(o["function"] for o in e["outils"] if o["function"]["name"] == "fiche")
        lire = next(o["function"] for o in e["outils"] if o["function"]["name"] == "lire")
        proprietes = {p.nom: _propriete(p, None) for p in action.parametres}
        requis = [p.nom for p in action.parametres if p.obligatoire]
        vue = contrat.VueDeLaReservation.depuis_un_dict(e["vue"])
        rendu, requis_rendu = CS.schema_selon_l_etat(proprietes, requis, contrat.cases_visibles_de_la_vue(vue), contrat.forme_de_la_vue(vue))
        assert _normal(rendu) == _normal(fiche["parameters"]["properties"]), f"{carte} / {e['etat']} : {sorted(set(rendu) ^ set(fiche['parameters']['properties']))}"
        assert sorted(requis_rendu) == sorted(fiche["parameters"].get("required") or []), (carte, e["etat"])
        assert {p.nom: _propriete(p, None) for p in lecture.parametres} == lire["parameters"]["properties"], (carte, "lire")
    assert action.description == next(o["function"]["description"] for o in B.rendus()["cartes"]["300"][-1]["outils"] if o["function"]["name"] == "fiche")


# --------------------------------------------------------------------------- L07-09 : jamais deux cases d'annulation d'un même objet


def test_quatre_annulations_reservation():
    for carte, e in _etats_de_reservation():
        vue = contrat.VueDeLaReservation.depuis_un_dict(e["vue"])
        visibles = contrat.cases_visibles_de_la_vue(vue)
        assert not {"annuler_la_reservation", "annuler_une_reservation_enregistree"} <= visibles, (carte, e["etat"])
        if vue.commencee or vue.objet or (vue.question or {}).get("type") == "choix":
            assert "retrouver_une_reservation_enregistree" not in visibles, (carte, e["etat"])
    assert ("annuler_la_reservation" in contrat.cases_visibles_de_la_vue(contrat.VueDeLaReservation(commencee=True)))
    assert ("annuler_une_reservation_enregistree" in contrat.cases_visibles_de_la_vue(contrat.VueDeLaReservation(existante=True, objet=True)))
    assert "annuler_une_reservation_enregistree" not in contrat.cases_visibles_de_la_vue(contrat.VueDeLaReservation(objet=True))  # annulée


# --------------------------------------------------------------------------- L07-03 : R01, une seule réservation par appel


async def test_on_sera_cinq_pas_de_seconde_table(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await _reservee(essai)
    assert await essai.nombre_de_reservations() == 1
    r = await essai.tour("en fait on sera cinq", personnes=5)
    assert r["question"]["type"] == "recap_modif", r  # elle change CETTE réservation
    assert await essai.nombre_de_reservations() == 1
    direct = await moteur.reserver(essai.source, essai.etat, essai.moteur_appelant, personnes=2, jour="samedi", heure="20h", prenom="Bob")
    assert direct.statut == "DEJA_FAIT" and direct.faits["raison"] == "deja_une_reservation_dans_cet_appel"
    assert await essai.nombre_de_reservations() == 1


# --------------------------------------------------------------------------- L07-04 : R02, le doute ne retire que son champ


async def test_heure_ambigue_garde_le_jour(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("quatre personnes samedi à sept heures", personnes=4, jour="samedi", heure="sept heures")
    assert r["statut"] == "A_PRECISER" and r["manque"] == "heure", r
    brouillon = essai.etat["brouillon"]
    assert brouillon["jour"] == "samedi" and "heure" not in brouillon and brouillon["personnes"] == 4


# --------------------------------------------------------------------------- L07-05 : R03, le jour dit sans l'heure est gardé


async def test_jour_puis_heure_en_modification(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await _reservee(essai)
    r = await essai.tour("plutôt dimanche", jour="dimanche")
    assert r["manque"] == "heure" and essai.etat["modification"]["jour"] == "dimanche", r
    r = await essai.tour("à dix-neuf heures", heure="dix-neuf heures")
    # C6 n° 8 (décision d'Evan 25/11 9 h 30) : la relecture du changement est dite par le modèle, d'après ce qui change (faits)
    assert r["question"]["type"] == "recap_modif" and "dimanche" in r["faits"]["ce_qui_change"]["quand"], r  # le bon jour, pas l'ancien


# --------------------------------------------------------------------------- L07-06 : R06, la lecture des places lit le brouillon, n'écrit jamais


async def test_disponibilites_completent_le_brouillon(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await essai.tour("quatre personnes samedi", personnes=4, jour="samedi")
    avant = json.dumps(essai.etat, sort_keys=True, default=str)
    r = await essai.lecture(sujet="places_libres")
    assert r["statut"] == "LU" and r["faits"]["horaires_libres"], r  # personnes et jour ne sont pas redemandés
    assert json.dumps(essai.etat, sort_keys=True, default=str) == avant  # E16 : la lecture n'écrit jamais


# --------------------------------------------------------------------------- L07-07 : R04, B08, désigner une réservation par ses mots


async def _deux_reservations(salle):
    for numero, debut, personnes in (("a", SAMEDI_20H, 2), ("b", SAMEDI_20H.replace(day=15, hour=19), 3)):
        r = await creer_reservation(salle.c, salle.a, {"debut": debut, "couverts": personnes, "prenom": "Alice", "telephone": TEL, "appel_id": f"avant-{numero}"})
        assert r.statut == "ENREGISTREE", r
        yield r.faits["numero"]


async def test_celle_de_samedi(salle, monkeypatch):
    samedi, dimanche = [n async for n in _deux_reservations(salle)]
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    assert r["statut"] == "A_PRECISER" and r["question"]["type"] == "choix", r
    assert len(CONV.question_de(essai.etat)["candidats"]) == 2
    r = await essai.tour("celle de samedi", reponse={"question_id": r["question"]["id"], "sens": "autre", "valeurs": ["celle de samedi"]})
    assert essai.etat["cible"] == samedi, r  # le code a retrouvé le candidat ; l'identifiant interne n'est jamais attendu du modèle
    # « la deuxième » : l'ordre dans lequel le code les a dites
    essai2 = EssaiReservation(salle, monkeypatch)
    r = await essai2.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    await essai2.tour("la deuxième", reponse={"question_id": r["question"]["id"], "sens": "autre", "valeurs": ["la deuxième"]})
    assert essai2.etat["cible"] == dimanche
    # deux fois sans comprendre : la sortie, jamais une troisième question
    essai3 = EssaiReservation(salle, monkeypatch)
    r = await essai3.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    r = await essai3.tour("euh bleu", reponse={"question_id": r["question"]["id"], "sens": "autre", "valeurs": ["bleu"]})
    assert r["question"]["id"] and "cible" not in essai3.etat
    r = await essai3.tour("bleu encore", reponse={"question_id": r["question"]["id"], "sens": "autre", "valeurs": ["bleu"]})
    assert r["raison"] == "choix_non_compris_deux_fois" and "question" not in r, r


# --------------------------------------------------------------------------- L07-08 : R05, le nom dit pour retrouver ne renomme jamais


async def test_nom_pour_retrouver_pas_pour_changer(salle, monkeypatch):
    await creer_reservation(salle.c, salle.a, {"debut": SAMEDI_20H, "couverts": 2, "prenom": "Alice", "telephone": TEL, "appel_id": "avant"})
    essai = EssaiReservation(salle, monkeypatch, appelant=None)  # numéro masqué
    r = await essai.tour("je veux retrouver ma réservation", retrouver_une_reservation_enregistree={})
    assert r["manque"] == "nom_et_jour_de_la_reservation" and essai.etat["recherche"], r
    r = await essai.tour("au nom d'Alice samedi", nom="Alice", jour="samedi")
    assert essai.etat.get("cible") and "modification" not in essai.etat and "question" not in r, r  # retrouvée, pas renommée
    assert await salle.c.fetchval("SELECT prenom FROM mark.resto_reservation") == "Alice"
    r = await essai.tour("mettez-la au nom de Durand", nom="Durand")
    assert r["question"]["type"] == "recap_modif" and r["faits"]["ce_qui_change"] == {"prenom": "Durand"}, r  # changer le nom est un autre geste (C6 n° 8 : en faits)


# --------------------------------------------------------------------------- L07-10 : B03, une seule capacité du jour, plans du soir compris


async def test_capacite_du_jour_unique(salle, monkeypatch):
    from api.db.bases_clients.restauration_plan_soir import poser_plan_du_soir

    t = salle.t
    plan = await poser_plan_du_soir(salle.c, salle.a, date(2026, 11, 14), [[t["T1"], t["T3"]]])
    assert plan.statut == "OK", plan
    await creer_reservation(salle.c, salle.a, {"debut": SAMEDI_20H, "couverts": 6, "prenom": "Zoe", "telephone": "+33600000001", "appel_id": "z"})  # prend la table de six
    jour = date(2026, 11, 14)
    capacite = await capacite_du_jour(salle.c, salle.a, jour, 5)
    assert any(c["debut"] == SAMEDI_20H for c in capacite.faits["creneaux"]), "le plan du soir rassemble T1 et T3 : cinq personnes tiennent à vingt heures"
    # la recherche des places, la relecture et l'enregistrement disent la même chose
    essai = EssaiReservation(salle, monkeypatch)
    lu = await essai.lecture(sujet="places_libres", jour="samedi", personnes=5)
    assert "vingt heures" in lu["faits"]["horaires_libres"] or lu["faits"]["horaires_libres"], lu
    r = await essai.tour("cinq personnes samedi à vingt heures au nom d'Alice", personnes=5, jour="samedi", heure="vingt heures", nom="Alice")
    assert r["question"]["type"] == "recapitulatif", r  # la relecture ne refuse pas ce que l'enregistrement accepte
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    from api.db.bases_clients import restauration

    # une seule capacité : le contrat comptoir ↔ classeur rend, après l'enregistrement, ce que rend ``capacite_du_jour`` (comportement, pas écriture)
    apres = await capacite_du_jour(salle.c, salle.a, jour, 5)
    assert (await restauration.disponibilites_capacite(salle.c, salle.a, jour, 5)).faits == apres.faits


# --------------------------------------------------------------------------- L07-11 : B07, un seul nom pour le nombre de personnes


def test_un_seul_nom_personnes():
    dossiers = [RACINE / "services" / "reservation", RACINE / "services" / "restauration" / "source_reservation.py"]
    fichiers = [f for d in dossiers for f in ([d] if d.is_file() else sorted(d.glob("*.py")))]
    for f in fichiers:
        assert "effectif" not in f.read_text(encoding="utf-8"), f"« effectif » dans {f.name} : un seul nom, « personnes » (B07)"
    from api.services.restauration import source_reservation as S

    assert S.vers_le_classeur({"personnes": 4, "debut": 1}) == {"couverts": 4, "debut": 1}
    assert S.vers_le_moteur({"couverts": 4, "numero": "x"}) == {"personnes": 4, "numero": "x"}
    appelants = [f.name for f in fichiers if "vers_le_classeur" in f.read_text(encoding="utf-8") or "vers_le_moteur" in f.read_text(encoding="utf-8")]
    assert appelants == ["source_reservation.py"]  # la seule rencontre des deux mots, à la source


# --------------------------------------------------------------------------- L07-12 : le module commun importé (R14, R15)


def test_reservation_sans_copies_privees():
    for f in sorted((RACINE / "services" / "reservation").glob("*.py")):
        texte = f.read_text(encoding="utf-8")
        assert "commande.parole" not in texte and "commande.resultat" not in texte, f"{f.name} importe de la commande (R15)"
        assert not re.search(r"^def (_jsonable|_texte|_entier)\b", texte, re.M), f"{f.name} recopie une aide commune (R14)"
        assert not re.search(r"from api\.services\.[\w.]+ import (_\w+)", texte), f"{f.name} importe un nom privé"
    assert not (RACINE / "services" / "reservation" / "action.py").exists()
    porte = (RACINE / "services" / "reservation" / "porte.py").read_text(encoding="utf-8")
    assert "lire_un_texte" in porte and "actions_communes" in porte


# --------------------------------------------------------------------------- L07-13 : la relecture déjà dite passe par la même clé que la commande (R08)


async def test_relecture_deja_dite_commune(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    fiche = {"personnes": 4, "jour": "samedi", "heure": "vingt heures", "nom": "Alice"}
    r = await essai.tour(MOTS, **fiche)
    assert r["question"]["type"] == "recapitulatif"
    rejouee = await essai.fiche(**fiche)  # la même fiche, dans le même tour : rien ne change, une seule relecture
    assert rejouee["faits"]["deja_fait"] is True and rejouee["statut"] == "FAIT"
    from api.services.actions_communes.idempotence import cle_d_idempotence

    assert any(cle_d_idempotence(essai.fiche_de_l_appel[CS.CLE_DU_TOUR], "fiche", fiche) in CONV.de(essai.etat).get("fiches_executees", []) for _ in [0])


# --------------------------------------------------------------------------- L07-14 : l'issue est posée par l'opération (C10)


async def test_issue_reservation_par_l_operation(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert "call_disposition" not in essai.fiche_de_l_appel  # une relecture n'enregistre rien
    from api.services.reservation.porte import issue_de_fin_d_appel

    assert issue_de_fin_d_appel(essai.fiche_de_l_appel) == "reservation_abandonnee"  # commencée, jamais enregistrée
    q = CONV.question_de(essai.etat)
    await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert essai.fiche_de_l_appel["call_disposition"] == "reservation_enregistree"
    r = await essai.tour("on sera cinq", personnes=5)
    await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert essai.fiche_de_l_appel["call_disposition"] == "reservation_modifiee"
    r = await essai.tour("annulez", annuler_une_reservation_enregistree=True)
    assert r["question"]["type"] == "annulation" and essai.fiche_de_l_appel["call_disposition"] == "reservation_modifiee"  # rien d'annulé avant son oui
    await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert essai.fiche_de_l_appel["call_disposition"] == "reservation_annulee"


# --------------------------------------------------------------------------- L07-15 : le tronc de la réservation sans « sens et mots » (R16)


def _prompts_de_reservation() -> dict[str, str]:
    from api.services.gabarits.restauration import textes

    # Lot 5 (n° 144) : les prompts versés par carte n'existent plus ; ils sont rendus depuis le texte à trous (la source unique) pour les deux cartes qui avaient une réservation.
    return {f"reservation-{carte}": B.prompt("reservation", carte) for carte in ("300", "300b")}


def test_tronc_sans_sens_ni_mots():
    prompts = _prompts_de_reservation()
    assert prompts
    for nom, texte in prompts.items():
        assert "le sens de sa réponse" not in texte and "et ses mots tels quels" not in texte, nom
        assert "par la sortie rendre_la_main" in texte, nom  # D44 : le nom de la sortie, jamais « la sortie retour »
        assert "sortie retour" not in texte, nom
    # R7 : le test voit rouge quand la phrase de production est là
    mutee = next(iter(prompts.values())) + " Quand elle répond, tu passes à l'outil le sens de sa réponse et ses mots tels quels."
    assert "le sens de sa réponse" in mutee


# --------------------------------------------------------------------------- L07-16 : une précision seule n'ouvre pas une création


async def test_precision_seule_n_ouvre_pas(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await essai.tour("une chaise haute", precision="une chaise haute")
    assert r["statut"] == "FAIT" and r["resultats"][0]["faits"]["precision_gardee"] is True and "question" not in r, r
    assert await essai.nombre_de_reservations() == 0 and not moteur.reservation_commencee(essai.etat)
    assert essai.etat["brouillon"]["note"] == "une chaise haute"
    r = await essai.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    assert r["manque"] == "nom_et_jour_de_la_reservation", r  # nom et jour demandés, la précision reste gardée
    assert essai.etat["brouillon"]["note"] == "une chaise haute"


# --------------------------------------------------------------------------- L07-17 : les phrases du manque, mot pour mot (B12 décision 1)


def test_valeurs_du_manque_reservation():
    attendu = {
        "le nombre de personnes": "Pour combien de personnes ?", "le jour": "Pour quel jour ?", "l'heure": "À quelle heure ?", "le nom": "À quel nom ?",
        "le numéro de téléphone": "Quel est votre numéro de téléphone ?",
        "le nom et le jour de sa réservation d'avant": "À quel nom et pour quel jour était votre réservation ?",
    }
    assert PM.VALEURS_DU_MANQUE == frozenset(attendu)  # C7 B9 : la valeur fermée seule ; la phrase d'avant (``attendu``) reste comme mémoire, le modèle la pose
    from api.services.reservation import etat_pour_le_modele as E

    # lot 7b-C5 (décision d'Evan 25/11 8 h 45) : le code ne dit plus la phrase du manque ; la relance du modèle reçoit la VALEUR fermée (``valeur_du_manque``)
    assert PM.valeur_du_manque({}) == "le nombre de personnes"
    assert PM.valeur_du_manque({"brouillon": {"personnes": 4}}) == "le jour"
    assert PM.valeur_du_manque({"brouillon": {"personnes": 4, "jour": "samedi", "heure": "20h", "prenom": "A"}, "numero_affiche": False}) == "le numéro de téléphone"
    assert PM.valeur_du_manque({"recherche": True}) == "le nom et le jour de sa réservation d'avant"
    assert PM.valeur_du_manque({CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1"}}}) is None  # une question porte ce qui manque
    assert {E.ce_qui_manque_ensuite({}, True), E.ce_qui_manque_ensuite({"recherche": True}, True)} <= set(attendu)
    from api.tests.mark.partie_1 import glossaire  # noqa: F401  # les raisons de refus de la réservation sont rangées « métier »

    assert {"passe", "trop_tot", "trop_loin", "hors_service", "ferme", "type_ferme", "passee", "plus_modifiable", "complet_a_cette_heure"} <= RAISONS_DU_METIER


async def test_le_manque_est_rendu_par_la_fiche(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("quatre personnes", personnes=4)
    assert r["manque"] == "jour" and r[CLE_DU]["manque"] == "le jour", r  # lot 7b-C5 : la valeur fermée, jamais sa phrase

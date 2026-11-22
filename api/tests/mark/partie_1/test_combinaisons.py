"""[.mark] Clôture de la Partie 1, lot A4 : le test des combinaisons (audit du code § 4), sans modèle, sur la vraie porte (``combinaisons.py``).

Niveaux (revue d'ingénierie, point 4) :
* ``-m "combinaisons and not combinaisons_longues"`` : la profondeur 1 (chaque geste depuis chaque état), les défauts connus (DF1 à DF15 et la file du 21/11) et le gabarit ;
* ``-m combinaisons_longues`` (le module entier porte aussi ``combinaisons``) : profondeur 2, gestes fusionnés par deux, 2 000 suites de 6 gestes tirées avec une graine (avant chaque déploiement).

Critère du lot A : rouge sur les défauts connus, AVANT tout correctif (une ligne par défaut dans le rapport ``banc-final/lot-a-combinaisons.json``,
écrit quand ``MARK_RAPPORT_COMBINAISONS`` donne le dossier). S5 (fin du lot B) : tout vert. Hors de la suite par défaut tant que le lot B n'a pas
posé ses mécanismes (``-m "not combinaisons and not combinaisons_longues"``), puis dans la suite.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from api.tests.mark.partie_1 import combinaisons as C

pytestmark = pytest.mark.combinaisons

# Les défauts connus (audit du code § 4, « ce que le test verrait rouge ») : DFn = Cn de l'audit des conversations.
DEFAUTS_CONNUS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "DF1 changement perdu pendant une question": [("E7", ("G29",)), ("E5", ("G29",)), ("E14", ("G29",))],
    "DF2 proposition jamais fermée": [("E7", ("G25", "G20")), ("E7", ("G23+G6",))],
    "DF3 relecture fermée ou marquée sans être dite": [("E11", ("G25", "G23")), ("E7", ("G25+G20", "G21"))],
    "DF4 fiche vide dite comme faite": [("E4", ("G30",)), ("E16", ("G8",))],
    "DF5 « pardon » après une action faite": [("E16", ("G35",)), ("E17", ("G35",))],
    "DF7 fait redit sans sortie": [("E10", ("G30", "G30", "G30")), ("E3", ("G17", "G17", "G17"))],
    "DF8 deux cases en conflit exécutées": [("E4", ("G10",))],
    "DF9 article perdu par la garde de la réponse": [("E6", ("G26+G6",)), ("E6", ("G26+G4",))],
    "DF10 numéro de question qui change": [("E5", ("G26", "G26", "G26", "G27"))],
    "DF11 annulation sans phase": [("E17", ("G1",)), ("E16", ("G22",))],
    "DF14 relecture et prix": [("E4", ("G20",))],
    "DF15 deux questions dans le tour": [("E0", ("G17+G1",))],
    "file du 21/11": [("E7", ("G2+G15",)), ("E7", ("G25+G20",))],
}
RAPPORT = os.environ.get("MARK_RAPPORT_COMBINAISONS")
GRAINE = int(os.environ.get("MARK_GRAINE_COMBINAISONS", "20261122"))


def _ecrire(nom: str, contenu: dict) -> None:
    if RAPPORT:
        Path(RAPPORT).mkdir(parents=True, exist_ok=True)
        (Path(RAPPORT) / f"{nom}.json").write_text(json.dumps(contenu, ensure_ascii=False, indent=1), encoding="utf-8")


def _lignes(resultats) -> list[str]:
    return [f"{r.etat} → {' · '.join(r.suite)} [{g}] {regle} : {detail}" for r in resultats for g, regle, detail in r.fautes]


@pytest.mark.parametrize("etat", C.ETATS)
async def test_profondeur_1(faire_monde, monkeypatch, etat):
    """Chaque geste, seul, depuis l'état ; les règles RC1 à RC15 après le geste. Un état non atteint n'est jamais compté vert."""
    monde = await faire_monde("casa-italia")
    resultats = [await C.jouer(monde, monkeypatch, etat, (code,)) for code in C.GESTES]
    _ecrire(f"profondeur-1-{etat}", C.rapport(resultats, f"profondeur 1 depuis {etat}"))
    if not resultats[0].atteint:
        pytest.skip(f"{etat} non atteint par sa recette sur Casa Italia jeudi midi (dit au rapport)")
    assert not _lignes(resultats), "\n".join(_lignes(resultats))


@pytest.mark.parametrize("defaut", DEFAUTS_CONNUS)
async def test_defauts_connus(faire_monde, monkeypatch, defaut):
    """Les suites de l'audit, une par défaut connu : rouges avant le lot B (critère du lot A), vertes après (S5)."""
    monde = await faire_monde("casa-italia")
    resultats = [await C.jouer(monde, monkeypatch, etat, suite) for etat, suite in DEFAUTS_CONNUS[defaut]]
    _ecrire("defaut-" + defaut.split()[0], {**C.rapport(resultats, defaut), "lignes": _lignes(resultats)})
    non_atteints = [r.etat for r in resultats if not r.atteint]
    assert not _lignes(resultats) and not non_atteints, "\n".join(_lignes(resultats) + [f"non atteint : {e}" for e in non_atteints])


def test_rc14_action_ouverte_joignable():
    """RC14 (M8, DF6) : sur le gabarit, la sortie ``rendre_la_main`` de la commande et de la réservation se ferme quand l'action est ouverte."""
    fautes = C.rc14_gabarit()
    assert not fautes, fautes


@pytest.mark.combinaisons_longues
@pytest.mark.parametrize("etat", C.ETATS)
async def test_profondeur_2(faire_monde, monkeypatch, etat):
    monde = await faire_monde("casa-italia")
    codes = list(C.GESTES)
    resultats = [await C.jouer(monde, monkeypatch, etat, (a, b)) for a in codes for b in codes]
    _ecrire(f"profondeur-2-{etat}", C.rapport(resultats, f"profondeur 2 depuis {etat}"))
    assert not _lignes(resultats), "\n".join(_lignes(resultats)[:60])


@pytest.mark.combinaisons_longues
@pytest.mark.parametrize("etat", C.ETATS)
async def test_fusions_de_deux(faire_monde, monkeypatch, etat):
    monde = await faire_monde("casa-italia")
    codes = [g.code for g in C.FUSIONNABLES]
    resultats = [await C.jouer(monde, monkeypatch, etat, (f"{a}+{b}",)) for i, a in enumerate(codes) for b in codes[i + 1:]]
    _ecrire(f"fusions-{etat}", C.rapport(resultats, f"deux gestes fusionnés depuis {etat}"))
    assert not _lignes(resultats), "\n".join(_lignes(resultats)[:60])


@pytest.mark.combinaisons_longues
async def test_suites_tirees(faire_monde, monkeypatch):
    """2 000 suites de 6 gestes, graine écrite ; chaque suite rouge est réduite à la plus courte qui reste rouge (gardée au rapport comme cas fixe)."""
    monde = await faire_monde("casa-italia")
    resultats, reduites = [], []
    for etat, suite in C.tirer(GRAINE, int(os.environ.get("MARK_NOMBRE_DE_SUITES", "2000")), 6):
        r = await C.jouer(monde, monkeypatch, etat, suite)
        resultats.append(r)
        if r.fautes and len(reduites) < 25:
            reduites.append(await C.reduire(monde, monkeypatch, r))
    _ecrire("suites-tirees", {**C.rapport(resultats, "suites tirées", GRAINE), "reduites": _lignes(reduites)})
    assert not _lignes(resultats), "\n".join(_lignes(reduites)[:60])


def test_le_temps_du_code_par_fiche_est_releve():
    """S4a : le seuil (50 ms au 95e centile par fiche) est lu dans le rapport ; ici, seulement que la mesure existe (sans base)."""
    assert C.centile([10.0, 20.0, 30.0, 40.0, 100.0], 0.95) == 100.0


# --------------------------------------------------------------------------- DF12 : la réservation (même règles, autre module ; RC4, RC15, M9)

from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation  # noqa: E402
from api.tests.mark.test_restauration_reservation import SAMEDI_20H, salle  # noqa: E402,F401


async def test_defauts_connus_df12_reservation(salle, monkeypatch):  # noqa: F811
    """DF12 (C12) : « oui c'est bon, à vingt heures » à la relecture ; un créneau complet propose des heures (jamais ``null``)."""
    from api.db.bases_clients.restauration_reservation import creer_reservation
    from api.services.actions_communes import parole as PAROLE

    fautes = []
    e = EssaiReservation(salle, monkeypatch)
    r = await e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r.get("question") or {}
    if q.get("type") != "recapitulatif":
        fautes.append(f"relecture non atteinte : {r}")
    else:
        r = await e.tour("oui c'est bon, à vingt heures", reponse={"question_id": q["id"], "sens": "accepte"}, heure="vingt heures")
        dit = " ".join((e.fiche_de_l_appel.get(PAROLE.CLE_TEXTES_DU_CODE) or {}).values())
        if r.get("statut") != "ENREGISTREE":
            fautes.append(f"RC4 : l'accord avec l'heure redite n'enregistre pas (statut {r.get('statut')}, {r.get('raison')})")
        elif not dit:
            fautes.append("RC4 : réservation enregistrée, le code ne le dit pas")
    await creer_reservation(salle.c, salle.a, {"debut": SAMEDI_20H, "couverts": 6, "prenom": "Zoe", "telephone": "+33600000001", "appel_id": "z"})
    e2 = EssaiReservation(salle, monkeypatch, appelant="+33600000077")
    r2 = await e2.tour("six personnes samedi à vingt heures au nom de Bob", personnes=6, jour="samedi", heure="vingt heures", nom="Bob")
    heures = [x.get("heure_dite") for x in (r2.get("faits") or {}).get("propositions") or [] if isinstance(x, dict)]
    if any(h is None for h in heures) or '"quand_dit": null' in json.dumps(r2):
        fautes.append(f"M9 : créneau complet, des heures proposées à null : {json.dumps(r2.get('faits'), ensure_ascii=False)[:300]}")
    _ecrire("defaut-DF12", {"lignes": fautes})
    assert not fautes, "\n".join(fautes)

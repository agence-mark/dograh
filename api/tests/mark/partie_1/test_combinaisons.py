"""[.mark] Clôture de la Partie 1, lot A4 : le test des combinaisons (audit du code § 4), sans modèle, sur la vraie porte (``combinaisons.py``).

Niveaux (revue d'ingénierie, point 4) :
* ``-m "combinaisons and not combinaisons_longues"`` : la profondeur 1 (chaque geste depuis chaque état), les défauts connus (DF1 à DF15 et la file du 21/11) et le gabarit ;
* ``-m combinaisons_longues`` (le module entier porte aussi ``combinaisons``) : profondeur 2, gestes fusionnés par deux, 2 000 suites de 6 gestes tirées avec une graine (avant chaque déploiement).

Critère du lot A : rouge sur les défauts connus, AVANT tout correctif (une ligne par défaut dans le rapport ``banc-final/lot-a-combinaisons.json``,
écrit quand ``MARK_RAPPORT_COMBINAISONS`` donne le dossier). S5 (fin du lot B) : tout vert. Hors de la suite par défaut tant que le lot B n'a pas
posé ses mécanismes (``-m "not combinaisons and not combinaisons_longues"``), puis dans la suite.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

import pytest

from api.services.actions_communes import journal_du_dit as J
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
    # Un état non atteint ÉCHOUE (Pierre 15) : jamais ``skip``, jamais compté vert ; sa recette est à corriger.
    assert resultats[0].atteint, f"{etat} non atteint par sa recette sur Casa Italia (jeudi midi ; E9 : jeudi 15 h)"
    assert not _lignes(resultats), "\n".join(_lignes(resultats))


@pytest.mark.parametrize("defaut", DEFAUTS_CONNUS)
async def test_defauts_connus(faire_monde, monkeypatch, defaut):
    """Les suites de l'audit, une par défaut connu : rouges avant le lot B (critère du lot A), vertes après (S5)."""
    monde = await faire_monde("casa-italia")
    resultats = [await C.jouer(monde, monkeypatch, etat, suite) for etat, suite in DEFAUTS_CONNUS[defaut]]
    _ecrire("defaut-" + defaut.split()[0], {**C.rapport(resultats, defaut), "lignes": _lignes(resultats)})
    non_atteints = [r.etat for r in resultats if not r.atteint]
    assert not _lignes(resultats) and not non_atteints, "\n".join(_lignes(resultats) + [f"non atteint : {e}" for e in non_atteints])


@pytest.mark.parametrize("modele", C.FICHES_EN_PANNE, ids=lambda m: m.nom)
async def test_rc13_tout_ou_rien_par_case_meme_en_panne(faire_monde, monkeypatch, modele):
    """RC13 : une panne simulée à CHAQUE case de la fiche ; le panier d'après est celui d'avant, ou celui que le retour dit fait (jamais un panier à moitié changé)."""
    monde = await faire_monde("casa-italia")
    cases = C.cases_de_la_fiche(modele.fiche({"lignes": [{"n": 1, "ref": C.MARGHERITA, "quantite": 1}]}))
    assert len(cases) >= 3, cases
    fautes = []
    for case in cases:
        fautes += [f"{modele.nom} [{case}] {regle} : {detail}" for regle, detail in await C.jouer_en_panne(monde, monkeypatch, modele, case)]
    _ecrire("rc13-" + modele.nom.split(",")[0].replace(" ", "-"), {"cases": cases, "fautes": fautes})
    assert not fautes, "\n".join(fautes)


def test_rc13_vu_rouge_sur_une_panne_sans_cases_dites():
    """La règle est vue rouge : un panier à moitié changé sans que le retour dise quelles cases sont faites échoue ; le panier d'avant, ou les cases dites faites, passent."""
    modele = C.FICHES_EN_PANNE[0]
    cases = ["retirer_article", "ajouter", "informations", "c_est_tout"]
    margherita, vide = C.Counter({C.MARGHERITA: 1}), C.Counter()
    panne = {"statut": "REJETEE", "faits": {"indisponible": True}}
    assert C.rc13(modele, cases, "ajouter", margherita, vide, panne), "panier à moitié changé, rien dit : doit échouer"
    assert not C.rc13(modele, cases, "ajouter", margherita, margherita, panne), "panier d'avant : passe"
    assert not C.rc13(modele, cases, "ajouter", margherita, vide, {**panne, "cases_executees": ["retirer_article"]}), "cases faites dites : passe"
    assert C.rc13(modele, cases, "ajouter", margherita, vide, {**panne, "cases_executees": ["ajouter"]}), "cases dites qui ne sont pas celles d'avant la panne"
    assert C.rc13(modele, cases, "ajouter", margherita, margherita, {"statut": "FAIT", "faits": {}}), "une panne non dite au retour"


# RC15 : une même fiche mal formée, sur la commande et sur la réservation (M3, M9) : la même raison de refus.
FICHES_MAL_FORMEES = {
    "mauvais numéro": lambda q: {"reponse": {"question_id": "Q-99", "sens": "accepte"}},
    "sens mal formé": lambda q: {"reponse": {"question_id": q, "sens": "refuse}"}},
    "sans numéro": lambda q: {"reponse": {"sens": "accepte"}},
    "réponse vide": lambda q: {"reponse": {}},
    "sans sens": lambda q: {"reponse": {"question_id": q}},
    "autre sans valeur": lambda q: {"reponse": {"question_id": q, "sens": "autre"}},
    "case inconnue": lambda q: {"truc": 1},
}


@pytest.mark.parametrize("avec_question", [False, True], ids=["sans question posée", "question posée"])
async def test_rc15_meme_faute_meme_traitement(faire_monde, salle, monkeypatch, avec_question):  # noqa: F811
    from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

    monde = await faire_monde("casa-italia")
    fautes = []
    for nom, fiche in FICHES_MAL_FORMEES.items():
        commande, reservation = C.Partie(monde, monkeypatch), EssaiReservation(salle, monkeypatch)
        qc = qr = None
        if avec_question:
            assert await commande.recette("E7")  # une proposition posée
            qc = C.question(commande.p)["id"]
            r = await reservation.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
            assert (r.get("question") or {}).get("type") == "recapitulatif", r  # une relecture posée
            qr = r["question"]["id"]
        rc = await commande.e.tour("x", **fiche(qc))
        rr = await reservation.tour("x", **fiche(qr))
        fautes += [f"{avec_question and 'question posée' or 'sans question'} : {detail}" for _, detail in C.rc15_meme_traitement(nom, rc, rr)]
    _ecrire(f"rc15-{'avec' if avec_question else 'sans'}-question", {"fautes": fautes})
    assert not fautes, "\n".join(fautes)


def test_rc15_vu_rouge_sur_deux_raisons_differentes():
    a = {"raison": "question_inconnue", "refus": [{"raison": "question_inconnue"}], "cases_refusees": ["reponse"]}
    assert not C.rc15_meme_traitement("x", a, dict(a, statut="REJETEE"))
    assert C.rc15_meme_traitement("x", a, {"raison": "case_sans_objet", "refus": [{"raison": "case_sans_objet"}], "cases_refusees": ["reponse"]})


# --------------------------------------------------------------------------- Pierre 15 : le test des combinaisons est vu rouge sur ce qu'il ne voyait pas


def _observation(**plus):
    base = dict(geste="G13", avant={}, apres={}, retour={}, textes={}, decision=None, attendu=C.Counter(), fiche={"annuler_la_commande": True})
    return C.Observation(**{**base, **plus})


@pytest.mark.parametrize("etat", ["E8", "E9"])
async def test_e8_e9_sont_atteints_jamais_sautes(faire_monde, monkeypatch, etat):
    """E8 (formule à étapes) et E9 (fermé, heure proposée) sont réellement atteints sur Casa Italia ; un état non atteint ÉCHOUE, il ne se saute jamais."""
    monde = await faire_monde("casa-italia")
    resultat = await C.jouer(monde, monkeypatch, etat, ())
    assert resultat.atteint, f"{etat} non atteint par sa recette"
    partie = C.Partie(monde, monkeypatch)
    with C.horloge.remplacer(monde.base, C.FERMETURE) if etat == "E9" else contextlib.nullcontext():
        assert await partie.recette(etat)
        assert C.question(partie.p)["type"] == ("etape" if etat == "E8" else "heure_proposee")


def test_un_effet_non_declare_echoue_vu_rouge():
    assert C.rc2(_observation(attendu=None)), "un geste sans effet déclaré doit faire échouer le cas"
    assert not C.rc2(_observation(attendu=C.Counter()))


async def test_une_fusion_sans_effet_connu_echoue(faire_monde, monkeypatch):
    """Une fusion dont l'effet d'un des gestes n'est pas connu échoue au lieu de passer verte (300 fusions sur 378 ne contrôlaient pas le panier)."""
    from dataclasses import replace

    monde = await faire_monde("casa-italia")
    monkeypatch.setitem(C.GESTES, "G6", replace(C.GESTES["G6"], effet=lambda avant, p: None))
    r = await C.jouer(monde, monkeypatch, "E4", ("G1+G6",))
    assert any(regle == "RC2" and "non déclaré" in detail for _, regle, detail in r.fautes), r.fautes
    r = await C.jouer(monde, monkeypatch, "E4", ("G6",))
    assert any(regle == "RC2" and "non déclaré" in detail for _, regle, detail in r.fautes), r.fautes


async def test_un_article_compte_en_trop_dans_une_fusion_est_vu(faire_monde, monkeypatch):
    """« oui » + « encore une margherita » qui passerait de 1 à 5 margherita reste rouge : l'effet de chaque geste est tenu."""
    from dataclasses import replace

    monde = await faire_monde("casa-italia")
    monkeypatch.setitem(C.GESTES, "G6", replace(C.GESTES["G6"], effet=C._plus(C.MARGHERITA, 4)))  # l'attente se trompe : elle dit 4 en plus, le code en met 1
    r = await C.jouer(monde, monkeypatch, "E7", ("G23+G6",))
    assert any(regle == "RC2" for _, regle, _ in r.fautes), r.fautes


def _fait_dit(texte):
    p: dict = {}
    J.dire_le_fait(p, texte, 1)
    return p


def test_rc4_la_phrase_dite_doit_etre_celle_du_fait_accompli_vu_rouge():
    annulee = dict(avant={"annulee": False}, apres={"annulee": True, **_fait_dit("Je ne l'enregistre pas.")})
    assert C.rc4(_observation(**annulee, textes={"avant": "Voulez-vous autre chose ?"})), "n'importe quelle phrase du code ne dit pas l'annulation"
    assert C.rc4(_observation(**annulee, textes={})), "aucune phrase : faute"
    assert C.rc4(_observation(**{**annulee, "apres": {"annulee": True, **_fait_dit("autre")}}, textes={"avant": "Je ne l'enregistre pas."})), "phrase non gardée comme fait dit"
    assert not C.rc4(_observation(**annulee, textes={"avant": "Je ne l'enregistre pas."}))
    enregistree = dict(avant={}, apres={"enregistree": {"numero": "n1", "total": 1200}, **_fait_dit("Votre commande est enregistrée.")})
    assert C.rc4(_observation(**enregistree, textes={"avant": "Je vous relis : une margherita."})), "la relecture n'est pas l'enregistrement"
    assert not C.rc4(_observation(**enregistree, textes={"avant": "Votre commande est enregistrée."}))


def test_rc10_la_relecture_doit_etre_dite_dans_le_tour_ou_elle_est_marquee_vu_rouge():
    relue = dict(avant={"relecture": None}, apres={"relecture": {"jeton": "j1"}, "question": {"type": "relecture", "texte": "Je vous relis : une margherita. Cela fait douze euros. C'est bon ?"}})
    assert C.rc10(None, _observation(**relue, textes={"avant": "Voulez-vous autre chose ?"})), "relecture marquée, pas dite dans ce tour"
    assert not C.rc10(None, _observation(**relue, textes={"avant": relue["apres"]["question"]["texte"]}))


async def test_la_base_falsifiee_est_vue_rouge(faire_monde, monkeypatch):
    """Une commande fausse en caisse ne reste pas verte parce que le panier en mémoire est juste : une ligne changée à la main en base est vue (resto_commande_ligne),
    comme ce que la prise a reçu."""
    monde = await faire_monde("casa-italia")
    partie = C.Partie(monde, monkeypatch)
    assert await partie.recette("E16")
    o = await partie.geste("G30")  # une fiche vide : rien ne change
    assert o.base is not None and o.prise is not None, "la commande est lue en base et dans la prise"
    assert not [x for x in C.juger(partie, o) if x[0] == "BASE"]
    await monde.c.execute("UPDATE mark.resto_commande_ligne SET quantite = quantite + 1 WHERE numero = $1::uuid", o.base["numero"])
    await monde.c.execute("UPDATE mark.resto_commande SET total = total + 100 WHERE numero = $1::uuid", o.base["numero"])
    o = await partie.geste("G30")
    fautes = [x for x in C.juger(partie, o) if x[0] == "BASE"]
    assert len(fautes) >= 2, fautes
    partie.e.source.prise.recues[-1]["total"] += 1
    o = await partie.geste("G30")
    assert any("la prise a reçu" in d for r, d in C.juger(partie, o) if r == "BASE")


def test_le_rapport_compte_les_cas_joues_a_part_des_non_applicables():
    a = C.Resultat("E0", ("G7",), True, joues=1)
    b = C.Resultat("E0", ("G12",), True, non_applicables=1)
    r = C.rapport([a, b], "x")
    assert (r["cas_joues"], r["cas_non_applicables"], r["gestes_joues"], r["gestes_non_applicables"]) == (1, 1, 1, 1)


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
    assert resultats[0].atteint, f"{etat} non atteint"
    assert not _lignes(resultats), "\n".join(_lignes(resultats)[:60])


@pytest.mark.combinaisons_longues
@pytest.mark.parametrize("etat", C.ETATS)
async def test_fusions_de_deux(faire_monde, monkeypatch, etat):
    monde = await faire_monde("casa-italia")
    codes = [g.code for g in C.FUSIONNABLES]
    resultats = [await C.jouer(monde, monkeypatch, etat, (f"{a}+{b}",)) for i, a in enumerate(codes) for b in codes[i + 1:]]
    _ecrire(f"fusions-{etat}", C.rapport(resultats, f"deux gestes fusionnés depuis {etat}"))
    assert resultats[0].atteint, f"{etat} non atteint"
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

"""[.mark] Chantier Partie 1, lot 19 bis, étape C : les lourds de l'audit de Pierre (ce que l'appelant entend), un test vu rouge chacun.

Allergie (A2), vente par lot (C4), poids en lettres (C5), parole (P3, P5), numéro affiché (C7), partage du règlement (C2 bis), réservation (C6 bis), essai hors Labo (T5 bis).
Tests sur la vraie porte et le vrai moteur (``essai_de``).
"""

from __future__ import annotations

from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, fait  # noqa: F401


# --------------------------------------------------------------------------- A2


async def test_article_ajoute_apres_l_allergie_reverifie(essai_de):
    """A2 : allergie au lait dite avec une salade au panier (faits donnés), puis « ajoutez une pizza reine » (lait validé) : les faits de CETTE ligne sont redonnés (``present``),
    l'enregistrement est bloqué ce tour-là (source : ``allergie_donnee`` ne comparait que le texte de l'allergie, jamais le panier) ; un article sans le lait ne rebloque rien."""
    carte = carte_de("briques/INF1")
    for p in carte["produits"]:
        if p["id"] == "P-REINE":
            p["allergenes"] = ["lait", "gluten"]
        if p["id"] == "P-SALADE":
            p["allergenes"] = ["gluten"]
    e = await essai_de("briques/INF1", carte=carte)
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salade", ajouter=[{"article": "salade verte", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "lait"
    premier = await e.tour("je suis allergique au lait", note_generale="allergique au lait")
    assert premier["faits"]["allergie"]["articles"] == [{"article": "Salade verte", "etat": "absent_de_la_fiche"}], premier
    suivant = await e.tour("et la salade ?", note_generale="allergique au lait")
    assert "allergie" not in (suivant.get("faits") or {})  # donnés une fois
    r = await e.tour("ajoutez une pizza reine", ajouter=[{"article": "pizza reine", "quantite": 1}], note_generale="allergique au lait")
    redonnes = (r.get("faits") or {}).get("allergie") or {}
    assert redonnes.get("articles") == [{"article": "Pizza reine", "etat": "present"}], r  # SES faits, pas ceux de la salade
    # le « oui » du même tour ne vaut pas : le tour suivant seulement
    assert not e.p.get("enregistree")


async def _jusqu_a_la_relecture(e) -> dict:
    """Mène la commande jusqu'à sa relecture posée (refuse ce que le code propose en route) et rend la question."""
    for _ in range(4):
        q = e.p.get("question") or {}
        if q.get("type") == "relecture":
            return q
        await e.tour("c'est tout", c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("id") else {}))
    q = e.p.get("question") or {}
    assert q.get("type") == "relecture", e.retours[-1]
    return q


# --------------------------------------------------------------------------- C4


async def test_correction_de_quantite_d_un_lot_en_pieces(essai_de):
    """C4 : un article vendu par lot de 6 (maki) : « douze maki » = 2 lots, DIT et MONTRÉ en pièces (état, relecture) ; « non, douze ! » (``changer_quantite``) reste 12 pièces = 2 lots, jamais 12 lots
    (source : ``modifier`` posait la quantité dite sans passer par QTE2) ; 24 pièces = 4 lots passe (source : le plafond de 20 était testé avant la conversion en lots, à la fiche et à l'ajout) ;
    hors multiple : refus avec les voisins."""
    from api.services.commande import etat_pour_le_modele as etat
    from api.services.commande import panier as P

    e = await brique(essai_de, "QTE2")
    await e.tour("douze maki", ajouter=[{"article": "maki", "quantite": 12}])
    n = e.p["lignes"][-1]["n"]
    assert e.p["lignes"][-1]["quantite"] == 2 and P.pieces(e.p["lignes"][-1]) == 12
    assert "12 × Maki" in (etat.texte(e.fiche_de_l_appel) or ""), etat.texte(e.fiche_de_l_appel)  # l'état dit des pièces, jamais « 2 × »
    await e.tour("non, douze !", changer_quantite=[{"ligne": n, "quantite": 12}])
    assert e.p["lignes"][-1]["quantite"] == 2, e.p["lignes"]  # avant : 12 lots (72 pièces, 72 €)
    await e.tour("vingt-quatre", changer_quantite=[{"ligne": n, "quantite": 24}])
    assert e.p["lignes"][-1]["quantite"] == 4, e.p["lignes"]  # avant : refusé, le plafond de 20 était testé sur les pièces
    r = await e.tour("sept", changer_quantite=[{"ligne": n, "quantite": 7}])
    assert "multiple_du_lot" in fait(r) and e.p["lignes"][-1]["quantite"] == 4, r
    q = await _jusqu_a_la_relecture(e)
    assert "vingt-quatre Maki" in q["texte"], q  # la relecture dit les pièces


# --------------------------------------------------------------------------- C5


def test_poids_en_lettres():
    """C5 : les cinq phrases de l'audit (avant : 500 g, 100,2 kg, 300 kg, 3 kg, 300 g), lues par le lecteur de nombres commun (``forme``) : « kilo + reste », « et demi », fractions, « N x M g » ;
    ce qui reste ambigu est refusé (``None``), jamais deviné."""
    from api.services.commande.briques.qte1 import lire_poids

    assert lire_poids("un kilo et demi") == 1500
    assert lire_poids("mille deux cents grammes") == 1200
    assert lire_poids("un kilo deux cents") == 1200
    assert lire_poids("trois quarts de kilo") == 750
    assert lire_poids("2 x 300 g") == 600
    assert lire_poids("deux kilos et demi") == 2500 and lire_poids("un quart de kilo") == 250 and lire_poids("quatre-vingt-dix grammes") == 90
    assert lire_poids("1 kg 2") is None and lire_poids("kilo") is None and lire_poids("un kilo des") is None


async def test_poids_au_dessus_du_maximum_redemande(essai_de):
    """C5 : un poids au-delà du maximum d'un article (cent kilos de houmous : 900 €) n'est jamais pris : refus ``poids_au_dessus_du_maximum`` avec le maximum, la question reste au modèle."""
    from api.services.commande import contrat

    e = await brique(essai_de, "QTE1")
    e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = (await e.source.charger_pour_l_appel())[1]  # la sous-case ``poids`` existe sur une carte qui vend au poids
    r = await e.tour("cent kilos de houmous", ajouter=[{"article": "houmous", "quantite": 1, "poids": "cent kilos"}])
    assert "poids_au_dessus_du_maximum" in fait(r) and not e.p["lignes"], r
    r = await e.tour("un kilo et demi de houmous", ajouter=[{"article": "houmous", "quantite": 1, "poids": "un kilo et demi"}])
    assert e.p["lignes"][-1]["poids_g"] == 1500, r


# --------------------------------------------------------------------------- P3


def _gestionnaire_de(action: str, fiche: dict, monkeypatch, rendus: list, dits: list):
    """Le vrai gestionnaire d'outil d'un connecteur interne (``outil.creer_gestionnaire``) pour ``action``, la lecture et la fiche partageant la fiche de l'appel ; l'exécution de l'action est rendue par
    la porte du métier (doublée ici : seule l'arrivée des résultats est jouée)."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from api.services.integrations.connectors import outil
    from api.services.integrations.connectors.execution import Resultat as ResultatDeLAction

    async def executer(*a, **k):
        return ResultatDeLAction(statut="ok", donnees={"faits": {"allergenes": []}}, duree_ms=1, message="")

    class Patience:
        def __init__(self, *a, **k): ...
        def demarrer(self): ...
        def arreter(self): ...

    monkeypatch.setattr(outil, "executer", executer)
    monkeypatch.setattr(outil, "resoudre", AsyncMock(return_value=({}, [])))
    monkeypatch.setattr(outil, "Patience", Patience)
    engine = SimpleNamespace(_gathered_context=fiche, _call_context_vars={}, _workflow_run_id=1, greffier=None,
                             queue_text_message=AsyncMock(side_effect=lambda t, **k: dits.append(t)))
    manager = SimpleNamespace(_engine=engine, _agent=None, get_organization_id=AsyncMock(return_value=1))
    tool = SimpleNamespace(name=action, definition={"config": {"connecteur": "commande", "action": action}})
    gestionnaire = outil.creer_gestionnaire(manager, tool, action)

    async def jouer(**arguments):
        async def rappel(resultat, *, properties=None):
            rendus.append((action, getattr(properties, "run_llm", None)))

        await gestionnaire(SimpleNamespace(arguments=arguments, tool_call_id=action, result_callback=rappel))

    return jouer


async def _lire_et_fiche(ordre: tuple[str, str], monkeypatch) -> tuple[list, list]:
    fiche = {"tour_de_la_personne": 4}
    rendus: list = []
    dits: list = []
    lire = _gestionnaire_de("lire", fiche, monkeypatch, rendus, dits)
    ecrire = _gestionnaire_de("fiche", fiche, monkeypatch, rendus, dits)
    jouer = {"lire": lambda: lire(sujet="allergenes", article="Regina"), "fiche": lambda: ecrire(ajouter=[{"article": "regina", "quantite": 1}], a_dire="Je regarde.")}
    for qui in ordre:
        await jouer[qui]()
    return rendus, dits


async def test_lire_et_fiche_meme_tour_reponse_dite(monkeypatch):
    """P3 : « une Regina, il y a des noix dedans ? » = une fiche (avec « Je regarde. ») et une lecture dans le même tour. Pipecat ne relance le modèle qu'au dernier résultat du groupe : la fiche dite seule
    (``run_llm`` faux) arrivant APRÈS la lecture ne relançait personne et la réponse à la question n'était jamais dite (source : la décision de la fiche ignorait la lecture du même tour).
    Les deux ordres d'arrivée : la fiche qui suit une lecture du même tour laisse la relance ; la fiche qui précède la lecture reste dite seule (la lecture relance, dernière du groupe)."""
    rendus, dits = await _lire_et_fiche(("lire", "fiche"), monkeypatch)
    assert dits == ["Je regarde."], dits
    assert dict(rendus)["fiche"] is not False, rendus  # lire d'abord : la fiche ne coupe pas la relance
    rendus, dits = await _lire_et_fiche(("fiche", "lire"), monkeypatch)
    assert dits == ["Je regarde."] and dict(rendus)["fiche"] is False and dict(rendus)["lire"] is not False, (rendus, dits)  # fiche d'abord : dite seule, la lecture relance


def test_lecture_deja_recue_par_le_modele_ne_relance_pas():
    """P3 : une lecture que le modèle a déjà reçue (une requête est partie depuis) ne fait plus relancer : la fiche qui la suit à un autre passage reste dite seule (sinon deux phrases)."""
    from api.services.actions_communes.parole import la_fiche_laisse_la_relance, la_lecture_est_vue, noter_la_lecture_rendue

    fiche = {"tour_de_la_personne": 4}
    assert not la_fiche_laisse_la_relance(fiche)
    noter_la_lecture_rendue(fiche)
    assert la_fiche_laisse_la_relance(fiche)
    la_lecture_est_vue(fiche)
    assert not la_fiche_laisse_la_relance(fiche)


# --------------------------------------------------------------------------- P5


async def test_fiche_illisible_jamais_muette(essai_de):
    """P5 : une fiche aux arguments JSON illisibles : Pipecat jette l'appel et le tour reste muet (le filet ne couvrait que les passations). Le filet couvre aussi l'outil de fiche d'un connecteur : l'appel
    arrive avec la marque ``arguments_illisibles``, la porte le refuse (``arguments_illisibles``, rien n'est changé, c'est un refus de LA FICHE : le modèle repasse, puis le repli du code)."""
    from api.services.pipecat.reponse_avalee import ArgumentsLisibles, noter_un_outil_de_fiche
    from api.tests.mark.test_correctifs_passations import ILLISIBLE, _FluxSimple, _appel, _comme_pipecat, _morceau

    flux = [_appel(0, "commande", ILLISIBLE[0], "t1"), _appel(0, None, ILLISIBLE[1]), _morceau(fin="tool_calls")]
    assert _comme_pipecat(flux) == []  # sans le filet : jeté, tour muet
    service = type("Service", (), {})()
    noter_un_outil_de_fiche(service, "commande")
    corrige = [m async for m in ArgumentsLisibles(_FluxSimple(flux), lambda: set(), lambda: getattr(service, "mark_noms_des_fiches", set()))]
    (nom, arguments), = _comme_pipecat(corrige)
    assert nom == "commande" and arguments == {"arguments_illisibles": True}, (nom, arguments)
    e = await brique(essai_de, "INF1")
    r = await e.fiche(**arguments)
    assert r["statut"] == "REJETEE" and r["raison"] == "arguments_illisibles" and e.p["lignes"] == [], r

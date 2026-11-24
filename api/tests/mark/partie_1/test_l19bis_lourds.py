"""[.mark] Chantier Partie 1, lot 19 bis, étape C : les lourds de l'audit de Pierre (ce que l'appelant entend), un test vu rouge chacun.

Allergie (A2), vente par lot (C4), poids en lettres (C5), parole (P3, P5), numéro affiché (C7), partage du règlement (C2 bis), réservation (C6 bis), essai hors Labo (T5 bis).
Tests sur la vraie porte et le vrai moteur (``essai_de``).
"""

from __future__ import annotations

from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, fait, oui_au_numero_dicte  # noqa: F401


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
    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    # lot 7a (ligne 64) : les faits ne sont notés donnés qu'une fois la parole décidée (en production, après chaque fiche) : le modèle repasse avec eux
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, premier, {"a_dire": "La salade n'en contient pas."}).mode != PAROLE.A_DIRE_SEUL
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
    from api.services.commande.briques.produit_au_poids import lire_poids

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


# --------------------------------------------------------------------------- C7


async def _jusqu_a_la_question_du_numero(e) -> dict:
    """Une commande d'un article menée jusqu'à la question du numéro qui s'affiche (« oui, par carte » à la relecture : un seul `finaliser`)."""
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    await e.tour("oui, par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    q = e.p.get("question") or {}
    assert q.get("type") == "numero_affiche" and not e.p.get("enregistree"), (q, e.retours[-1])
    return q


async def test_numero_affiche_jamais_valide_sans_reponse(essai_de):
    """C7 : « oui + moyen » dans une même fiche appelait `finaliser` deux fois : le premier posait la question du numéro qui s'affiche, le second (`confirmer`) la validait aussitôt, et n'importe quelle fiche
    de fin avait le même effet (« non, pas ce numéro. Léa » enregistrait avec le numéro affiché). Maintenant : un seul `finaliser` par fiche ; la question du numéro est numérotée (`numero_affiche`), seule
    sa réponse la cite (`reponse`) et la valide ; une fiche qui ne la cite pas est refusée ; « non » demande le numéro à noter."""
    e = await brique(essai_de, "INF6")
    q = await _jusqu_a_la_question_du_numero(e)
    e.dit("Léa")  # sans l'aide qui répond aux questions à la place du modèle
    r = await e.fiche(prenom="Léa")  # la question attend sa réponse
    # B1 : une fiche sans réponse vaut « autre » pour la question posée : le prénom est pris, le numéro qui s'affiche n'est JAMAIS gardé sans sa réponse,
    # la question reste posée (avant : la fiche entière refusée)
    assert not e.p.get("enregistree") and (e.p.get("question") or {}).get("id") == q["id"] and e.p["client"].get("prenom") == "Léa", r
    r = await e.tour("non, pas ce numéro. Léa", reponse={"question_id": q["id"], "sens": "refuse"}, prenom="Léa")
    assert not e.p.get("enregistree") and "telephone" in fait(r), r  # le numéro à noter est redemandé
    await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
    assert not e.p.get("enregistree") and e.p["question"]["type"] == "numero_dicte"  # DC10 : le numéro dicté est relu, il attend son « oui »
    await oui_au_numero_dicte(e)
    assert e.p.get("enregistree") and e.p["client"]["telephone"].endswith("612345678"), e.retours[-1]


async def test_numero_affiche_accepte_enregistre_avec_ce_numero(essai_de):
    """C7 : la réponse « accepte » à la question du numéro qui s'affiche le garde ; le prénom ensuite enregistre."""
    e = await brique(essai_de, "INF6")
    q = await _jusqu_a_la_question_du_numero(e)
    await e.tour("oui, c'est bon, Léa", reponse={"question_id": q["id"], "sens": "accepte"}, prenom="Léa")
    assert e.p.get("enregistree") and e.p["client"]["telephone"] == "+33600000000", e.retours[-1]


# --------------------------------------------------------------------------- C6 bis


from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation  # noqa: E402
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: E402,F401
from api.tests.mark.test_restauration_reservation import salle  # noqa: E402,F401


async def test_refus_d_une_case_reservation_ne_fait_pas_refaire_le_reste(salle, monkeypatch):
    """C6 bis : même défaut que C6 pour la réservation (source : ``a_faire`` du premier refus, « rien n'est changé : refais la fiche sans nom », alors que ``personnes`` et ``jour`` de la même fiche sont pris) :
    le retour nomme la case refusée (un nom qu'elle n'a pas dit) et dit que le reste est fait."""
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("quatre personnes samedi", personnes=4, jour="samedi", nom="Zorglub")
    assert "nom" in r["cases_refusees"] and "valeurs" in r["cases_executees"], r
    assert essai.etat["brouillon"]["personnes"] == 4 and essai.etat["brouillon"]["jour"] == "samedi", essai.etat
    assert "rien n'est changé : refais la fiche sans" not in r["a_faire"], r["a_faire"]
    assert "nom" in r["a_faire"] and "déjà fait" in r["a_faire"], r["a_faire"]


# --------------------------------------------------------------------------- C2 bis


async def test_partage_du_reglement_par_la_fiche(essai_de):
    """C2 bis (décision d'Evan : partage ouvert) : `part` et `moyen_reste` sont des cases de la fiche, ouvertes avec le récapitulatif comme le moyen de paiement ; « cinq euros par carte et le reste en espèces » :
    la part (dite en argent, sinon refusée avec son moyen) et le moyen du reste arrivent jusqu'au règlement ; la commande s'enregistre."""
    from api.services.commande import contrat

    e = await brique(essai_de, "INF6")
    assert not {"part", "moyen_reste"} & set(e.montrer())  # fermées avant le récapitulatif, comme le moyen
    await e.tour("un gâteau", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    q = await _jusqu_a_la_relecture(e)
    assert {"part", "moyen_reste"} <= set(e.montrer()) and {"part", "moyen_reste"} <= set(contrat.CASES_DE_FIN)
    r = await e.tour("oui, neuf euros par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire", part=2, moyen_reste="especes")
    assert "part" in r.get("cases_refusees", []) and not (e.p.get("paiement") or {}).get("part"), r  # une part qu'elle n'a pas dite est refusée, avec son moyen (cases liées)
    q = e.p.get("question") or {}
    if q.get("type") == "relecture":
        await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    await e.tour("trois euros par carte et le reste en espèces", moyen_de_paiement="carte_bancaire", part=3, moyen_reste="especes")
    assert e.p["paiement"]["part"] == 300 and e.p["paiement"]["moyen_reste"] == "especes" and e.p["paiement"]["moyen"] == "carte", e.p.get("paiement")
    q = e.p.get("question") or {}
    if q.get("type") == "numero_affiche":
        await e.tour("oui, ce numéro, Léa", reponse={"question_id": q["id"], "sens": "accepte"}, prenom="Léa")
    assert e.p.get("enregistree"), e.retours[-1]

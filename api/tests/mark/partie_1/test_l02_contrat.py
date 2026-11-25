"""[.mark] Chantier Partie 1, lot 2 : le contrat (forme de la fiche seulement, D48).

La référence est le rendu de la version finale, versé dans le fork par ``verser_textes.py`` (``gabarits/restauration/textes/gemma-4/outils.json`` :
les outils envoyés au modèle par le banc dans chaque état type, et la vue de l'état du banc). Le fork rend la fiche par SON mécanisme
(``Parametre`` → ``outil._propriete`` → ``cases_selon_l_etat``) à partir de la même vue : les deux doivent être égaux.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.gabarits.restauration.textes import banc as B

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.services.actions_communes import enveloppe as EN
from api.services.commande import contrat as K
from api.services.commande import panier as P
from api.services.gabarits.restauration import textes as T
from api.services.integrations.connectors.actions.commande import COMMANDE
from api.services.integrations.connectors.catalogue import Parametre
from api.services.integrations.connectors.outil import _propriete
from api.services.workflow import cases_selon_l_etat as CS
from api.tests.mark.banc_a.commun import appel_de, base_essai, base_prete, faire_monde  # noqa: F401

CARTES = ("300", "300b", "305f", "307b", "307c")
API = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- aides


def _fiche_du_banc(outils):
    return next(o["function"] for o in outils if o["function"]["name"] == "fiche")


def _normal(x):
    """Même forme : l'ordre des clés ne compte pas, l'ordre des listes requises non plus ; l'ordre d'une liste fermée compte."""
    if isinstance(x, dict):
        return {k: (sorted(v) if k == "required" else _normal(v)) for k, v in x.items()}
    if isinstance(x, list):
        return [_normal(v) for v in x]
    return x


def _contexte_de_la_carte(carte):
    """Les listes fermées du décroché, telles que la version finale les montre sur cette carte."""
    ctx = {}
    for e in B.rendus()["cartes"][carte]:
        if e["etape"] != "commande":
            continue
        pr = _fiche_du_banc(e["outils"])["parameters"]["properties"]
        if "enum" in pr.get("mode_de_retrait", {}):
            ctx[K.LISTE_DES_MODES] = pr["mode_de_retrait"]["enum"]
        if "enum" in pr.get("moyen_de_paiement", {}):
            ctx[K.LISTE_DES_MOYENS] = pr["moyen_de_paiement"]["enum"]
        v = pr.get("ajouter", {}).get("items", {}).get("properties", {}).get("variante", {})
        if "enum" in v:
            ctx[K.LISTE_DES_VARIANTES] = v["enum"]
    return ctx


def _rendu_du_fork(vue: K.VueDeLaCommande, contexte: dict) -> tuple[dict, list]:
    action = COMMANDE.action("fiche")
    proprietes = {p.nom: _propriete(p, contexte) for p in action.parametres}
    requis = [p.nom for p in action.parametres if p.obligatoire]
    return CS.schema_selon_l_etat(proprietes, requis, K.cases_visibles_de_la_vue(vue), K.forme_de_la_vue(vue))


def _etats_de_commande():
    for carte in CARTES:
        for e in B.rendus()["cartes"][carte]:
            if e["etape"] == "commande":
                yield carte, e


def _vue(**k):
    base = {"objets_de_la_carte": {"choix": True, "poids": False, "personnes": False, "code_de_remise": False}}
    return K.VueDeLaCommande.depuis_un_dict({**base, **k})


def _fiche_du_fork(vue, contexte=None):
    proprietes, requis = _rendu_du_fork(vue, contexte or {})
    return proprietes, requis


# --------------------------------------------------------------------------- 1. paramètres typés et schéma égal au banc


def test_parametre_liste_d_objets():
    p = Parametre(
        "lignes", type="array", description="Des lignes.", obligatoire=False,
        elements=Parametre("", type="object", proprietes=(Parametre("ligne", type="integer", minimum=1), Parametre("texte")), obligatoires=("ligne",)),
        min_elements=1,
    )
    assert _propriete(p, None) == {
        "type": "array", "description": "Des lignes.", "minItems": 1,
        "items": {"type": "object", "properties": {"ligne": {"type": "integer", "minimum": 1}, "texte": {"type": "string"}}, "required": ["ligne"]},
    }
    with pytest.raises(ValueError):
        Parametre("x", type="array")  # une liste déclare ses éléments
    with pytest.raises(ValueError):
        Parametre("x", type="liste")
    # un connecteur d'avant rend le même schéma
    assert _propriete(Parametre("mode", description="Le mode.", choix=("a", "b")), None) == {"type": "string", "description": "Le mode.", "enum": ["a", "b"]}


@pytest.mark.parametrize("carte", CARTES)
def test_schema_fiche_identique_au_banc(carte):
    contexte = _contexte_de_la_carte(carte)
    for c, e in _etats_de_commande():
        if c != carte:
            continue
        banc = _fiche_du_banc(e["outils"])["parameters"]
        proprietes, requis = _rendu_du_fork(K.VueDeLaCommande.depuis_un_dict(e["vue"]), contexte)
        assert _normal(proprietes) == _normal(banc["properties"]), f"{carte} / {e['etat']} : {sorted(set(proprietes) ^ set(banc['properties']))}"
        assert sorted(requis) == sorted(banc.get("required") or []), (carte, e["etat"], requis, banc.get("required"))
    assert COMMANDE.action("fiche").description == _fiche_du_banc(B.rendu("commande", "vide"))["description"]


def test_toutes_les_cases_facultatives_sauf_a_dire():
    _, requis = _fiche_du_fork(_vue(mode="livraison", lignes=1))
    assert requis == ["a_dire"]
    assert [p.nom for p in COMMANDE.action("fiche").parametres if p.obligatoire] == ["a_dire"]


def test_reponse_obligatoire_quand_question():
    proprietes, requis = _fiche_du_fork(_vue(lignes=1, question={"type": "proposition", "posee": True}))
    assert "reponse" in proprietes and requis[0] == "reponse" and "Obligatoire" in proprietes["reponse"]["description"]
    proprietes, requis = _fiche_du_fork(_vue(lignes=1, question={"type": "proposition", "posee": False}))
    assert "reponse" not in proprietes and requis == ["a_dire"]  # une question née dans ce tour : sa réponse est sans objet


def test_reponse_absente_sans_question():
    proprietes, _ = _fiche_du_fork(_vue(lignes=1))
    assert "reponse" not in proprietes


def test_mode_liste_fermee_avec_autre():
    listes = K.listes_du_contexte(["emporter", "livraison"], ["carte_bancaire", "especes"], ["Normale", "Mega"])
    proprietes, _ = _fiche_du_fork(_vue(), listes)
    assert proprietes["mode_de_retrait"]["enum"] == ["emporter", "livraison", "autre"]


def test_moyen_liste_fermee_avec_autre():
    listes = K.listes_du_contexte(["emporter"], ["carte_bancaire", "titre_restaurant"], [])
    proprietes, _ = _fiche_du_fork(_vue(lignes=1, question={"type": "relecture", "posee": True}), listes)
    assert proprietes["moyen_de_paiement"]["enum"] == ["carte_bancaire", "titre_restaurant", "autre"]


ETATS_DE_LA_VUE = [
    _vue(),
    _vue(mode="livraison"),
    _vue(lignes=2, question={"type": "proposition", "posee": True}),
    _vue(lignes=2),
    _vue(lignes=2, question={"type": "relecture", "posee": True}),
    _vue(lignes=2, relecture_acceptee=True, moyen="especes"),
    _vue(lignes=2, relecture_acceptee=True, enregistree=True),
    _vue(lignes=2, relecture_acceptee=True, annulee=True),
    _vue(lignes=1, question={"type": "etape", "posee": True}, ligne_de_formule=True),
]


def test_quatre_annulations_jamais_ensemble():
    # Sur les états de la version finale (21 avec la réservation, la réservation est au lot 7) et ceux de la vue : jamais deux annulations d'un objet.
    vues = [K.VueDeLaCommande.depuis_un_dict(e["vue"]) for _, e in _etats_de_commande()] + ETATS_DE_LA_VUE
    for vue in vues:
        proprietes, _ = _fiche_du_fork(vue)
        assert not {"annuler_la_commande", "annuler_une_commande_enregistree"} <= set(proprietes), vue
    assert "annuler_la_commande" in _fiche_du_fork(_vue(mode="livraison"))[0]
    assert "annuler_une_commande_enregistree" in _fiche_du_fork(_vue(lignes=1, enregistree=True, relecture_acceptee=True))[0]


def test_cases_de_fin_cachees_avant_recapitulatif():
    proprietes, _ = _fiche_du_fork(_vue(lignes=2))
    assert not set(K.CASES_DE_FIN) & set(proprietes)
    proprietes, _ = _fiche_du_fork(_vue(lignes=2, question={"type": "relecture", "posee": True}))
    assert set(K.CASES_DE_FIN) <= set(proprietes)
    proprietes, _ = _fiche_du_fork(_vue(lignes=2, relecture_acceptee=True, moyen="carte_bancaire"))
    assert {"moyen_de_paiement", "telephone", "prenom"} <= set(proprietes) and "rendu_sur" not in proprietes


def test_question_d_etape_sans_sens():
    proprietes, requis = _fiche_du_fork(_vue(lignes=1, question={"type": "etape", "posee": True}))
    r = proprietes["reponse"]
    assert "sens" not in r["properties"] and sorted(r["required"]) == ["question_id", "valeurs"]
    assert r["properties"]["valeurs"]["description"] == T.variantes()["reponse.valeurs.etape"] == "Son choix pour cette étape, avec ses mots."


def test_cases_des_briques_selon_la_carte():
    sans = _vue(lignes=1, objets_de_la_carte={})
    proprietes, _ = _fiche_du_fork(sans)
    articles = proprietes["ajouter"]["items"]["properties"]
    assert not {"composition", "poids", "personnes"} & set(articles)
    assert not {"code_de_remise", "reduction_annoncee"} & set(proprietes)
    assert "composition" not in proprietes["changer_quantite"]["items"]["properties"]
    tout = _vue(lignes=1, objets_de_la_carte={"choix": True, "poids": True, "personnes": True, "code_de_remise": True})
    proprietes, _ = _fiche_du_fork(tout)
    assert {"composition", "poids", "personnes"} <= set(proprietes["ajouter"]["items"]["properties"]) and {"code_de_remise", "reduction_annoncee"} <= set(proprietes)


def test_composition_d_un_changement_seulement_le_choix():
    proprietes, _ = _fiche_du_fork(_vue(lignes=1, ligne_de_formule=True))
    assert proprietes["changer_quantite"]["items"]["properties"]["composition"]["description"] == T.variantes()["changer_quantite[].composition.ligne_de_formule"]


def test_sans_formule_schema_identique():
    proprietes, _ = _fiche_du_fork(_vue(lignes=1))
    banc = _fiche_du_banc(B.rendu("commande", "lignes sans question"))["parameters"]["properties"]
    assert _normal(proprietes["changer_quantite"]["items"]["properties"]["composition"]) == _normal(banc["changer_quantite"]["items"]["properties"]["composition"])


def test_lire_n_ecrit_jamais():
    # Le contrat : une lecture n'a aucune case qui écrive, et elle s'exécute sur une copie du panier (E16, A26).
    from api.services.commande.lire import lecture_sur_une_copie

    lire = COMMANDE.action("lire")
    assert not lire.ecrit and [p.nom for p in lire.parametres if p.obligatoire] == ["sujet"]
    assert "vider" not in {p.nom for p in lire.parametres}
    p = P.nouveau()
    p["lignes"].append({"n": 1, "nom": "x", "quantite": 1, "choix": [], "retires": []})
    copie = lecture_sur_une_copie(p)
    copie["lignes"].clear()
    copie["mentions_de_remise"] = 9
    assert p["lignes"] and p["mentions_de_remise"] == 0


async def test_lire_n_ecrit_jamais_sur_la_vraie_source(appel_de):
    from api.services.commande import moteur
    from api.services.commande.lire import lire

    a = await appel_de("casa-italia")
    # le panier est rempli par l'écriture de la cuisine que la fiche appelle (lot 4 : ``ajouter_un_article``, la case ``ajouter``)
    await moteur.choisir_mode(a.source, a.p, moteur.Reglages(), "emporter")
    pris = await moteur.ajouter_un_article(a.source, a.p, moteur.Reglages(), {"article": "margherita", "quantite": 1, "variante": "Normale"})
    assert pris.statut == "OK" and a.p["lignes"], pris
    avant = json.dumps(a.p, sort_keys=True, default=str)
    for sujet in ("panier", "offres", "delai", "article", "carte", "frais", "horaires", "autre"):
        r = await lire(a.source, a.p, moteur.Reglages(), {"sujet": sujet, "article": "margherita"})
        assert r["statut"] in EN.STATUTS
    assert json.dumps(a.p, sort_keys=True, default=str) == avant


# --------------------------------------------------------------------------- 2. l'enveloppe


def test_enveloppe_unique():
    e = EN.Enveloppe("FAIT", resultats=[{"operation": "ajouter"}], question=EN.Question("Q-1", "proposition", "proposer un Coca-Cola")).vers_json()
    assert set(e) <= set(EN.CLES) and e["statut"] == "FAIT" and e["question"]["reponses"] == ["accepte", "refuse", "autre"]
    with pytest.raises(EN.EnveloppeInvalide):
        EN.verifier({"statut": "OK"})
    with pytest.raises(EN.EnveloppeInvalide):
        EN.verifier({"statut": "FAIT", "suggestion": "Qu'est-ce que je vous mets ?"})


def test_retour_sans_phrase_du_code():
    # C6 n° 11 (décision d'Evan 25/11 9 h 30) : le drapeau du prix dit par le code n'existe plus, même à ``true`` (les prix sont des faits que le modèle dit)
    for faux in ({"statut": "FAIT", "prix_dit_par_le_code_apres_ta_phrase": True},
                 {"statut": "FAIT", "prix_dit_par_le_code_apres_ta_phrase": "Le Coca-Cola est à deux euros."},
                 {"statut": "FAIT", "faits": {"phrase_du_code": "Le minimum est de quinze euros."}}):
        with pytest.raises(EN.EnveloppeInvalide):
            EN.verifier(faux)


def _raisons_des_modules() -> set[str]:
    """Les raisons de refus écrites dans le code des modules de la fiche (commande, service, actions communes)."""
    fichiers = [*(API / "services" / "actions_communes").glob("*.py"), *(API / "services" / "commande" / n for n in ("porte.py", "lire.py", "contrat.py")),
                *(API / "services" / "integrations" / "connectors" / "actions" / n for n in ("commande.py", "service.py"))]
    raisons = set()
    for f in fichiers:
        if f.exists():
            texte = f.read_text(encoding="utf-8")
            raisons |= set(re.findall(r"""\braison(?:\s*=\s*|["']\s*:\s*)["']([a-z_]+)["']""", texte))
    return raisons


def test_chaque_raison_rangee_fiche_ou_metier():
    assert not EN.REFUS_DE_LA_FICHE & EN.RAISONS_DU_METIER
    non_rangees = {r for r in _raisons_des_modules() if EN.rangee(r) is None}
    assert non_rangees == set(), f"raisons non rangées « fiche » ou « métier » : {sorted(non_rangees)}"
    with pytest.raises(EN.EnveloppeInvalide):
        EN.verifier({"statut": "REJETEE", "raison": "raison_inventee_pour_l_epreuve"})  # R7 : une raison neuve non rangée fait échouer


def test_question_porte_un_identifiant():
    with pytest.raises(EN.EnveloppeInvalide):
        EN.Question("question-1", "relecture", "x")
    with pytest.raises(EN.EnveloppeInvalide):
        EN.verifier({"statut": "FAIT", "question": {"id": "Q-2", "type": "relecture", "texte": "x", "reponses": []}})
    EN.verifier({"statut": "FAIT", "question": {"id": "Q-2", "type": "relecture", "texte": "x", "reponses": ["accepte", "refuse", "autre"]}})


def test_cles_et_raisons_au_glossaire():
    from api.tests.mark.partie_1 import glossaire as GL

    manquent = [n for n in (*EN.CLES, *EN.STATUTS, *EN.REFUS_DE_LA_FICHE) if n not in GL.GLOSSAIRE]
    assert manquent == [], manquent


# --------------------------------------------------------------------------- 3. les cases montrées gardées dans le tour (D52)


class _Outil:
    def __init__(self, name, properties, required):
        self.name, self.description, self.properties, self.required = name, "d", properties, required


def _moteur(fiche):
    from api.services.workflow.etat_des_connecteurs import ATTRIBUT

    return SimpleNamespace(_gathered_context=fiche, **{ATTRIBUT: {"fiche": "commande"}})


def _contexte_de_requete():
    from pipecat.adapters.schemas.function_schema import FunctionSchema
    from pipecat.adapters.schemas.tools_schema import ToolsSchema
    from pipecat.processors.aggregators.llm_context import LLMContext

    action = COMMANDE.action("fiche")
    fs = FunctionSchema(name="fiche", description=action.description, properties={p.nom: _propriete(p, {}) for p in action.parametres}, required=["a_dire"])
    return LLMContext(messages=[{"role": "user", "content": "bonjour"}], tools=ToolsSchema(standard_tools=[fs]))


def test_cases_montrees_gardees_dans_le_tour():
    fiche = {K.CLE_DES_OBJETS: {"choix": True}}
    P.du_dossier(fiche)["mode"] = "livraison"
    moteur = _moteur(fiche)
    copie = CS.contexte_avec_les_cases_de_l_etat(moteur, _contexte_de_requete())
    envoye = copie.tools.standard_tools[0]
    montrees = fiche[CS.CLE_DES_CASES_MONTREES]["fiche"]
    assert montrees == CS.chemins_du_schema(envoye.properties) and "annuler_la_commande" in montrees and "reponse" not in montrees
    # l'état change après l'envoi : la liste gardée ne bouge pas
    P.du_dossier(fiche)["lignes"].append({"n": 1})
    assert fiche[CS.CLE_DES_CASES_MONTREES]["fiche"] == montrees


def test_erreur_des_cases_jamais_avalee(monkeypatch, caplog):
    from dataclasses import replace as remplacer

    from api.services.integrations.connectors import catalogue

    def casse(fiche):
        raise RuntimeError("état illisible")

    faux = remplacer(COMMANDE, cases_visibles=casse)
    monkeypatch.setattr(catalogue, "connecteur", lambda nom: faux if nom == "commande" else None)
    erreurs = []
    from loguru import logger

    jeton = logger.add(lambda m: erreurs.append(str(m)), level="ERROR")
    try:
        with pytest.raises(CS.CasesIllisibles):
            CS.contexte_avec_les_cases_de_l_etat(_moteur({}), _contexte_de_requete())
    finally:
        logger.remove(jeton)
    assert any("fiche" in e and "illisibles" in e for e in erreurs), erreurs


# --------------------------------------------------------------------------- 4. l'état injecté


def _etat(fiche):
    from api.services.commande.etat_pour_le_modele import texte

    return texte(fiche, {}) or ""


def _fiche_avec(**panier):
    fiche = {}
    p = P.du_dossier(fiche)
    CONV.poser_question(p, panier.pop("question", None))  # la question vit sous la conversation (G3)
    p.update(panier)
    return fiche


def test_etat_lignes_numerotees():
    fiche = _fiche_avec(mode="emporter", lignes=[{"n": 1, "nom": "Margherita Normale", "quantite": 2, "choix": [], "retires": []}],
                        question={"id": "Q-3", "type": "relecture", "texte": "C'est bon ?", "nee_au_tour": 0})
    t = _etat(fiche)
    assert "- Lignes : ligne 1 : 2 × Margherita Normale." in t, t
    # C6 n° 3b (décision d'Evan 25/11 9 h 30) : la relecture est dite par le modèle ; l'état la donne par son type, sans texte
    assert "- Question en attente : Q-3 (récapitulatif) ; réponses : accepte, refuse, autre." in t, t


def test_etat_rien_n_est_change_sans_fiche():
    ligne = "Rien n'est changé tant que tu n'as pas rempli la fiche."
    assert ligne not in _etat(_fiche_avec())
    assert ligne in _etat(_fiche_avec(mode="emporter"))
    assert ligne in _etat(_fiche_avec(question={"id": "Q-1", "type": "proposition", "texte": "proposer Coca-Cola", "article_propose": "Coca-Cola"}))


def test_etat_sans_repartirait_de_zero():
    fiche = _fiche_avec(mode="emporter", lignes=[{"n": 1, "nom": "Margherita", "quantite": 1, "choix": [], "retires": []}], enregistree={"numero_court": "T12"})
    t = _etat(fiche)
    # Le texte est celui de la version finale (``commande_b13.etat_texte_v6``, rendu versé), qui dit la case de chaque geste (ambiguïté 16).
    banc = next(e["etat_texte"] for e in B.rendus()["cartes"]["300"] if e["etat"] == "enregistrée").splitlines()[1]
    assert "repartirait de zéro" not in t and banc.replace("(numéro 28)", "(numéro T12)") in t, t


# --------------------------------------------------------------------------- 5. noms, textes, accueil, service


def test_descriptions_en_francais():
    anglais = re.compile(r"\b(the|she|her|his|order|item|empty|when|only|caller|said|words)\b", re.IGNORECASE)

    def textes(params):
        for p in params:
            yield p.description
            if p.elements:
                yield from textes((p.elements,))
            yield from textes(p.proprietes)

    from api.services.integrations.connectors.actions.service import SERVICE

    for c in (COMMANDE, SERVICE):
        for a in c.actions:
            for t in (a.description, *textes(a.parametres)):
                assert not anglais.search(t or ""), f"{c.nom}.{a.nom} : {t!r}"


def test_textes_gabarit_egaux_au_banc():
    versees = B.rendus()
    assert versees["source"].endswith("banc-b13") and versees["drapeaux"] == "accueil_sans_carte,heure_fidele,passer_a_premier"
    banc = API.parents[2] / "Labo-agent-vocal" / "plans" / "agent-fiable-une-passe" / "outils" / "banc-b13"
    if not banc.exists():
        pytest.skip("le labo n'est pas à côté du fork : empreintes non recalculées")
    for nom, empreinte in versees["empreintes"].items():
        assert hashlib.sha256((banc / nom).read_bytes()).hexdigest() == empreinte, f"{nom} a changé depuis le versement : relancer verser_textes.py"
    for etape in ("accueil", "accueil_repris", "commande", "reservation", "service"):
        assert B.prompt(etape).count("{{etat}}") == 1, etape


def test_passer_a_cible_fermee():
    passer = next(o["function"] for o in B.rendu("accueil", "accueil") if o["function"]["name"] == "passer_a")
    assert passer["parameters"]["properties"]["cible"]["enum"] == ["commande", "reservation", "service"]
    assert passer["parameters"]["properties"]["cible"]["description"] == "Le collègue de sa demande."
    assert passer["description"] == T.variantes()["passer_a"]


def test_accueil_sans_voir_produit():
    from api.services.gabarits.restauration.textes import outils_de_l_accueil

    from api.services.gabarits.restauration.textes import passage_en_tete

    noms = [o["function"]["name"] for o in outils_de_l_accueil()]
    assert "voir_produit" not in noms and noms[0] == "passer_a"  # B12 décision 3 ; B13 point 2 : le passage en tête, ordre fixé par le code
    melanges = [{"function": {"name": n}} for n in ("ouverture_en_ce_moment", "voir_produit", "passer_a", "fin")]
    assert [o["function"]["name"] for o in passage_en_tete(melanges)] == ["passer_a", "ouverture_en_ce_moment", "voir_produit", "fin"]
    p = B.prompt("accueil")
    assert "La carte, les prix, les compositions" not in p and "- Les offres, les délais et les places de la terrasse ne se savent que par les outils." in p


def test_service_fiche_schema():
    from api.services.integrations.connectors.actions.service import SERVICE

    banc = _fiche_du_banc(B.rendu("service", "service"))
    fiche = SERVICE.action("fiche")
    proprietes = {p.nom: _propriete(p, {}) for p in fiche.parametres}
    assert fiche.description == banc["description"]
    assert _normal(proprietes) == _normal(banc["parameters"]["properties"])
    assert [p.nom for p in fiche.parametres if p.obligatoire] == banc["parameters"]["required"]


def test_retrouver_par_telephone_dicte_exige_le_numero():
    from api.services.integrations.connectors.actions.service import retrouver_par_telephone_dicte_exige_le_numero as regle

    qui_appelle = "+33600000000"
    refus = regle({"retrouver_une_commande_enregistree": {"telephone": "06 12 34 56 78"}}, qui_appelle)
    assert refus is not None and refus["raison"] == "numero_de_commande_exige" and refus["question"]["id"].startswith("Q-")
    assert regle({"retrouver_une_commande_enregistree": {"telephone": "06 12 34 56 78", "numero_de_commande": "T12"}}, qui_appelle) is None
    assert regle({"retrouver_une_commande_enregistree": {}}, qui_appelle) is None  # le numéro qui appelle suffit seul
    assert regle({"retrouver_une_commande_enregistree": {"telephone": "06 00 00 00 00"}}, qui_appelle) is None  # c'est le numéro qui appelle

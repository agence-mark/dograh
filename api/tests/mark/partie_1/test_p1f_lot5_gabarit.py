"""[.mark] Plan final Partie 1, lot 5 (G, n° 142 à 148, 153) : le gabarit tient chaque donnée en UN endroit.

Avant : le contrat des outils servi aux vrais appels était un instantané du banc rangé par carte de test (310 Ko), les prompts existaient en 13 copies remplies et en
6 textes à trous, l'installation retrouvait le texte de chaque cible en découpant une description, la phrase d'urgence était écrite dans cinq textes. Règles : le contrat
est ``outils.json`` SANS carte ; les rendus du banc ne sont lus que par les tests ; le prompt d'une carte est RENDU depuis le texte à trous ; les textes de passage sont
dans ``gabarit.json`` ; une phrase citée par plusieurs textes est un trou constant ; le gabarit dit lui-même son étape principale et l'état de référence de chaque étape.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from api.services.gabarits import gabarit as G
from api.services.gabarits import installation as I
from api.services.gabarits.restauration import textes as TX
from api.services.gabarits.restauration.textes import banc as B

RACINE_SERVICES = Path(__file__).resolve().parents[3] / "services"
NOMS_DU_BANC = {"outils_verses", "rendu", "prompt", "requetes_types", "CARTE_TEMOIN"}
PROMPTS = ("accueil", "accueil_repris", "commande", "reservation", "service")
URGENCE = "En cas de malaise, appelez tout de suite le quinze ou le cent douze."


def test_le_contrat_des_outils_n_a_aucune_carte_de_test():
    """n° 143 : ``outils.json`` porte les étapes, leurs outils et les textes d'état ; aucune carte, aucune empreinte de script du banc, aucune valeur d'une carte."""
    c = TX.contrat()
    assert set(c) == {"variantes", "etapes"} and set(c["etapes"]) == set(G.charger().definition["etapes"])
    brut = json.dumps(c, ensure_ascii=False)
    assert '"cartes"' not in brut and "banc-b13" not in brut and "Normale" not in brut and "Mega" not in brut
    assert len(brut) < 60_000  # 310 Ko avant
    variante = TX.cases_de_la_fiche("commande")["ajouter"]["items"]["properties"]["variante"]
    assert "enum" not in variante  # la liste fermée est construite au décroché, jamais copiée d'une carte


def _lectures_du_banc(arbre: ast.AST) -> list[str]:
    """Ce qu'un module lit du banc : un import de ``textes.banc``, un ancien nom du banc importé de ``textes``, ou un appel PAR ATTRIBUT sur le module ``textes`` (``textes.rendu(...)``)."""
    trouves, alias = [], set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.ImportFrom):
            module = n.module or ""
            if module.endswith("restauration.textes.banc"):
                trouves.append("import banc")
            if module.endswith("gabarits.restauration.textes"):
                trouves += [a.name for a in n.names if a.name in NOMS_DU_BANC | {"banc"}]
            if module.endswith("gabarits.restauration"):
                alias |= {a.asname or a.name for a in n.names if a.name == "textes"}
        if isinstance(n, ast.Import):
            alias |= {a.asname for a in n.names if a.asname and a.name.endswith("restauration.textes")}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias and n.attr in NOMS_DU_BANC | {"banc"}:
            trouves.append(f"{n.value.id}.{n.attr}")
    return trouves


def test_aucun_module_du_fonctionnement_ne_lit_les_rendus_du_banc():
    """n° 143, règle : seuls les tests lisent ``textes.banc`` (``outils_verses``, ``rendu``, ``prompt``, ``requetes_types``, ``CARTE_TEMOIN``) ; ni par import, ni par attribut."""
    fautifs = {}
    for chemin in RACINE_SERVICES.rglob("*.py"):
        if "textes" in chemin.parts and chemin.name in ("banc.py", "__init__.py"):
            continue
        lectures = _lectures_du_banc(ast.parse(chemin.read_text(encoding="utf-8")))
        if lectures:
            fautifs[str(chemin)] = lectures
    assert fautifs == {}


def test_la_regle_voit_un_appel_par_attribut_comme_un_import():
    """Le détecteur n'est pas aveugle : les trois formes de lecture du banc sont vues (rouge si l'une cesse de l'être)."""
    assert _lectures_du_banc(ast.parse("from api.services.gabarits.restauration import textes\nx = textes.rendu('a', 'b')")) == ["textes.rendu"]
    assert _lectures_du_banc(ast.parse("from api.services.gabarits.restauration import textes as T\nT.outils_verses()")) == ["T.outils_verses"]
    assert _lectures_du_banc(ast.parse("from api.services.gabarits.restauration.textes import prompt")) == ["prompt"]
    assert _lectures_du_banc(ast.parse("from api.services.gabarits.restauration.textes import outil, variantes")) == []


def test_les_textes_de_passage_sont_dans_le_gabarit_et_dans_le_contrat():
    """n° 142 : ce que traite chaque collègue est écrit UNE fois dans ``gabarit.json`` ; la description de ``passer_a`` du contrat le cite, aucune découpe n'est faite à l'installation."""
    g = G.charger()
    assert set(g.passages) == set(g.definition["etapes"]) - {g.principal}
    passer = next(o["function"]["description"] for o in TX.outils_de(g.principal) if o["function"]["name"] == TX.OUTIL_DE_PASSAGE)
    for etape, phrase in g.passages.items():
        assert f" cible {etape} : {phrase}" in passer
    assert not hasattr(I, "_cibles_du_passage")


def test_le_gabarit_dit_son_etape_principale_et_l_etat_de_reference_de_chaque_etape():
    """n° 153 : l'installation lit ces deux choses dans le gabarit, plus de nom d'étape en dur."""
    g = G.charger()
    assert g.principal == "accueil" and all(d.get("etat_de_reference") for d in g.definition["etapes"].values())
    for etape in g.definition["etapes"]:
        assert TX.outils_de(etape)  # l'état de référence a ses outils dans le contrat


def test_la_phrase_d_urgence_est_ecrite_une_fois_et_dite_dans_chaque_prompt():
    """n° 147 : un trou constant ; aucun texte à trous ne la recopie ; chaque prompt rendu la porte une fois."""
    g = G.charger()
    assert g.trous["phrase_d_urgence"] == {"constante": URGENCE}
    for nom in PROMPTS:
        assert URGENCE not in g.textes[nom] and "{{phrase_d_urgence}}" in g.textes[nom], nom
    assert URGENCE not in g.textes["accueil_au_decroche"]
    assert all(B.prompt(f).count(URGENCE) == 1 for f in PROMPTS)


CONSIGNES = {  # trou constant -> (la consigne, les textes qui la portent) : écrites UNE fois, le code ne les tient pas (un merci ne finit pas l'appel, le nom, l'alcool)
    "consigne_merci_ok": ("Un merci ou un ok n'est pas une fin.", PROMPTS),
    "consigne_nom": ("Tu ne dis jamais son nom ni son prénom.", PROMPTS),
    "consigne_alcool": ("Tu ne proposes jamais d'alcool.", ("commande", "reservation", "service")),
}


def test_les_consignes_que_le_code_ne_tient_pas_sont_ecrites_une_fois_et_dites_dans_chaque_prompt():
    """R1 (n° 119, 148) : un merci ou un ok qui ne finit pas l'appel, ne jamais dire le nom de la personne, ne jamais proposer d'alcool : aucun code ne les tient, le modèle les dit.
    Chacune est un trou constant (comme la phrase d'urgence), jamais recopiée ; chaque prompt qui la portait la porte encore, une fois.
    Les trois scénarios (« ah ok merci » à l'accueil, « Monsieur Dupont » en réservation, « une bière avec ça ? » en commande) se rejouent au banc des 72."""
    g = G.charger()
    for trou, (consigne, textes) in CONSIGNES.items():
        assert g.trous[trou] == {"constante": consigne}
        for nom in PROMPTS:
            texte = g.textes[nom]
            assert consigne not in texte
            assert ("{{%s}}" % trou in texte) == (nom in textes), (trou, nom)
            assert B.prompt(nom).count(consigne) == (1 if nom in textes else 0), (trou, nom)


def test_les_textes_ne_portent_plus_les_phrases_retirees_ni_le_mauvais_nom_de_sortie():
    """n° 145, 48 : la sortie du service est nommée juste ; la phrase « personne ici ne traite » n'est plus écrite."""
    g = G.charger()
    for nom, texte in g.textes.items():
        assert "sortie retour" not in texte and "personne ici ne traite" not in texte, nom
    assert "la sortie rendre_la_main" in g.textes["service"]


def test_le_gabarit_est_a_la_version_7_et_la_6_garde_son_empreinte():
    assert G.charger().version == 7
    d, t, r = {"etapes": ["accueil"]}, {"accueil": "texte"}, {"modele": {}}
    assert G._empreinte(d, t, r, 6, "outils-a") == G._empreinte(d, t, r, 6, "outils-b")  # la version 6, figée, n'est jamais réécrite


async def test_le_lexique_suit_la_carte_dans_la_limite_du_fournisseur():
    """``lexique_depuis_la_carte`` : les noms de la carte entrent au lexique, avec le plafond du fournisseur de l'organisation."""
    vu = {}

    async def remplir(organization_id, elements, plafond):
        vu.update(organisation=organization_id, elements=elements, plafond=plafond)
        return type("R", (), {"ajoutes": 2, "deja_presents": 1, "a_ecouter": 0})()

    with patch("api.db.bases_clients.restauration_carte.carte_du_restaurant", new=AsyncMock(return_value={"x": 1})), patch(
        "api.db.bases_clients.restauration_client.elements_de_la_carte", return_value=(["napolitaine", "diavola"], None)
    ), patch("api.services.restauration.carte_et_allergenes.lexique_liste.remplir_le_lexique", new=remplir), patch.object(
        I, "_plafond_de_l_organisation", new=AsyncMock(return_value=150)
    ):
        bilan = await I.lexique_depuis_la_carte(7, object(), 3)
    assert bilan == {"ajoutes": 2, "deja_presents": 1, "a_ecouter": 0}
    assert vu == {"organisation": 7, "elements": ["napolitaine", "diavola"], "plafond": 150}


async def test_apres_l_import_un_lexique_en_echec_ne_bloque_pas_les_tests_generes():
    from api.services.gabarits import tests_generes

    regeneres = []

    async def regenerer(organization_id, workflow_id):
        regeneres.append(workflow_id)

    with patch.object(I, "lexique_depuis_la_carte", new=AsyncMock(side_effect=RuntimeError("base coupée"))), patch.object(
        I.db_client, "applications_de_l_etablissement", new=AsyncMock(return_value=[{"workflow_id": 11}])
    ), patch.object(tests_generes, "regenerer", new=regenerer):
        await I.apres_l_import_de_la_carte(7, object(), 3, {"carte": {"x": 1}})
        await I.apres_l_import_de_la_carte(7, object(), 3, {"carte": None})  # pas de carte : rien à faire
    assert regeneres == [11]


EMPREINTE_DU_BANC = "0cd956273c37363de3b0b4b57356e9dd912f5a6ccca1daf1f9538c7e66bccd23"  # ``rendus.json`` tel que le banc l'a produit (commit 609437c5, version 6)


def test_les_rendus_du_banc_sont_geles_et_les_ecarts_de_la_v7_sont_declares_en_un_seul_endroit():
    """R6 : ``rendus.json`` n'est jamais corrigé à la main (même empreinte que la version 6) ; chaque écart de la v7 est dans ``ecarts_v7.json`` et change exactement ce qu'il dit."""
    from api.services.gabarits.restauration.textes import banc

    octets = (TX.DOSSIER / TX.TEMOIN / "banc" / "rendus.json").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(octets).hexdigest() == EMPREINTE_DU_BANC
    ecarts = json.loads((TX.DOSSIER / TX.TEMOIN / "banc" / "ecarts_v7.json").read_text(encoding="utf-8"))["ecarts"]
    assert {e["n"] for e in ecarts} == {43, 47, "R12", "RC2"}
    avant, apres = json.dumps(banc.rendus_du_banc(), ensure_ascii=False), json.dumps(banc.rendus(), ensure_ascii=False)
    for e in ecarts:
        assert json.dumps(e["de"], ensure_ascii=False)[1:-1] in avant and json.dumps(e["vers"], ensure_ascii=False)[1:-1] in apres
        assert json.dumps(e["de"], ensure_ascii=False)[1:-1] not in apres


def test_les_contrats_de_chaque_version_sont_la_derivation_des_rendus_du_banc():
    """R2 : le contrat 6 est celui du banc, tel quel ; le contrat 7 ajoute les écarts déclarés. Jamais l'un réécrit pour l'autre (I-12)."""
    from api.services.commande.contrat import LISTES
    from api.services.gabarits.restauration.textes import banc

    listes = {"commande": set(LISTES)}
    def fichier(n):
        return json.loads((TX.DOSSIER / TX.TEMOIN / "contrats" / f"{n}.json").read_text(encoding="utf-8"))

    assert fichier(6) == banc.derivation_du_contrat(banc.rendus_du_banc(), listes)
    assert fichier(7) == banc.derivation_du_contrat(banc.rendus(), listes)
    assert TX.contrat() == TX.contrat(gabarit_version=TX.version_courante())


def test_un_agent_installe_en_version_6_lit_le_texte_6_de_la_case_variante():
    """R2 : le texte de la case ``variante`` est celui de la version du gabarit de l'application. Rouge si le contrat 6 est écrasé par le 7."""
    vieux, neuf = "Seulement si elle l'a dite.", "Seulement si elle l'a dite : la taille ou la déclinaison de cet article. Le choix dans un menu ou une formule va dans composition, jamais ici."
    for version, texte in ((6, vieux), (7, neuf)):
        variante = TX.cases_de_la_fiche("commande", gabarit_version=version)["ajouter"]["items"]["properties"]["variante"]
        assert variante["description"] == texte, version
    assert TX.outil("service", "rendre_la_main", gabarit_version=6)["description"] != TX.outil("service", "rendre_la_main", gabarit_version=7)["description"]


async def test_l_installation_lit_les_sorties_du_contrat_de_la_version_du_gabarit():
    g = G.charger()
    g6 = G.Gabarit(g.nom, 6, g.definition, g.textes, g.reglages, "x")
    assert I._sorties_du_contrat(g6, "service")["rendre_la_main"] != I._sorties_du_contrat(g, "service")["rendre_la_main"]
    assert g.outils_de("service") == TX.outils_de("service")  # le gabarit chargé et la lecture du métier disent la même chose


def test_le_texte_de_chaque_cible_du_passage_n_est_ecrit_qu_une_fois_dans_le_gabarit():
    """R10 : ``gabarit.json`` (``passages``) est la source ; les contrats ne portent que l'en-tête de l'outil de passage, le gabarit compose la description."""
    g = G.charger()
    for n in (6, 7):
        brut = json.dumps(json.loads((TX.DOSSIER / TX.TEMOIN / "contrats" / f"{n}.json").read_text(encoding="utf-8")), ensure_ascii=False)
        assert " cible " not in brut, n
        for phrase in g.passages.values():
            assert phrase not in brut, n
    passer = TX.outil(g.principal, g.definition["outil_de_passage"])
    assert all(f" cible {e} : {t}" in passer["description"] for e, t in g.passages.items())
    assert TX.variantes()[g.definition["outil_de_passage"]] == passer["description"]


def test_aucun_nom_d_article_des_cartes_du_banc_dans_la_version_7():
    """R12 (consigne d'Evan : aucun nom d'article en dur) : le contrat 7, les textes à trous et le gabarit servent TOUS les métiers ; le nom d'un produit ou d'une catégorie des cartes du banc n'y figure pas (la v6 reste figée, hors de ce test)."""
    import re

    cartes = Path(__file__).resolve().parents[1] / "banc_a" / "cartes"
    noms: set[str] = set()
    for f in cartes.glob("*.json"):
        carte = json.loads(f.read_text(encoding="utf-8"))["carte"]
        for cle in ("produits", "categories"):
            noms |= {x["nom"].strip().lower() for x in carte.get(cle, []) if len(x.get("nom", "").strip()) >= 4}
    racine = Path(G.__file__).resolve().parent / "restauration"
    fichiers = [racine / "textes/gemma-4/contrats/7.json", racine / "gabarit.json", *sorted((racine / "textes_a_trous").glob("*.txt"))]
    trouves = sorted(
        (f.name, n)
        for f in fichiers
        for n in noms
        if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", f.read_text(encoding="utf-8").lower())
    )
    assert not trouves, trouves

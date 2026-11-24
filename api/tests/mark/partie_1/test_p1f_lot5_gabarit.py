"""[.mark] Plan final Partie 1, lot 5 (G, n° 142 à 148, 153) : le gabarit tient chaque donnée en UN endroit.

Avant : le contrat des outils servi aux vrais appels était un instantané du banc rangé par carte de test (310 Ko), les prompts existaient en 13 copies remplies et en
6 textes à trous, l'installation retrouvait le texte de chaque cible en découpant une description, la phrase d'urgence était écrite dans cinq textes. Règles : le contrat
est ``outils.json`` SANS carte ; les rendus du banc ne sont lus que par les tests ; le prompt d'une carte est RENDU depuis le texte à trous ; les textes de passage sont
dans ``gabarit.json`` ; une phrase citée par plusieurs textes est un trou constant ; le gabarit dit lui-même son étape principale et l'état de référence de chaque étape.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from api.services.gabarits import gabarit as G
from api.services.gabarits import installation as I
from api.services.gabarits.restauration import textes as TX

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


def test_aucun_module_du_fonctionnement_ne_lit_les_rendus_du_banc():
    """n° 143, règle : seuls les tests lisent ``textes.banc`` et ses anciens noms (``outils_verses``, ``rendu``, ``prompt``, ``requetes_types``, ``CARTE_TEMOIN``)."""
    fautifs = []
    for chemin in RACINE_SERVICES.rglob("*.py"):
        if "textes" in chemin.parts and chemin.name in ("banc.py", "__init__.py"):
            continue
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for n in ast.walk(arbre):
            if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("restauration.textes.banc"):
                fautifs.append(str(chemin))
            if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("gabarits.restauration.textes") and any(a.name in NOMS_DU_BANC | {"banc"} for a in n.names):
                fautifs.append(str(chemin))
    assert fautifs == []


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
    assert all(TX.prompt(f).count(URGENCE) == 1 for f in PROMPTS)


def test_les_textes_ne_portent_plus_les_regles_que_le_code_tient():
    """n° 119, 145, 148, 48 : un seul texte par règle (fin de l'appel, nom de la sortie, alcool et nom de la personne tenus par le code)."""
    g = G.charger()
    for nom, texte in g.textes.items():
        assert "Un merci ou un ok" not in texte and "sortie retour" not in texte and "personne ici ne traite" not in texte, nom
        assert "ni son prénom" not in texte, nom
    for nom in ("commande", "reservation", "service"):
        assert "d'alcool" not in g.textes[nom], nom
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

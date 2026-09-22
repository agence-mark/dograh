"""[.mark] Garantie : la rue et l'épellation sont BRANCHÉES, au bon endroit, dans le bon ordre.

Les deux lecteurs sont éprouvés isolément (`test_recherche_voie.py`,
`test_lecture_epellation.py`). ⛔ **Des lecteurs justes ne prouvent rien tant
qu'on n'a pas traversé la vraie route d'écriture** : le 14/09, retirer
`run_configs` d'un point d'appel laissait tous les tests unitaires verts.

Ce fichier fait donc passer un message **par le processeur**, et regarde ce qui
en sort.

| Section | Ce qu'elle tient |
|---|---|
| 1 | L'**ordre** de lecture : épellation AVANT les nombres, sinon « deux T » → « 2 T » |
| 2 | La **rue** est cherchée dans la commune des tours PRÉCÉDENTS (Q6) |
| 3 | Les deux **interrupteurs** (Q11), lus chacun pour soi |
| 4 | Les **traces** écrites, et le verbatim intact |
| 5 | Ce qui ne doit **jamais** arriver : double lecture, échec qui coûte l'appel |
| 6 | Le **clavier du labo** traité comme un appel (R5) |
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests import run_test

from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.epellation.mention import MARQUE as MARQUE_EPELLATION
from api.services.pipecat.lecture_appelant import (
    LectureAppelantProcessor,
    creer_lecture_appelant,
    lire_message_tape,
    lire_texte,
)
from api.services.pipecat.verification_communes import (
    CLE_TRACE,
    CLE_TRACE_EPELLATIONS,
    CLE_TRACE_VOIES,
    epellation_allumee,
    voies_allumees,
)
from api.services.voies import base as base_voies
from api.services.voies.mention import MARQUE as MARQUE_VOIE

DONNEES = Path(__file__).parent / "donnees"
MAGASIN = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")
STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)

NOEUD_ADRESSE = SimpleNamespace(
    name="adresse",
    extraction_variables=[SimpleNamespace(name="adresse_intervention"), SimpleNamespace(name="commune")],
)
NOEUD_ACCUEIL = SimpleNamespace(name="accueil", extraction_variables=[SimpleNamespace(name="motif")])

DEMARRAGE_S = 15
# Pont-Sainte-Maxence (60509) porte une vraie « Rue Danton » et un vrai
# « Quai de la Pêcherie » : les deux sont dans l'index de test.
PONT = "60509"


@pytest.fixture(autouse=True)
def index_de_test(monkeypatch, tmp_path):
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", DONNEES / "voies")
    monkeypatch.setattr(base_voies, "EXPORT", "test-2026-09-16")
    monkeypatch.setattr(base_voies, "DOSSIER_TRAVAIL", tmp_path / "voies")
    base_voies.voies_de.cache_clear()
    yield
    base_voies.voies_de.cache_clear()


class Registre:
    """Un consignateur minimal, qui sait aussi se relire (comme la vraie)."""

    def __init__(self, deja: dict | None = None):
        self.entrees: dict[str, list] = {cle: list(v) for cle, v in (deja or {}).items()}

    def __call__(self, entree: dict, cle: str) -> None:
        self.entrees.setdefault(cle, []).append(entree)

    def lire(self, cle: str) -> list:
        return self.entrees.get(cle, [])


def _commune_deja_vue(insee: str, nom: str) -> Registre:
    """Le registre d'un appel où la commune a été tranchée à un tour précédent."""
    return Registre(
        {CLE_TRACE: [{"etape": "coordonnees", "entendu": nom, "statut": "sure",
                      "commune_retenue": {"nom": nom, "code_insee": insee}}]}
    )


async def _lu(texte, *, noeud=NOEUD_ADRESSE, consigner=None, conversion=True, voies=True,
              epellation=True, verification=True):
    return await lire_texte(
        texte,
        conversion=conversion,
        verification=verification,
        langue_francaise=True,
        adresse=MAGASIN,
        noeud=noeud,
        consigner=consigner,
        voies=voies,
        epellation=epellation,
    )


# --- 1. L'ordre de lecture ------------------------------------------------


async def test_lepellation_est_lue_avant_les_nombres():
    """🔴 L'ordre du plan, et la raison d'être de cet ordre.

    Si les nombres passaient d'abord, « deux T » deviendrait « 2 T » et
    l'épellation serait définitivement perdue — le lecteur ne verrait plus de
    lettre à lire.
    """
    lu = await _lu("c'est d u p o n avec deux t", noeud=NOEUD_ACCUEIL)
    assert "Dupontt" in lu
    assert MARQUE_EPELLATION in lu


async def test_les_mentions_arrivent_dans_lordre_du_plan():
    """Communes, rue, épellation, nombres : l'ordre des notes accolées."""
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    lu = await _lu("c'est au six rue Danton, d a n t o n", consigner=registre)
    assert MARQUE_VOIE in lu and MARQUE_EPELLATION in lu
    assert lu.index(MARQUE_VOIE) < lu.index(MARQUE_EPELLATION)


# --- 2. La rue, et la commune des tours précédents ------------------------


async def test_la_rue_est_cherchee_dans_la_commune_dun_tour_precedent():
    """🔑 Le cas NORMAL de vos agents (Q6) : la ville est demandée avant la rue,
    et n'est pas répétée avec elle. Sans la relecture du registre, la rue ne
    serait vérifiée sur aucun des tours qui en portent une."""
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    lu = await _lu("c'est au six rue Danton", consigner=registre)
    assert MARQUE_VOIE in lu
    assert "Rue Danton" in lu


async def test_sans_aucune_commune_connue_la_rue_nest_pas_cherchee():
    """⛔ Chercher dans une commune au hasard serait pire que ne rien faire."""
    lu = await _lu("c'est au six rue Danton", consigner=Registre())
    assert MARQUE_VOIE not in lu


async def test_une_commune_seulement_a_confirmer_ne_sert_pas_de_base():
    """Une ville non tranchée ne doit pas désigner la liste de rues à fouiller."""
    registre = Registre(
        {CLE_TRACE: [{"etape": "coordonnees", "entendu": "Bovet", "statut": "a_confirmer",
                      "commune_retenue": None}]}
    )
    lu = await _lu("c'est au six rue Danton", consigner=registre)
    assert MARQUE_VOIE not in lu


async def test_la_rue_nest_pas_cherchee_a_une_etape_sans_adresse():
    """Q7 : la rue suit le même réglage d'étape que les communes."""
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    lu = await _lu("c'est au six rue Danton", noeud=NOEUD_ACCUEIL, consigner=registre)
    assert MARQUE_VOIE not in lu


async def test_lepellation_elle_agit_a_toute_etape():
    """Q8 : on épelle un nom à n'importe quel moment de l'appel."""
    lu = await _lu("c'est monsieur f l a m a n t", noeud=NOEUD_ACCUEIL)
    assert MARQUE_EPELLATION in lu


# --- 3. Les interrupteurs (Q11) -------------------------------------------


def test_les_deux_interrupteurs_sortent_allumes():
    assert WorkflowConfigurationDefaults().verification_voies is True
    assert WorkflowConfigurationDefaults().lecture_epellation is True
    for configuration in ({}, None, {"verification_voies": None}, {"lecture_epellation": None}):
        assert voies_allumees(configuration) is True
        assert epellation_allumee(configuration) is True


def test_chaque_interrupteur_ne_relit_que_sa_cle():
    """⛔ Un autre réglage stocké hors bornes ne doit pas tuer l'appel ici."""
    hors_bornes = {"max_call_duration": 0, "horaires_ouverture": 12}
    assert voies_allumees(hors_bornes) is True
    assert epellation_allumee(hors_bornes) is True


def test_une_valeur_illisible_laisse_linterrupteur_allume():
    assert voies_allumees({"verification_voies": "peut-être"}) is True
    assert epellation_allumee({"lecture_epellation": []}) is True


async def test_chaque_interrupteur_eteint_coupe_son_lecteur_et_lui_seul():
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    texte = "c'est au six rue Danton, d a n t o n"

    sans_voie = await _lu(texte, consigner=registre, voies=False)
    assert MARQUE_VOIE not in sans_voie
    assert MARQUE_EPELLATION in sans_voie

    sans_epellation = await _lu(texte, consigner=_commune_deja_vue(PONT, "Pont-Sainte-Maxence"),
                                epellation=False)
    assert MARQUE_VOIE in sans_epellation
    assert MARQUE_EPELLATION not in sans_epellation


def test_la_fabrique_transmet_les_deux_reglages_au_processeur():
    """⛔ Mesuré le 14/09 : un point de collecte qui ne reçoit pas la
    configuration tourne sur les défauts, tous les autres tests restant verts."""
    etape = creer_lecture_appelant(
        {"verification_voies": False, "lecture_epellation": False, "verification_communes": True},
        STT_FRANCAIS, None, lambda: None,
    )
    assert isinstance(etape, LectureAppelantProcessor)
    assert etape._voies is False
    assert etape._epellation is False


# --- 4. Les traces, et le verbatim ----------------------------------------


async def test_la_rue_et_lepellation_sont_consignees():
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    await _lu("c'est au six rue Danton, d a n t o n", consigner=registre)

    voies = registre.lire(CLE_TRACE_VOIES)
    assert len(voies) == 1
    assert voies[0]["etape"] == "adresse"
    assert voies[0]["statut"] in ("sure", "a_confirmer")
    assert voies[0]["propositions"]

    epellations = registre.lire(CLE_TRACE_EPELLATIONS)
    assert len(epellations) == 1
    assert epellations[0]["epele"] == "Danton"
    # I1 : la forme ENTENDUE, que le filtre du nom de l'autre session peut relire.
    assert "d a n t o n" in epellations[0]["entendu"]


async def test_la_trace_de_la_rue_porte_le_numero_sans_le_dire_au_modele():
    """Q5 : le numéro est vérifié et consigné, jamais dit."""
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    lu = await _lu("c'est au six rue Danton", consigner=registre)
    trace = registre.lire(CLE_TRACE_VOIES)[0]
    assert trace["propositions"][0]["numero_present"] is not None
    assert "numéro" not in lu.split(MARQUE_VOIE)[1].lower()


async def test_le_texte_de_lappelant_nest_jamais_reecrit_par_ces_deux_lecteurs():
    """🔒 N1 : le verbatim garde les mots ; seules des notes sont accolées."""
    texte = "c'est au six rue Danton, d a n t o n"
    lu = await _lu(texte, consigner=_commune_deja_vue(PONT, "Pont-Sainte-Maxence"), conversion=False)
    assert lu.startswith(texte)


# --- 5. Ce qui ne doit jamais arriver -------------------------------------


async def test_un_message_deja_annote_nest_pas_relu():
    """⛔ Un contexte renvoyé après un appel d'outil ne doit pas doubler les notes."""
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    une_fois = await _lu("c'est au six rue Danton, d a n t o n", consigner=registre)
    deux_fois = await _lu(une_fois, consigner=registre)
    assert deux_fois == une_fois
    assert une_fois.count(MARQUE_VOIE) == 1
    assert une_fois.count(MARQUE_EPELLATION) == 1


async def test_un_departement_absent_de_limage_ne_coute_pas_lappel():
    """⛔ Un fichier manquant rend « rue non vérifiée », jamais une erreur."""
    registre = Registre(
        {CLE_TRACE: [{"etape": "coordonnees", "entendu": "Ajaccio", "statut": "sure",
                      "commune_retenue": {"nom": "Ajaccio", "code_insee": "2A004"}}]}
    )
    texte = "c'est au six cours Napoléon"
    # conversion coupée : ce test regarde la rue, pas la réécriture des nombres.
    lu = await _lu(texte, consigner=registre, conversion=False)
    assert lu.startswith(texte)
    assert MARQUE_VOIE not in lu


async def test_un_lecteur_qui_echoue_laisse_le_message_intact(monkeypatch):
    def tombe(*args, **kwargs):
        raise RuntimeError("banc")

    monkeypatch.setattr("api.services.pipecat.lecture_appelant.analyser_voie", tombe)
    texte = "c'est au six rue Danton"
    lu = await _lu(texte, consigner=_commune_deja_vue(PONT, "Pont-Sainte-Maxence"), conversion=False)
    assert lu.startswith(texte)
    assert MARQUE_VOIE not in lu


async def test_le_processeur_traverse_un_vrai_contexte():
    """La route d'écriture entière : le message du contexte ressort annoté."""
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    processeur = LectureAppelantProcessor(
        conversion=False,
        verification=True,
        langue_francaise=True,
        adresse=MAGASIN,
        etape_courante=lambda: NOEUD_ADRESSE,
        consigner=registre,
        voies=True,
        epellation=True,
    )
    contexte = LLMContext(messages=[{"role": "user", "content": "c'est au six rue Danton"}])
    await run_test(
        processeur, frames_to_send=[LLMContextFrame(context=contexte)], start_timeout=DEMARRAGE_S
    )
    assert MARQUE_VOIE in contexte.messages[-1]["content"]
    assert registre.lire(CLE_TRACE_VOIES)


# --- 5 bis. La base de rues elle-même ------------------------------------


def test_letat_de_la_base_de_rues_est_dit_au_demarrage(monkeypatch, tmp_path, caplog):
    """🔴 Une production SANS aucun fichier de rues est autrement invisible :
    les tests pointent leur propre dossier et restent verts, chaque tour
    d'adresse lève, le lecteur avale l'erreur, et l'écran continue d'offrir un
    interrupteur pour quelque chose qui ne tourne jamais."""
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", tmp_path / "vide")
    combien, souci = base_voies.base_disponible()
    assert combien == 0
    assert souci and "absent" in souci

    (tmp_path / "vide").mkdir()
    combien, souci = base_voies.base_disponible()
    assert combien == 0
    assert souci and "aucun fichier" in souci

    # Le vrai dossier de test, lui, répond présent.
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", DONNEES / "voies")
    monkeypatch.setattr(base_voies, "EXPORT", "test-2026-09-16")
    combien, souci = base_voies.base_disponible()
    assert combien == 11
    assert souci is None


def test_un_fichier_de_rues_abime_est_refait_au_lieu_detre_servi(monkeypatch, tmp_path):
    """⛔ Sans ce contrôle, un fichier tronqué une seule fois faisait échouer
    TOUTES les lectures suivantes jusqu'au redéploiement, en silence."""
    monkeypatch.setattr(base_voies, "DOSSIER_BASE", DONNEES / "voies")
    monkeypatch.setattr(base_voies, "EXPORT", "test-2026-09-16")
    monkeypatch.setattr(base_voies, "DOSSIER_TRAVAIL", tmp_path / "voies")
    base_voies.voies_de.cache_clear()

    bon = base_voies.fichier_departement("60")
    assert bon.exists()
    bon.write_bytes(b"ceci n'est pas une base SQLite")

    base_voies.voies_de.cache_clear()
    voies = base_voies.voies_de("60509")
    assert len(voies) > 100, "le fichier abîmé aurait dû être refait"


# --- 6. Le clavier du labo (R5) -------------------------------------------


async def test_le_clavier_est_traite_comme_un_appel():
    registre = _commune_deja_vue(PONT, "Pont-Sainte-Maxence")
    lu = await lire_message_tape(
        "c'est au six rue Danton, d a n t o n", {}, STT_FRANCAIS, MAGASIN, NOEUD_ADRESSE, registre
    )
    assert MARQUE_VOIE in lu
    assert MARQUE_EPELLATION in lu
    assert registre.lire(CLE_TRACE_VOIES)
    assert registre.lire(CLE_TRACE_EPELLATIONS)

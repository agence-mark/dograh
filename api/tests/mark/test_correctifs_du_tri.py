"""[.mark] Les correctifs de code du tri du 17/10 (chantier orchestrateur-trois-cerveaux, lot 5).

Tri `Labo-agent-vocal/plans/agents-specialises/2026-10-17-tri-defauts-prompts-code-modele.md` :
défauts vus sur plusieurs cerveaux avec les mêmes textes, donc corrigés dans le code, sans toucher
au parcours. Chaque cas est joué par la vraie route (lecteur d'adresses, greffier, lecteur de
portes, flux du cerveau, trace) et échoue si le correctif ne produit rien (R1).

| Test | Ce qu'il prouve |
|---|---|
| B1 | « paul.garnier60 arobase gmail point com » (run 1442) est lu en entier ; tiret, tiret bas ; un point suivi d'une espace n'est jamais collé ; la consigne du greffier dit de recopier l'adresse entière |
| B3 | un champ dicté tiré d'une adresse e-mail est refusé par la vraie passe du greffier ; dit à côté, il est écrit ; un champ qui recopie la parole s'écrit une fois |
| B5 | la trace d'une réponse porte l'envoi (UTC) et les délais du premier morceau, du premier texte et de la fin, mesurés côté serveur |
| C1 | « *(→ retour)* » et « **•**retour** » sont des portes prises, jamais dites, au bout d'une phrase ou en tête ; une puce suivie d'une phrase reste dite |
| C2 | « *(Je le relis une fois noté.)* » n'est jamais dit, même coupé en morceaux ; une didascalie à flèche reste au lecteur de portes ; un texte en gras passe |
| C6 | l'en-tête « [Fiche de l'appel … » n'est jamais dit, quelle que soit sa longueur, coupé en morceaux ou jamais fermé |
"""

import json

import pytest
from pipecat.frames.frames import LLMContextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.tests import run_test
from pipecat.tests.utils import SleepFrame

from api.services.epellation.lecture import lire
from api.services.epellation.mention import mentionner_epellations
from api.services.pipecat.greffier import (
    REGLES_D_ECRITURE,
    champs_a_noter,
    consigne_du_greffier,
)
from api.services.pipecat.texte_du_cerveau import DEBUT_ENTETE_FICHE
from api.services.pipecat.trace_modele import (
    CLE_TRACE_REQUETES,
    TRACE_REQUETES,
    brancher_la_trace,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    ENTETE_ETAT,
    ENTETE_ETAT_GREFFIER,
    ENTETE_ETAT_NOTE_D_ABORD,
    ENTETE_ETAT_POST_SCRIPTUM,
    MODE_GREFFIER,
    ReglagesFiche,
)
from api.tests.mark.test_greffier import _Modele, _Montage
from api.tests.mark.test_greffier_portes import _MontageGreffier
from api.tests.mark.test_post_scriptum import DEMARRAGE_S
from api.tests.mark.test_porte_parlee_processeur import _Ordre
from api.tests.mark.test_texte_du_cerveau import _appels, _dit, _lire, _m
from api.tests.mark.test_trace_modele import _contexte, _lecteur, _moteur, _service

# --------------------------------------------------------------------------- #
# B1. L'adresse dictée avec un point collé
# --------------------------------------------------------------------------- #

RUN_1442 = "Mon adresse mail c'est paul.garnier60 arobase gmail point com"


def test_b1_le_run_1442_est_lu_en_entier():
    [lue] = lire(RUN_1442)
    assert lue.courriel is True
    assert lue.epele == "paul.garnier60@gmail.com"
    assert lue.entendu == "paul.garnier60 arobase gmail point com"


@pytest.mark.parametrize(
    "dit, attendu",
    [
        ("paul-garnier60 arobase gmail point com", "paul-garnier60@gmail.com"),
        ("paul_garnier arobase gmail point com", "paul_garnier@gmail.com"),
        ("c.caron arobase orange point fr", "c.caron@orange.fr"),
        ("paul point garnier arobase gmail point com", "paul.garnier@gmail.com"),
        ("evan arobase gmail point com", "evan@gmail.com"),
    ],
)
def test_b1_les_autres_formes_collees(dit, attendu):
    [lue] = lire(dit)
    assert lue.epele == attendu


def test_b1_un_point_suivi_d_une_espace_n_est_jamais_colle():
    # La fin d'une phrase, puis l'adresse : le mot d'avant n'en fait pas partie.
    [lue] = lire("C'est fini. evan arobase gmail point com")
    assert lue.epele == "evan@gmail.com"


def test_b1_la_note_donnee_au_modele_porte_l_adresse_entiere():
    note = mentionner_epellations(RUN_1442, lire(RUN_1442))
    assert "paul.garnier60@gmail.com" in note


# --------------------------------------------------------------------------- #
# B3. Un champ dicté n'est jamais déduit ; la demande s'écrit une fois
# --------------------------------------------------------------------------- #

_FICHE_B3 = {
    "fiche_au_fil_de_leau": True,
    CLE_MODE: MODE_GREFFIER,
    "fiche_champs": [
        {"nom": "prenom", "origine": "dicte", "description": "Prénom"},
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {"nom": "courriel", "origine": "dicte", "description": "Adresse e-mail"},
        {
            "nom": "demande_dite",
            "origine": "dicte",
            "description": "La demande, avec les mots de la personne",
            "copie_de_la_parole": True,
        },
    ],
}


def test_b1_la_consigne_du_greffier_dit_de_recopier_l_adresse_entiere():
    consigne = consigne_du_greffier(ReglagesFiche.depuis(_FICHE_B3), None)
    assert "tout ce qui précède l'arobase compte" in consigne
    assert "jamais raccourcie à sa fin" in consigne
    assert "ne se tire pas d'une adresse e-mail" in consigne
    assert REGLES_D_ECRITURE in consigne


async def _passe(paroles: list[str], rendue: dict) -> _Montage:
    montage = _Montage(_Modele(rendue), _FICHE_B3, fiche={})
    montage.messages = [{"role": "user", "content": p} for p in paroles]
    await montage.passe()
    return montage


@pytest.mark.asyncio
async def test_b3_un_prenom_tire_d_une_adresse_dite_est_refuse():
    montage = await _passe([RUN_1442], {"prenom": "paul", "nom": "garnier"})
    assert "prenom" not in montage.fiche and "nom" not in montage.fiche
    assert {r["champ"] for r in montage.greffier._refus} == {"prenom", "nom"}
    assert all(r["raison"] == "non_dit" for r in montage.greffier._refus)


@pytest.mark.asyncio
async def test_b3_la_meme_valeur_dite_a_cote_est_ecrite():
    montage = await _passe(
        ["Je m'appelle Paul Garnier", "Mon mail : paul.garnier60 arobase gmail point com"],
        {"prenom": "Paul", "nom": "Garnier"},
    )
    assert montage.fiche["prenom"] == "Paul"
    assert montage.fiche["nom"] == "Garnier"


@pytest.mark.asyncio
async def test_b3_l_adresse_elle_meme_est_ecrite_entiere():
    montage = await _passe([RUN_1442], {"courriel": "paul.garnier60@gmail.com"})
    assert montage.fiche.get("courriel") == "paul.garnier60@gmail.com"


@pytest.mark.asyncio
async def test_b3_une_adresse_ecrite_en_clair_ne_donne_pas_de_prenom():
    montage = await _passe(["mon mail est paul@gmail.com"], {"prenom": "paul"})
    assert "prenom" not in montage.fiche


def test_b3_un_champ_qui_recopie_la_parole_s_ecrit_une_fois():
    reglages = ReglagesFiche.depuis(_FICHE_B3)
    # Première formulation : écrite.
    assert champs_a_noter(reglages, {}, {"demande_dite": "je veux un devis"}) == {
        "demande_dite": "je veux un devis"
    }
    # Une réplique de confirmation ne la remplace pas.
    assert (
        champs_a_noter(
            reglages,
            {"demande_dite": "je veux un devis"},
            {"demande_dite": "Je viens de vous le donner"},
        )
        == {}
    )
    # Un champ ordinaire est toujours corrigé par la personne.
    assert champs_a_noter(reglages, {"nom": "Dupond"}, {"nom": "Dupont"}) == {"nom": "Dupont"}


# --------------------------------------------------------------------------- #
# B5. Les délais mesurés côté serveur
# --------------------------------------------------------------------------- #


async def _jouer_simple(service, lecteur):
    ordre = _Ordre()
    await run_test(
        Pipeline([service, lecteur, ordre]),
        frames_to_send=[LLMContextFrame(_contexte()), SleepFrame(sleep=0.3)],
        start_timeout=DEMARRAGE_S,
    )
    return ordre


@pytest.mark.asyncio
async def test_b5_la_trace_porte_l_envoi_et_les_delais_du_serveur():
    fiche = {"tour_appelant": 3}
    service, _ = _service()
    trace = brancher_la_trace(_moteur(fiche), service, {CLE_TRACE_REQUETES: True})
    await _jouer_simple(service, _lecteur(fiche, trace))
    [entree] = fiche[TRACE_REQUETES]
    # L'envoi : une date UTC lisible.
    assert entree["envoye_a"].endswith("+00:00") and entree["envoye_a"].startswith("20")
    assert isinstance(entree["premier_morceau_ms"], int) and entree["premier_morceau_ms"] >= 0
    assert entree["premier_texte_ms"] >= entree["premier_morceau_ms"]
    assert entree["fini_ms"] >= entree["premier_texte_ms"]
    # Chaque morceau dit son délai depuis l'envoi, croissant.
    delais = [m["depuis_l_envoi_ms"] for m in entree["morceaux"]]
    assert delais == sorted(delais) and len(delais) == len(entree["morceaux"])
    json.dumps(fiche)


@pytest.mark.asyncio
async def test_b5_case_eteinte_rien_n_est_ecrit():
    fiche = {"tour_appelant": 3}
    service, _ = _service()
    assert brancher_la_trace(_moteur(fiche), service, {}) is None
    await _jouer_simple(service, _lecteur(fiche, None))
    assert TRACE_REQUETES not in fiche


# --------------------------------------------------------------------------- #
# C1. La porte habillée
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["Quelle marque ? *(→ vers_panne)*"],
        ["Quelle marque ? *(→ vers_", "panne)*"],
        ["Quelle marque ? *", "(→ vers_panne)*"],
        ["Quelle marque ? **•**vers_panne**"],
        ["Quelle marque ? **", "•", "**vers_panne**"],
        ["*(→ vers_panne)*\nQuelle marque ?"],
        ["Quelle marque ? (→ vers_panne)"],
        ["Quelle marque ? **→ vers_panne**"],
    ],
    ids=[
        "italique-parentheses",
        "coupee-dans-le-nom",
        "balisage-dans-un-morceau-a-part",
        "puce-gras-colle",
        "puce-coupee-en-trois",
        "en-tete",
        "parentheses-seules",
        "gras-fleche",
    ],
)
async def test_c1_la_porte_habillee_est_prise_et_jamais_dite(morceaux):
    montage = _MontageGreffier()
    ordre = await montage.reponse(*morceaux)
    assert ordre.dit.strip() == "Quelle marque ?"
    for reste in ("→", "•", "*", "(", ")", "vers_panne"):
        assert reste not in ordre.dit
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]
    assert montage.portes_lues[-1]["porte_etat"] == "prise"


@pytest.mark.asyncio
async def test_c1_une_puce_suivie_d_une_phrase_reste_dite():
    montage = _MontageGreffier()
    ordre = await montage.reponse("Au choix : • entretien • panne ?")
    assert ordre.dit == "Au choix : • entretien • panne ?"
    assert montage.moteur.prises == []


@pytest.mark.asyncio
async def test_c1_un_gras_ordinaire_est_rendu_tel_quel():
    montage = _MontageGreffier()
    ordre = await montage.reponse("Rendez-vous **jeudi matin**, ", "c'est noté.")
    assert ordre.dit == "Rendez-vous **jeudi matin**, c'est noté."
    assert montage.moteur.prises == []


@pytest.mark.asyncio
async def test_c1_une_phrase_finie_par_un_balisage_est_dite_a_la_fin():
    montage = _MontageGreffier()
    ordre = await montage.reponse("Très bien. **")
    assert ordre.dit.strip().startswith("Très bien.")


# --------------------------------------------------------------------------- #
# C2. Les didascalies en italique
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["*(Je le relis une fois noté.)* Quelle marque ?"],
        ["*(Je le relis", " une fois noté.)* Quelle marque ?"],
        ["*", "(Je le relis une fois noté.)", "* Quelle marque ?"],
        ["Quelle marque ? *(L'appel est terminé.)*"],
    ],
    ids=["entiere", "coupee", "etoile-seule", "en-fin"],
)
async def test_c2_une_didascalie_n_est_jamais_dite(morceaux):
    sorties = await _lire([_m(t) for t in morceaux] + [_m(fin="stop")])
    assert _dit(sorties).strip() == "Quelle marque ?"


@pytest.mark.asyncio
async def test_c2_une_didascalie_a_fleche_reste_au_lecteur_de_portes():
    sorties = await _lire([_m("Quelle marque ? *(→ retour)*"), _m(fin="stop")])
    assert "→ retour" in _dit(sorties)


@pytest.mark.asyncio
async def test_c2_le_gras_et_l_italique_ordinaires_passent():
    sorties = await _lire(
        [_m("Rendez-vous **jeudi"), _m(" matin** à *huit* heures."), _m(fin="stop")]
    )
    assert _dit(sorties) == "Rendez-vous **jeudi matin** à *huit* heures."


@pytest.mark.asyncio
async def test_c2_une_didascalie_jamais_fermee_est_rendue():
    sorties = await _lire([_m("Bonjour *(sans fin"), _m(fin="stop")])
    assert _dit(sorties) == "Bonjour *(sans fin"


@pytest.mark.asyncio
async def test_c2_la_porte_habillee_traverse_le_flux_puis_le_lecteur():
    """R1 : le flux nettoyé donne sa ligne au lecteur de portes, qui la prend."""
    sorties = await _lire([_m("Quelle marque ? *(→ vers_panne)*"), _m(fin="stop")])
    montage = _MontageGreffier()
    ordre = await montage.reponse(_dit(sorties))
    assert ordre.dit.strip() == "Quelle marque ?"
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_panne"]


# --------------------------------------------------------------------------- #
# C6. L'en-tête de la fiche
# --------------------------------------------------------------------------- #

ENTETE_LONG = (
    "[Fiche de l'appel : pour toi seulement, tu ne la lis jamais à voix haute. "
    "Elle se remplit par tes notes, écrites avant |||. Elle montre ce qui était noté "
    "AVANT la dernière réplique de la personne : ce que cette réplique contient n'y est "
    "pas encore, c'est ta note qui l'y met.]"
)


def test_c6_l_entete_garde_le_meme_debut_que_celui_du_code():
    for entete in (
        ENTETE_ETAT,
        ENTETE_ETAT_POST_SCRIPTUM,
        ENTETE_ETAT_GREFFIER,
        ENTETE_ETAT_NOTE_D_ABORD,
    ):
        assert entete.startswith(DEBUT_ENTETE_FICHE)
    assert len(ENTETE_ETAT_NOTE_D_ABORD) > 160  # le cas que les crochets ordinaires manquaient


@pytest.mark.asyncio
@pytest.mark.parametrize("entete", [ENTETE_LONG, ENTETE_ETAT, ENTETE_ETAT_GREFFIER])
async def test_c6_l_entete_n_est_jamais_dit_quelle_que_soit_sa_longueur(entete):
    sorties = await _lire([_m(entete + " Votre numéro ?"), _m(fin="stop")])
    assert _dit(sorties).strip() == "Votre numéro ?"


@pytest.mark.asyncio
async def test_c6_coupe_en_morceaux_de_dix_caracteres():
    morceaux = [ENTETE_LONG[i : i + 10] for i in range(0, len(ENTETE_LONG), 10)]
    sorties = await _lire(
        [_m("Bien. "), *[_m(t) for t in morceaux], _m(" Votre numéro ?"), _m(fin="stop")]
    )
    assert " ".join(_dit(sorties).split()) == "Bien. Votre numéro ?"


@pytest.mark.asyncio
async def test_c6_un_entete_jamais_ferme_est_retire_a_la_fin_du_flux():
    sorties = await _lire(
        [
            _m("Bien. "),
            _m("[Fiche de l'appel : pour toi seulement, "),
            _m("nom = Dupont"),
            _m(fin="stop"),
        ]
    )
    assert _dit(sorties).strip() == "Bien."


@pytest.mark.asyncio
async def test_c6_un_crochet_ordinaire_garde_sa_regle():
    sorties = await _lire([_m("Bien [à voix basse] merci."), _m(fin="stop")])
    assert _dit(sorties) == "Bien merci."
    assert not _appels(sorties)

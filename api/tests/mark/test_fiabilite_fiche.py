"""[.mark] Chantier fiabilite-fiche-et-renvoi (01/10/2026), plan
`Labo-agent-vocal/plans/fiabilite-fiche-et-renvoi/`.

Lot A : le contrôle « dit tel quel » d'un champ dicté sans module compare aux paroles de
la personne SANS les notes des modules. Au run 925 (clavier, n° 34 v9), « devis » a fait
PROPOSER Deville par le lexique ; la note du lexique, collée au message, contient
« Deville », et le contrôle l'a lue comme une parole : « DEVILLE » a été écrit sûr dans
le nom. Une proposition « à confirmer » n'est jamais une parole ; une reconnaissance SÛRE
du lexique l'est (la même parole, avec l'écriture officielle).

Ces tests passent par les VRAIES routes HTTP du clavier, avec le lexique de
l'organisation en base ; seuls le modèle (réponses écrites d'avance) est remplacé.

| Test | Ce qu'il prouve |
|---|---|
| proposition | un terme seulement PROPOSÉ par le lexique, écrit par le modèle dans un champ sans module, est refusé (`non_dit`) |
| reconnaissance sûre | « édile kamine » reconnu sûr (Edilkamin) : la phrase écrite avec l'écriture officielle reste écrite |
| transcription propre | « Deville » bien transcrit : écrit, comme avant (exigence d'Evan du 01/10 : ne pénaliser aucun transcripteur qui transcrit bien) |
"""

import pytest

from api.enums import OrganizationConfigurationKey
from api.tests.mark.test_clavier_porte_la_fiche import _converser, _monter, _noter
from pipecat.tests import MockLLMService

LEXIQUE = {
    "format": "lexique-mark",
    "version": 1,
    "modeles_importes": [],
    "termes": [
        {"terme": "Deville", "variantes": [], "prononciation": None, "type": "nom", "categorie": "marque", "a_ecouter": False},
        {"terme": "Edilkamin", "variantes": [], "prononciation": "édile kamine", "type": "nom", "categorie": "marque", "a_ecouter": False},
    ],
}

CONFIGURATION = {
    "fiche_au_fil_de_leau": True,
    "lexique_metier": True,
    "sons_lexique": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {"nom": "motif", "origine": "dicte", "description": "Ce que la personne demande"},
    ],
}


async def _avec_lexique(db_session, async_session):
    user, workflow = await _monter(db_session, async_session, CONFIGURATION)
    await db_session.upsert_configuration(
        workflow.organization_id, OrganizationConfigurationKey.LEXIQUE_METIER.value, LEXIQUE
    )
    return user, workflow


def _journal(fiche: dict, champ: str) -> list[dict]:
    return [e for e in fiche.get("fiche_journal") or [] if e.get("champ") == champ]


@pytest.mark.asyncio
async def test_A_un_terme_seulement_propose_par_le_lexique_n_est_pas_une_parole(
    db_session, async_session, test_client_factory
):
    user, workflow = await _avec_lexique(db_session, async_session)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [_noter({"nom": "Deville"}, "note_1"), MockLLMService.create_text_chunks("D'accord.")],
        "je voudrais un devis",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    # Le lexique a bien proposé Deville pour « devis » (sinon le test ne prouve rien).
    assert any(
        t.get("terme") == "Deville" and t.get("statut") == "a_confirmer"
        for t in fiche.get("lexique_reconnu") or []
    ), fiche.get("lexique_reconnu")
    assert not fiche.get("nom"), fiche
    assert [(e["statut"], e["raison"]) for e in _journal(fiche, "nom")] == [("refuse", "non_dit")]


@pytest.mark.asyncio
async def test_A_une_reconnaissance_sure_du_lexique_compte_comme_dite(
    db_session, async_session, test_client_factory
):
    user, workflow = await _avec_lexique(db_session, async_session)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            _noter({"motif": "mon poêle Edilkamin ne démarre plus"}, "note_1"),
            MockLLMService.create_text_chunks("D'accord."),
        ],
        "mon poêle édile kamine ne démarre plus",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert any(
        t.get("terme") == "Edilkamin" and t.get("statut") == "sure"
        for t in fiche.get("lexique_reconnu") or []
    ), fiche.get("lexique_reconnu")
    assert fiche.get("motif") == "mon poêle Edilkamin ne démarre plus", fiche


@pytest.mark.asyncio
async def test_A_transcription_propre_inchangee(db_session, async_session, test_client_factory):
    user, workflow = await _avec_lexique(db_session, async_session)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [_noter({"motif": "mon poêle Deville ne ferme plus"}, "note_1"), MockLLMService.create_text_chunks("D'accord.")],
        "mon poêle Deville ne ferme plus",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert fiche.get("motif") == "mon poêle Deville ne ferme plus", fiche


# --------------------------------------------------------------------------- #
# Lots B : le module des communes (mécanismes, données seulement)
# --------------------------------------------------------------------------- #

from api.services.communes.analyse import SURE  # noqa: E402
from api.services.communes.base import charger_base  # noqa: E402
from api.services.nombres.lecture import analyser_message  # noqa: E402

SAINT_MAXIMIN = "60589"


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees(SAINT_MAXIMIN)


def _communes(texte, base, magasin, trace=None):
    r = analyser_message(texte, base, magasin, trace)
    return [(d.lectures[0].commune.nom, d.statut) for d in r.detections if not d.code_postal_entendu], r


def test_B3_une_epellation_qui_suit_ne_fait_plus_perdre_la_commune(base, magasin):
    """Run 935 : la commune dite, puis le nom épelé dans la même phrase."""
    communes, _ = _communes("Oui, Montataire. Et mon nom c'est Meunier, m e u n i e r", base, magasin)
    assert communes == [("Montataire", SURE)]


def test_B3_les_lettres_d_une_elision_comptent_comme_avant(base, magasin):
    """Témoin (corpus réel) : « l'appel », « d'ouverture » ne sont pas une épellation."""
    communes, _ = _communes("Allez c'est bon fin de l'appel. fondamental.", base, magasin)
    assert communes == []


def test_B2_un_code_dit_confirme_la_commune_dont_le_nom_ouvre_les_mots_entendus(base, magasin):
    """Run 935 : « c'est Montataire maintenant, 60160 » restait à confirmer."""
    communes, _ = _communes(
        "Je dis Nogent mais j'ai déménagé, c'est Montataire maintenant, soixante mille cent soixante", base, magasin
    )
    assert ("Montataire", SURE) in communes


def test_B2_temoin_transcription_propre_inchangee(base, magasin):
    """Témoin : le nom seul, bien transcrit, avec son code : sûr avant comme après."""
    communes, _ = _communes("c'est Montataire, soixante mille cent soixante", base, magasin)
    assert communes == [("Montataire", SURE)]


def test_B1_un_nom_porte_aussi_par_une_commune_bien_plus_proche_est_a_confirmer(base, magasin):
    """Run 935 : « Nogent » seul était Nogent (Haute-Marne), sûr ; Nogent-sur-Oise est à
    côté de l'établissement. Les deux sont proposées, la plus proche d'abord (D1)."""
    r = analyser_message("Nogent", base, magasin, [])
    (d,) = r.detections
    assert d.statut != SURE
    assert [l.commune.nom for l in d.lectures[:2]] == ["Nogent-sur-Oise", "Nogent"]


@pytest.mark.parametrize("texte, nom", [("je suis à Creil", "Creil"), ("à Senlis", "Senlis"), ("à Clermont", "Clermont")])
def test_B1_temoins_une_commune_proche_reste_sure(base, magasin, texte, nom):
    communes, _ = _communes(texte, base, magasin)
    assert communes == [(nom, SURE)]


def test_B1_temoin_la_grande_ville_reste_sure_loin_de_l_etablissement(base):
    """Corpus réel : « C'est à Bordeaux » pour un établissement de Marseille reste Bordeaux."""
    communes, _ = _communes("C'est à Bordeaux.", base, base.coordonnees("13055"))
    assert communes == [("Bordeaux", SURE)]


# --------------------------------------------------------------------------- #
# Lot C : la correction d'un numéro, paire par paire (vraie route du clavier)
# --------------------------------------------------------------------------- #

import uuid  # noqa: E402

from api.tests.mark.test_portes_souples import _messages  # noqa: E402

NUMERO = {
    "fiche_au_fil_de_leau": True,
    # Comme le n° 34 : le module des nombres lit la parole avant le modèle.
    "conversion_nombres_transcription": True,
    "fiche_champs": [{"nom": "numero_dicte", "origine": "dicte", "description": "Numéro de rappel", "chiffres": 10}],
}


async def _numero_puis(db_session, async_session, test_client_factory, correction: str, corrige: str):
    user, workflow = await _monter(db_session, async_session, NUMERO)
    appel = uuid.uuid4().hex[:6]
    charge = await _messages(
        test_client_factory,
        user,
        workflow,
        [
            (
                "zéro six douze trente-quatre quarante-sept quatre-vingt-neuf",
                [_noter({"numero_dicte": "0612344789"}, f"n_{appel}_1"), MockLLMService.create_text_chunks("Je relis.")],
            ),
            (
                correction,
                [_noter({"numero_dicte": corrige}, f"n_{appel}_2"), MockLLMService.create_text_chunks("Je relis.")],
            ),
        ],
    )
    return charge["checkpoint"]["gathered_context"]


@pytest.mark.asyncio
async def test_C_une_paire_corrigee_au_milieu_du_numero_est_notee(db_session, async_session, test_client_factory):
    fiche = await _numero_puis(
        db_session, async_session, test_client_factory,
        "non c'est pas quarante-sept c'est soixante-quatorze", "0612347489",
    )
    assert fiche.get("numero_dicte") == "0612347489", fiche.get("fiche_journal")


@pytest.mark.asyncio
async def test_C_deux_paires_corrigees_sont_notees(db_session, async_session, test_client_factory):
    fiche = await _numero_puis(
        db_session, async_session, test_client_factory,
        "non c'est trente-cinq soixante-quatorze", "0612357489",
    )
    assert fiche.get("numero_dicte") == "0612357489", fiche.get("fiche_journal")


@pytest.mark.asyncio
async def test_C_temoin_une_paire_changee_non_dite_reste_refusee(db_session, async_session, test_client_factory):
    fiche = await _numero_puis(
        db_session, async_session, test_client_factory,
        "non c'est pas quarante-sept c'est soixante-quatorze", "0612347488",
    )
    assert fiche.get("numero_dicte") == "0612344789", fiche.get("fiche_journal")

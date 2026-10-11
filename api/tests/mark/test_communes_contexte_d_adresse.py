"""[.mark] Non-regression test: « à » after a noun is not an address context for a commune.

The question this file answers:

    Does the town reader still invent a commune on « un poêle à granulés » (Grandrû, Grans,
    Grane), WITHOUT losing a commune a caller meant (« à Brel » for Bresles, « je suis à ... »,
    a postal code said), and is « Pont-Saint-Maxence » the sure Pont-Sainte-Maxence (Saint = Sainte)?

Why it exists
-------------
Run 1048 (``reading_modules``, constat B1 of the global repair): the readings « granulés » ->
Grandrû and « Delaunay » -> Launay were proposed aloud by the agent. « à » alone does not say a
place: it does after a being or living verb (« je suis à », « j'habite à »), or at the head of the
answer. After a noun it is « poêle à granulés ».

⛔ What is NOT done, and why. The plan also asked to keep a proposal without address context only
if its sound is close to a commune of the shop's radius. That rule was built and measured on the
real corpus (4 shops): it loses « Grand Villiers » -> Grandvilliers, « Abrel dans l'Oise » -> Bresles
and fails ``test_aucune_regle_ne_depend_du_magasin``, i.e. it reverses the decision of Evan of
2026-09-17 (option d: zero loss, no radius).

« Delaunay » -> Launay is fixed instead by the caller's NAME (chantier postscriptum-et-communes,
lot 1, 11/10; replay run 1088): a commune read without a sign of place is neither proposed nor
put to confirm when its words are the caller's name (noted on the record, compared by sound as
the name filter L6 does) or when the agent's last line asked for the name. Last tests below,
through the real caller reading with the record on.

The words are common words and real communes of France; no trade word is in the code.
"""

import pytest

from api.services.communes.analyse import SURE
from api.services.communes.base import charger_base
from api.services.nombres.lecture import analyser_message


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def saint_maximin(base):
    return base.coordonnees("60589")


@pytest.fixture(scope="module")
def marseille(base):
    return base.coordonnees("13055")


def _noms(r):
    return [[l.commune.nom for l in d.lectures] for d in r.detections if not d.code_postal_entendu]


@pytest.mark.parametrize(
    "texte",
    [
        "Un poêle à granulés",
        "Je voudrais un poêle à granulés pour ma maison",
        "Il me faut un tuyau à granulés",
    ],
)
def test_a_apres_un_nom_ne_propose_aucune_commune(base, saint_maximin, texte):
    assert _noms(analyser_message(texte, base, saint_maximin)) == []


@pytest.mark.parametrize("magasin", ["saint_maximin", "marseille"])
def test_la_regle_ne_depend_pas_de_l_etablissement(base, saint_maximin, marseille, magasin):
    position = saint_maximin if magasin == "saint_maximin" else marseille
    assert _noms(analyser_message("Un poêle à granulés", base, position)) == []
    assert _noms(analyser_message("Un poêle à granulés", base, None)) == []


@pytest.mark.parametrize(
    "texte, premiere",
    [
        ("Brel", "Bresles"),  # alone, badly heard
        ("à Brel", "Bresles"),  # « à » at the head of the answer
        ("j'habite à Brel", "Bresles"),
        ("oui c'est à Brel", "Bresles"),
        ("je suis à Brel", "Bresles"),
        ("nous habitons à Brel", "Bresles"),
        # Revue du 10/10 : perdues par la première version de B1, données en production.
        ("je vis à Brel", "Bresles"),
        ("on vit à Brel", "Bresles"),
        ("on est domicilié à Brel", "Bresles"),
        ("j'ai une maison à Brel", "Bresles"),
        ("je suis basé à Brel", "Bresles"),
        ("le chantier est à Brel", "Bresles"),
        ("on loge à Brel", "Bresles"),
        ("mon appartement à Brel", "Bresles"),
    ],
)
def test_la_commune_voulue_et_mal_transcrite_reste_proposee(base, saint_maximin, texte, premiere):
    noms = _noms(analyser_message(texte, base, saint_maximin))
    assert noms and noms[0][0] == premiere


def test_un_code_postal_dit_garde_la_proposition_meme_apres_un_nom(base, saint_maximin):
    """The postal code is a context of its own: the rule leaves the sentence alone."""
    r = analyser_message("la maison à Brel 60510", base, saint_maximin)
    assert any(d.lectures for d in r.detections)


def test_saint_et_sainte_sont_la_meme_commune_et_elle_est_sure(base, saint_maximin):
    r = analyser_message("c'est à Pont-Saint-Maxence", base, saint_maximin)
    [d] = [d for d in r.detections if not d.code_postal_entendu]
    assert d.statut == SURE and d.lectures[0].commune.nom == "Pont-Sainte-Maxence"
    r = analyser_message("oui Pont Saint Maxence", base, saint_maximin)
    [d] = [d for d in r.detections if not d.code_postal_entendu]
    assert d.statut == SURE and d.lectures[0].commune.nom == "Pont-Sainte-Maxence"


def test_une_autre_ville_un_autre_metier_un_garage_a_marseille(base, marseille):
    """Same rule elsewhere, nothing about a trade in the code."""
    for texte in ("Un moteur à pistons", "Un joint à remplacer", "Un contrat à durée"):
        assert _noms(analyser_message(texte, base, marseille)) == [], texte
    r = analyser_message("j'habite à Aubagne", base, marseille)
    [d] = [d for d in r.detections if not d.code_postal_entendu]
    assert d.statut == SURE and d.lectures[0].commune.nom == "Aubagne"


# --- Lot 1 du chantier postscriptum-et-communes (11/10) : le nom de la personne ------------

from types import SimpleNamespace  # noqa: E402

from api.schemas.organization_preferences import AdresseEtablissement  # noqa: E402
from api.services.pipecat.lecture_appelant import LectureAppelantProcessor  # noqa: E402
from api.services.pipecat.verification_communes import consigner_dans  # noqa: E402

SAINT_MAXIMIN = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")
MARSEILLE = AdresseEtablissement(code_postal="13001", code_insee="13055", commune="Marseille")
CHAMPS_NOM = ("nom", "commune", "code_postal")
QUESTION_NOM = "Quel est votre nom, s'il vous plaît ?"


async def _lire(parole, agent_avant=None, fiche=None, magasin=SAINT_MAXIMIN):
    """Une parole lue comme un appel la lit, fiche allumée ; rend (texte lu, fiche)."""
    fiche = dict(fiche or {})
    messages = []
    if agent_avant:
        messages.append({"role": "assistant", "content": agent_avant})
    message = {"role": "user", "content": parole}
    messages.append(message)
    processeur = LectureAppelantProcessor(
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=magasin,
        etape_courante=lambda: SimpleNamespace(name="rappel", extraction_variables=[]),
        consigner=consigner_dans(lambda: fiche),
        champs_fiche=CHAMPS_NOM,
        champs_nom=("nom",),
    )
    await processeur._lire_contexte(SimpleNamespace(context=SimpleNamespace(messages=messages), speculation=False))
    return message["content"], fiche


def _proposees(fiche):
    return [p["nom"] for t in fiche.get("communes_verifiees") or [] for p in t["propositions"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("texte", ["oui Delaunay", "Delaunay", "Delaunay Jean", "Delaunay."])
async def test_le_nom_demande_n_est_jamais_une_commune(texte):
    """Run 1088 : « Delaunay » en réponse à la question du nom sortait Launay à confirmer."""
    _, fiche = await _lire(texte, QUESTION_NOM)
    assert "Launay" not in _proposees(fiche), fiche.get("communes_verifiees")
    # La trace est gardée, à part, avec son motif.
    assert any(t.get("motif") == "nom" for t in fiche.get("communes_ecartees") or []), fiche


@pytest.mark.asyncio
async def test_le_nom_note_a_la_fiche_n_est_jamais_une_commune_meme_plus_tard():
    """Le nom déjà noté, redit à un autre tour (« c'est Delaunay »), même au même son."""
    for parole in ("c'est Delaunay", "Delonay"):
        _, fiche = await _lire(parole, "Pouvez-vous me rappeler qui appelle ?", fiche={"nom": "Delaunay"})
        assert "Launay" not in _proposees(fiche), (parole, fiche.get("communes_verifiees"))


@pytest.mark.asyncio
async def test_le_nom_donne_au_meme_tour_n_est_pas_une_commune():
    _, fiche = await _lire("Bonjour, je m'appelle Delaunay", "Que puis-je pour vous ?")
    assert "Launay" not in _proposees(fiche)


@pytest.mark.asyncio
async def test_dupont_a_creil_garde_creil():
    """Le nom puis la commune au même tour : la commune après « à » reste proposée."""
    _, fiche = await _lire("Dupont, à Creil", QUESTION_NOM)
    assert "Creil" in _proposees(fiche), fiche.get("communes_verifiees")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "texte, premiere, question",
    [
        ("Grand Villiers", "Grandvilliers", "Dans quelle commune habitez-vous ?"),
        ("Abrel dans l'Oise", "Bresles", "Dans quelle commune habitez-vous ?"),
        ("je suis à Brel", "Bresles", QUESTION_NOM),
        ("Delaunay, et j'habite à Brel", "Bresles", QUESTION_NOM),
    ],
)
async def test_zero_perte_du_corpus_reel(texte, premiere, question):
    """Les communes voulues et mal transcrites restent proposées, même le nom à côté."""
    _, fiche = await _lire(texte, question, fiche={"nom": "Delaunay"})
    assert premiere in _proposees(fiche), fiche.get("communes_verifiees")


@pytest.mark.asyncio
async def test_une_commune_qui_porte_le_nom_reste_quand_on_demande_la_commune():
    """Un signe de lieu l'emporte toujours : la personne nommée Launay qui habite Launay."""
    _, fiche = await _lire("Launay", "Dans quelle commune habitez-vous ?", fiche={"nom": "Launay"})
    assert "Launay" in _proposees(fiche), fiche.get("communes_verifiees")


@pytest.mark.asyncio
async def test_un_garage_a_marseille_meme_regle():
    """Un autre métier, une autre ville : rien du métier dans le code."""
    _, fiche = await _lire("Pagnol", "Quel est votre nom ?", magasin=MARSEILLE)
    assert not _proposees(fiche), fiche.get("communes_verifiees")
    _, fiche = await _lire("Pagnol, à Aubagne", "Quel est votre nom ?", magasin=MARSEILLE)
    assert "Aubagne" in _proposees(fiche), fiche.get("communes_verifiees")


@pytest.mark.asyncio
async def test_fiche_eteinte_rien_ne_change():
    """Sans fiche (aucune force posée), la lecture d'avant est intacte."""
    fiche: dict = {}
    messages = [{"role": "assistant", "content": QUESTION_NOM}, {"role": "user", "content": "Delaunay"}]
    processeur = LectureAppelantProcessor(
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=SAINT_MAXIMIN,
        etape_courante=lambda: SimpleNamespace(
            name="rappel", extraction_variables=[SimpleNamespace(name="commune")]
        ),
        consigner=consigner_dans(lambda: fiche),
    )
    await processeur._lire_contexte(SimpleNamespace(context=SimpleNamespace(messages=messages), speculation=False))
    assert not fiche.get("communes_ecartees")


# --- Revue du 11/10 : « appeler » veut d'abord dire téléphoner ------------------------------


@pytest.mark.asyncio
async def test_je_vous_appelle_de_garde_la_commune():
    """« Je vous appelle de Bovais » : « appelle » n'est pas un nom donné, rien n'est écarté."""
    _, fiche = await _lire("Je vous appelle de Bovais", "Que puis-je pour vous ?")
    assert not fiche.get("communes_ecartees"), fiche.get("communes_ecartees")


@pytest.mark.asyncio
async def test_d_ou_m_appelez_vous_n_est_pas_la_question_du_nom():
    _, fiche = await _lire("Bovais", "D'où m'appelez-vous ?")
    assert not fiche.get("communes_ecartees"), fiche.get("communes_ecartees")


@pytest.mark.asyncio
async def test_comment_vous_appelez_vous_est_la_question_du_nom():
    _, fiche = await _lire("Delaunay", "Comment vous appelez-vous ?")
    assert "Launay" not in _proposees(fiche)


@pytest.mark.asyncio
async def test_le_nom_note_apres_une_preposition_de_lieu_reste_une_commune():
    """Revue du 11/10 : une personne nommée Launay qui dit « à Launay » parle d'un lieu."""
    _, fiche = await _lire("Dupont, à Launay", "Que puis-je pour vous ?", fiche={"nom": "Launay"})
    assert not fiche.get("communes_ecartees"), fiche.get("communes_ecartees")


def test_le_clavier_lit_la_question_precedente_comme_le_telephone():
    """Revue du 11/10 (R1) : même fonction des deux côtés, réplique vide comprise."""
    from api.services.pipecat.lecture_appelant import _question_avant
    from api.services.workflow.text_chat_runner import _derniere_replique_agent

    for messages in (
        [{"role": "assistant", "content": "Quel est votre nom ?"}],
        [{"role": "assistant", "content": "Quel est votre nom ?"}, {"role": "user", "content": "x"},
         {"role": "assistant", "content": ""}],
        [{"role": "assistant", "content": None, "tool_calls": []}],
        [],
    ):
        assert _derniere_replique_agent(SimpleNamespace(messages=messages)) == _question_avant(messages, len(messages))

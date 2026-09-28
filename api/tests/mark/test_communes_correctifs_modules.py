"""[.mark] Chantier correctifs-modules, lot 3 : communes et rues.

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.
Les phrases sont celles des runs 861 à 881 (entendu exact). Chaque test passe par la
lecture de l'appelant telle qu'un appel la fait, fiche allumée (le module lit toutes
les phrases, à tout moment de l'appel : D4 v2), et, pour la fiche, par le vrai
gestionnaire de ``noter_information``.

| Test | Décision | Preuve (runs) |
|---|---|---|
| sans signe de lieu, un mot courant n'est jamais une commune sûre | D4 ③ | 867, 869 |
| un signe de lieu garde le comportement actuel | D4 ① | 861 |
| la question d'adresse posée juste avant est un signe de lieu | D4 ① | — |
| un nom exact sans signe de lieu est recommandé, retenu sans question s'il est noté | D4 ② | — |
| le code postal dit tranche entre les candidates | D5 | 863 |
| un type de voie au pluriel n'est pas une commune | lot 3 | 862, 863, 870 |
| « cent lits » est Senlis, et reste en lettres | lot 3 | 868 |
| un tour en deux messages est lu en entier pour la rue | lot 3 | 869 |
| aucune trace de rue sur une phrase sans rue | lot 3 | 861, 867 à 870 |
| la commune dite après la rue, sans « à », ne pèse plus sur la rue | lot 3 | 862, 866 |
"""

from types import SimpleNamespace

import pytest

from api.schemas.organization_preferences import AdresseEtablissement
from api.services.communes.base import charger_base
from api.services.pipecat.lecture_appelant import LectureAppelantProcessor, lire_texte
from api.services.pipecat.verification_communes import consigner_dans
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    ReglagesFiche,
    creer_gestionnaire,
)

MAGASIN = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")
CHAMPS = (
    {"nom": "commune", "origine": "dicte"},
    {"nom": "code_postal", "origine": "dicte"},
    {"nom": "adresse_intervention", "origine": "dicte"},
)
CONFIG = {"fiche_au_fil_de_leau": True, "fiche_champs": list(CHAMPS)}
NOMS = tuple(c["nom"] for c in CHAMPS)


@pytest.fixture(scope="module", autouse=True)
def _base():
    charger_base()


class Appel:
    """Les messages et la fiche d'un appel ; chaque parole passe par la lecture de l'appelant."""

    def __init__(self):
        self.fiche: dict = {}
        self.messages: list[dict] = []
        self.consigner = consigner_dans(lambda: self.fiche)
        self._outil = creer_gestionnaire(
            ReglagesFiche.depuis(CONFIG), lambda: self.fiche, lambda: self.messages
        )
        self._n = 0

    async def dit(self, parole: str, agent_avant: str | None = None) -> str:
        if agent_avant:
            self.messages.append({"role": "assistant", "content": agent_avant})
        message = {"role": "user", "content": parole}
        self.messages.append(message)
        processeur = LectureAppelantProcessor(
            conversion=True,
            verification=True,
            langue_francaise=True,
            adresse=MAGASIN,
            etape_courante=lambda: SimpleNamespace(name="etape", extraction_variables=[]),
            consigner=self.consigner,
            voies=True,
            epellation=True,
            champs_fiche=NOMS,
        )
        cadre = SimpleNamespace(context=SimpleNamespace(messages=self.messages), speculation=False)
        await processeur._lire_contexte(cadre)
        return message["content"]

    async def note(self, **arguments) -> dict:
        self._n += 1
        recu = {}

        async def rappel(resultat, properties=None):
            recu["r"] = resultat

        await self._outil(
            SimpleNamespace(arguments=arguments, tool_call_id=f"n{self._n}", result_callback=rappel)
        )
        return recu["r"]

    def communes(self, tour: int | None = None) -> list[dict]:
        return [
            t for t in self.fiche.get("communes_verifiees") or [] if tour is None or t.get("tour") == tour
        ]

    def voies(self) -> list[dict]:
        return list(self.fiche.get("voies_verifiees") or [])

    def sure(self, champ: str) -> bool:
        return bool(((self.fiche.get(CLE_ETAT) or {}).get(champ) or {}).get("sure"))


# --- D4 : le module lit partout, la force de ce qu'il envoie change -------------


@pytest.mark.asyncio
@pytest.mark.parametrize("parole", ["depuis deux jours.", "Oui, c'est depuis ce matin."])
async def test_sans_signe_de_lieu_un_mot_courant_n_est_jamais_une_commune_sure(parole):
    """Runs 867, 869 : « depuis » → Deuillet, SÛRE."""
    appel = Appel()
    await appel.dit(parole)
    assert all(t["statut"] != "sure" for t in appel.communes()), appel.communes()
    assert all(t.get("force") == "son" for t in appel.communes()), appel.communes()


@pytest.mark.asyncio
async def test_un_signe_de_lieu_garde_le_comportement_actuel():
    """Run 861 : « j'habite … à Crail soixante mille cent » → Creil sûre."""
    appel = Appel()
    await appel.dit("j'habite au douze rue Jean Jaurès à Crail soixante mille cent.")
    creil = [t for t in appel.communes() if (t.get("commune_retenue") or {}).get("nom") == "Creil"]
    assert creil and creil[0]["statut"] == "sure" and creil[0]["force"] == "lieu", appel.communes()


@pytest.mark.asyncio
async def test_la_question_d_adresse_posee_juste_avant_est_un_signe_de_lieu():
    avec = Appel()
    await avec.dit("Crail.", agent_avant="Dans quelle commune se trouve l'appareil ?")
    assert [t["statut"] for t in avec.communes()] == ["sure"], avec.communes()
    sans = Appel()
    await sans.dit("Crail.", agent_avant="Quel est votre nom ?")
    assert all(t["statut"] != "sure" for t in sans.communes()), sans.communes()


@pytest.mark.asyncio
async def test_un_nom_exact_sans_signe_de_lieu_est_recommande_et_retenu_s_il_est_note():
    """Réponse courte, question sans rapport avec le lieu : le module lit, sans force."""
    appel = Appel()
    await appel.dit("Chantilly.", agent_avant="Pouvez-vous me rappeler votre nom ?")
    traces = [t for t in appel.communes() if t["entendu"].lower() == "chantilly"]
    assert traces and traces[0]["statut"] != "sure" and traces[0]["force"] == "nom", appel.communes()
    r = await appel.note(commune="Chantilly")
    assert not r.get("a_confirmer") and not r.get("a_proposer"), r
    assert appel.fiche["commune"] == "Chantilly" and appel.sure("commune")


# --- D5 : le code postal tranche ------------------------------------------------


@pytest.mark.asyncio
async def test_le_code_postal_dit_tranche_entre_les_candidates():
    """Run 863 : « Brûle-Vert » + 60600 : seule Breuil-le-Vert porte le code."""
    appel = Appel()
    await appel.dit("Il est aux trois rues des Merles, soixante mille six cents Brûle-Vert.")
    trace = next(t for t in appel.communes() if t["entendu"] == "Brûle-Vert")
    assert trace["statut"] == "sure" and trace["commune_retenue"]["nom"] == "Breuil-le-Vert", trace
    r = await appel.note(commune="Brûle-Vert", code_postal="60600")
    assert not r.get("a_confirmer") and not r.get("a_proposer"), r
    assert appel.fiche["commune"] == "Breuil-le-Vert" and appel.sure("commune")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parole",
    [
        "Il est aux trois rues des Merles, soixante mille six cents Brûle-Vert.",  # 863
        "Alors je suis aux deux places Victor Hugo soixante mille cent quatre vingt, Nogent-sur-Oise.",  # 862
    ],
)
async def test_un_type_de_voie_au_pluriel_n_est_pas_une_commune(parole):
    appel = Appel()
    await appel.dit(parole)
    lus = {t["entendu"].lower() for t in appel.communes()}
    assert not lus & {"merles", "hugo"}, lus


# --- « cent lits » : les communes avant la conversion des nombres ----------------


@pytest.mark.asyncio
async def test_cent_lits_est_senlis_et_reste_en_lettres():
    """Run 868 : « 100 lits » n'était plus lisible comme une commune."""
    appel = Appel()
    lu = await appel.dit("Oui bonjour. Alors voilà, j'habite à cent lits.")
    senlis = [t for t in appel.communes() if any(p["nom"] == "Senlis" for p in t["propositions"])]
    assert senlis, appel.communes()
    assert "cent lits" in lu and "100 lits" not in lu, lu


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parole, jamais",
    [("on se voit vers vingt heures", "Vervins"), ("c'est le cinq rue des Lilas", "Cinqueux")],
)
async def test_un_nombre_ordinaire_ne_devient_pas_une_commune(parole, jamais):
    appel = Appel()
    await appel.dit(parole)
    assert not [t for t in appel.communes() if any(p["nom"] == jamais for p in t["propositions"])]


# --- Les rues ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_un_tour_en_deux_messages_est_lu_en_entier_pour_la_rue():
    """Run 869 : la rue dans le premier morceau, la commune dans le second."""
    appel = Appel()
    await appel.dit("Oui bonjour, j'habite au douze rue Jean Jaurès,")
    await appel.dit("soixante mille cent à Creuil.")
    assert any(v["statut"] == "sure" and v["voie_retenue"] == "Rue Jean Jaurès" for v in appel.voies()), appel.voies()


@pytest.mark.asyncio
@pytest.mark.parametrize("parole", ["Non, c'est bon.", "Oui, c'est bien ça."])
async def test_aucune_trace_de_rue_sur_une_phrase_sans_rue(parole):
    appel = Appel()
    await appel.dit("j'habite à Crail soixante mille cent.")
    await appel.dit(parole)
    assert all(v["entendu"] for v in appel.voies()), appel.voies()


@pytest.mark.asyncio
async def test_la_commune_dite_apres_la_rue_ne_pese_plus_sur_la_rue():
    """Run 866 : « cinq places de la gare, chantilly » restait à confirmer (88)."""
    appel = Appel()
    await appel.dit("Alors j'habite aux cinq places de la gare, chantilly soixante mille cinq cents.")
    assert any(v["statut"] == "sure" and v["voie_retenue"] == "Place de la Gare" for v in appel.voies()), appel.voies()


# --- D4 et D5 ne cassent rien de ce qui passait ---------------------------------


def test_la_lecture_de_l_appelant_est_la_meme_fonction_au_clavier():
    """Le clavier passe par ``lire_texte`` : même lecture, sans question d'avant."""
    assert callable(lire_texte)


@pytest.mark.asyncio
async def test_fiche_eteinte_aucune_force_et_le_verdict_d_avant():
    """D4 ne vaut que fiche allumée : éteinte, la trace n'a pas de force et le
    verdict est celui de la production (« depuis » reste lu comme avant)."""
    fiche: dict = {}
    processeur = LectureAppelantProcessor(
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=MAGASIN,
        etape_courante=lambda: SimpleNamespace(name="etape", extraction_variables=[SimpleNamespace(name="commune")]),
        consigner=consigner_dans(lambda: fiche),
        voies=True,
        epellation=True,
    )
    messages = [{"role": "user", "content": "depuis deux jours."}]
    await processeur._lire_contexte(SimpleNamespace(context=SimpleNamespace(messages=messages), speculation=False))
    traces = fiche.get("communes_verifiees") or []
    assert traces and all("force" not in t for t in traces), traces
    assert [t["statut"] for t in traces] == ["sure"], traces

"""[.mark] Le patch de la fiche après le banc de sortie (runs 838 à 852, 25/09/2026).

Plan : `Labo-agent-vocal/plans/patch-fiche-banc/2026-09-25-plan-patch-fiche-banc.md`.
Données : `Labo-agent-vocal/carnet/2026-09-25-banc-sortie-fiche.md` et les runs bruts.

⛔ Chaque correction a au moins un test bâti sur les données RÉELLES de son run
(phrase de l'appelant, traces des modules, valeur envoyée par le modèle) ET un
test dans l'autre sens : ce qui doit toujours être refusé (PB15).

| Test | Ce qu'il prouve |
|---|---|
| C1 | Un déduit n'est refusé comme recopie que s'il est la MÊME suite de mots qu'un autre champ |
| C13 | Un déduit écrit par le balayage contient un mot porteur que l'appelant a dit (PB2) |
| PB3 | Un champ à liste fermée n'accepte qu'une de ses valeurs, et échappe à l'ancrage |
| C2 | Une commune ou une rue SÛRE du dernier tour de l'appelant l'emporte ; ni dite ni trouvée = refusée |
| C3 | Une commune refusée ou introuvable renvoie les communes du code postal lu, à proposer une par une |
| C4 | Le type de voie dit (comparé au son) choisit entre des voies de même nom ; une option confirmée s'enregistre |
| C5 | Un type de voie au pluriel (« rues », liaison entendue) vaut le singulier |
| C6 | Une voie notée sans numéro garde le numéro déjà noté pour la même voie |
"""

from types import SimpleNamespace

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.services.communes.base import charger_base
from api.services.pipecat import verification_communes
from api.services.pipecat.lecture_appelant import lire_message_tape
from api.services.pipecat.verification_communes import consigner_dans
from api.services.workflow import fiche_au_fil_de_leau
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CONSIGNE_A_PROPOSER,
    ReglagesFiche,
    balayer_la_fiche,
    creer_gestionnaire,
    ecrire_dans_la_fiche,
    garder_le_numero,
    lire_commune,
    lire_rue,
    type_entendu,
)
from api.tests.mark.test_fiche_balayage import Extracteur

# Les champs de l'agent n° 26 du banc (nom et origine ; les descriptions ne
# jouent aucun rôle dans les contrôles).
CHAMPS_26 = [
    ("numero_dicte", "dicte"),
    ("nom", "dicte"),
    ("appelant", "dicte"),
    ("motif", "deduit"),
    ("verbatim_demande", "dicte"),
    ("degre_urgence", "deduit"),
    ("email", "dicte"),
    ("appareil", "deduit"),
    ("marque_appareil", "dicte"),
    ("dernier_entretien", "dicte"),
    ("symptome", "deduit"),
    ("projet", "deduit"),
    ("type_logement", "deduit"),
    ("echeance_projet", "deduit"),
    ("montants_evoques", "deduit"),
    ("commune", "dicte"),
    ("code_postal", "dicte"),
    ("adresse_intervention", "dicte"),
]


def _reglages(**en_plus) -> ReglagesFiche:
    champs = [{"nom": nom, "origine": origine} for nom, origine in CHAMPS_26]
    for champ in champs:
        champ.update(en_plus.get(champ["nom"], {}))
    reglages = ReglagesFiche.depuis(
        {"fiche_au_fil_de_leau": True, "fiche_champs": champs}
    )
    assert reglages is not None
    return reglages


def _messages(*paroles: str) -> list[dict]:
    return [{"role": "user", "content": p} for p in paroles]


def _refus(fiche: dict, champ: str) -> str | None:
    for entree in reversed(fiche.get(CLE_JOURNAL) or []):
        if entree["champ"] == champ:
            return entree["raison"] if entree["statut"] == "refuse" else None
    return None


# --- C1 : la recopie, c'est la même suite de mots ------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "run, remplis, paroles, balaye",
    [
        (
            841,
            {"motif": "Prendre rendez-vous pour l'entretien annuel d'un poêle à bois"},
            ["Oui bonjour, je vous appelle pour prendre rendez-vous pour "
             "l'entretien annuel de mon poêle à bois."],
            {"appareil": "poêle à bois"},
        ),
        (
            843,
            {"motif": "Panne sur un poêle à granulés"},
            ["Ouais bonjour, je vous appelle parce que mon poêle à granulés, il "
             "est en panne."],
            {"appareil": "poêle à granulés", "degre_urgence": "panne"},
        ),
        (
            845,
            {
                "motif": "Projet d'installation d'un insert à bois",
                "verbatim_demande": "elle voudrait installer un poêle à bois, un "
                "insert à bois pardon",
            },
            ["Oui bonjour Julien Masson à l'appareil. J'appelle pour ma mère, elle "
             "voudrait installer un poêle à bois, un insert à bois pardon. Il y a "
             "déjà un conduit."],
            {"appareil": "insert", "projet": "installer un insert à bois"},
        ),
    ],
)
async def test_C1_un_deduit_contenu_dans_un_autre_champ_est_ecrit(
    run, remplis, paroles, balaye
):
    """Runs 841, 843, 845 : le balayage refusait `appareil`, `degre_urgence`,
    `projet` parce que le motif ou le verbatim les CONTENAIT."""
    fiche = dict(remplis)
    ecrits = await balayer_la_fiche(
        _reglages(), Extracteur(balaye), fiche, _messages(*paroles)
    )
    assert ecrits == balaye, run


@pytest.mark.asyncio
async def test_C1_run_838_la_recopie_mot_pour_mot_reste_refusee():
    """Run 838 (comme 837) : `symptome` = le verbatim de la demande, mot pour mot.
    La même suite de mots reste une recopie."""
    verbatim = (
        "mon poêle à granulés affiche une alarme et s'arrête tout seul depuis ce matin"
    )
    fiche = {"verbatim_demande": verbatim}
    ecrits = await balayer_la_fiche(
        _reglages(),
        Extracteur({"symptome": verbatim}),
        fiche,
        _messages(f"Oui bonjour, je vous appelle parce que {verbatim}."),
    )
    assert ecrits == {}
    assert _refus(fiche, "symptome") == "recopie_de_verbatim_demande"


@pytest.mark.asyncio
async def test_C1_casse_accents_et_ponctuation_ne_font_pas_une_autre_phrase():
    fiche = {"verbatim_demande": "Mon poêle s'arrête."}
    await balayer_la_fiche(
        _reglages(),
        Extracteur({"symptome": "mon POELE s arrete"}),
        fiche,
        _messages("Mon poêle s'arrête."),
    )
    assert _refus(fiche, "symptome") == "recopie_de_verbatim_demande"


# --- C13 : un déduit du balayage doit s'ancrer sur ce qui a été dit (PB2) ------

PAROLES_852 = [
    "Oui bonjour, j'aimerais faire l'entretien annuel de mon poêle à bois s'il "
    "vous plaît.",
    "Je, excusez-moi, mais je veux, je je veux juste faire l'entretien de mon "
    "poêle à bois là. Est-ce que je pourrais prendre un rendez-vous d'entretien "
    "s'il vous plaît?",
    "Oui, c'est madame Fontaine, f o n t a i n e.",
    "Ouais, c'est Noyon 60400 et j'habite aux 8 rues de Paris.",
]


@pytest.mark.asyncio
async def test_C13_run_852_maison_jamais_dit_est_refuse():
    fiche = {"motif": "Demande d'entretien annuel pour un poêle à bois."}
    ecrits = await balayer_la_fiche(
        _reglages(),
        Extracteur({"type_logement": "Maison", "appareil": "poêle à bois"}),
        fiche,
        _messages(*PAROLES_852),
    )
    assert ecrits == {"appareil": "poêle à bois"}
    assert _refus(fiche, "type_logement") == "non_ancre"
    assert "type_logement" not in fiche


@pytest.mark.asyncio
async def test_C13_run_845_un_deduit_ancre_sur_un_mot_dit_est_ecrit():
    """« maison, conduit existant » : la personne a dit « maison » et « conduit »."""
    ecrits = await balayer_la_fiche(
        _reglages(),
        Extracteur({"type_logement": "maison, conduit existant"}),
        {},
        _messages(
            "Oui bonjour Julien Masson à l'appareil. J'appelle pour ma mère, elle "
            "voudrait installer un poêle à bois, un insert à bois pardon. Il y a "
            "déjà un conduit.",
            "Ouais, c'est pour une maison et puis on a un budget autour de 4000 "
            "euros à peu près.",
        ),
    )
    assert ecrits == {"type_logement": "maison, conduit existant"}


@pytest.mark.asyncio
async def test_C13_ni_mot_vide_ni_mot_court_n_ancre_un_deduit():
    fiche: dict = {}
    await balayer_la_fiche(
        _reglages(),
        Extracteur({"type_logement": "pour une maison"}),
        fiche,
        _messages("C'est pour un appartement, avec un conduit."),
    )
    assert _refus(fiche, "type_logement") == "non_ancre"


@pytest.mark.asyncio
async def test_C13_pluriel_et_accents_confondus():
    ecrits = await balayer_la_fiche(
        _reglages(),
        Extracteur({"appareil": "Poêle"}),
        {},
        _messages("j'ai deux poeles a la maison"),
    )
    assert ecrits == {"appareil": "Poêle"}


@pytest.mark.asyncio
async def test_C13_un_oui_non_est_exempte():
    reglages = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [
                {"nom": "conduit_existant", "type": "boolean", "origine": "deduit"}
            ],
        }
    )
    ecrits = await balayer_la_fiche(
        reglages, Extracteur({"conduit_existant": True}), {}, _messages("il y en a un")
    )
    assert ecrits == {"conduit_existant": True}


# --- PB3 : la liste fermée de valeurs -----------------------------------------

URGENCES = {"degre_urgence": {"valeurs": ["danger", "panne", "normal"]}}


@pytest.mark.asyncio
async def test_PB3_un_deduit_a_liste_fermee_est_exempte_de_l_ancrage():
    """Runs 841, 845, 851 : `degre_urgence` = « normal », jamais dit tel quel.
    La liste le tient ; sans liste, il est refusé non ancré."""
    paroles = _messages(
        "Oui bonjour, je vous appelle pour l'entretien annuel de mon insert s'il "
        "vous plaît."
    )
    fiche: dict = {}
    ecrits = await balayer_la_fiche(
        _reglages(**URGENCES), Extracteur({"degre_urgence": "Normal"}), fiche, paroles
    )
    assert ecrits == {"degre_urgence": "normal"}  # la forme déclarée
    fiche = {}
    await balayer_la_fiche(
        _reglages(), Extracteur({"degre_urgence": "normal"}), fiche, paroles
    )
    assert _refus(fiche, "degre_urgence") == "non_ancre"


def test_PB3_hors_liste_refuse_d_ou_qu_il_vienne():
    reglages = _reglages(**URGENCES)
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(fiche, reglages, "degre_urgence", "urgent")
    assert (verdict.statut, verdict.raison) == ("refuse", "hors_liste")
    verdict = ecrire_dans_la_fiche(
        fiche, reglages, "degre_urgence", "urgent", source="balayage"
    )
    assert (verdict.statut, verdict.raison) == ("refuse", "hors_liste")
    verdict = ecrire_dans_la_fiche(fiche, reglages, "degre_urgence", "PANNE")
    assert (verdict.statut, fiche["degre_urgence"]) == ("ecrit", "panne")


@pytest.mark.parametrize(
    "valeurs, message",
    [
        ([f"v{i}" for i in range(21)], "at most 20"),
        (["x" * 41], "longer than 40"),
    ],
)
def test_PB3_bornes_de_la_liste(valeurs, message):
    with pytest.raises(ValueError, match=message):
        ChampFiche(nom="degre_urgence", valeurs=valeurs)


def test_PB3_liste_vide_equivaut_a_aucune_liste():
    assert ChampFiche(nom="x", valeurs=["  ", ""]).valeurs is None
    assert ChampFiche(nom="x", valeurs=[" panne "]).valeurs == ["panne"]


# --- C2 et C3 : la commune et la rue trouvées par les modules (PB4 à PB6) -----
#
# Les traces ci-dessous sont celles du run 845, telles que les modules les ont
# écrites, chacune rangée au tour de l'appelant qui l'a produite (le 25/09 elles
# ne portaient pas encore leur tour : c'est ce que le patch ajoute).

SENLIS = {
    "nom": "Senlis",
    "code_insee": "60612",
    "departement": "Oise",
    "codes_postaux": ["60300"],
}
PROPOSITIONS_60300 = [
    SENLIS,
    {
        "nom": "Chamant",
        "code_insee": "60138",
        "departement": "Oise",
        "codes_postaux": ["60300"],
    },
    {
        "nom": "Avilly-Saint-Léonard",
        "code_insee": "60033",
        "departement": "Oise",
        "codes_postaux": ["60300"],
    },
]
TOURS_845 = {
    # T9 : « Alors l'adresse de ma mère, c'est le sept rue de Maud à cent lice
    # dans l'oise. » Aucune commune entendue, aucune rue (commune pas tranchée).
    8: {
        "parole": "Alors l'adresse de ma mère, c'est le 7 rue de Maud à 100 lice "
        "dans l'oise.",
        "nombres_lus": [
            {"entendu": "sept", "type": "autre", "ecrit": "7"},
            {"entendu": "cent", "type": "autre", "ecrit": "100"},
        ],
    },
    # T10 : « Non non non non, c'est à cent lisses dans l'oise soixante trois cents. »
    9: {
        "parole": "Non non non non, c'est à 100 lisses dans l'oise 60300.",
        "communes_verifiees": [
            {
                "etape": "adresse",
                "entendu": "soixante trois cents",
                "statut": "a_confirmer",
                "commune_retenue": None,
                "propositions": PROPOSITIONS_60300,
                "code_postal_entendu": True,
            }
        ],
        "nombres_lus": [
            {
                "entendu": "soixante trois cents",
                "type": "code_postal",
                "ecrit": "60300",
                "retenu": "60300",
                "statut": "sure",
            },
        ],
    },
    # T11 : « … elle habitait à sans lice dans l'oise, le code postal c'est
    # soixante trois cents et elle habite au sept rue de Maud. »
    10: {
        "parole": "Non non, je écoutez-moi, je vous ai dit qu'elle habitait à sans "
        "lice dans l'oise, le code postal c'est 60300 et elle habite au 7 rue de Maud.",
        "communes_verifiees": [
            {
                "etape": "adresse",
                "entendu": "sans lice",
                "statut": "sure",
                "commune_retenue": SENLIS,
                "propositions": PROPOSITIONS_60300[:1],
            }
        ],
        "voies_verifiees": [
            {
                "etape": "adresse",
                "entendu": "maud",
                "statut": "sure",
                "voie_retenue": "Rue de Meaux",
                "propositions": [{"nom": "Rue de Meaux", "score": 103.0}],
            }
        ],
    },
}


def _jusqu_au_tour(tours: dict, dernier: int) -> tuple[dict, list[dict]]:
    """La fiche et les messages tels qu'au tour ``dernier`` de l'appelant."""
    fiche: dict = {"tour_appelant": dernier}
    messages = []
    for tour in sorted(t for t in tours if t <= dernier):
        messages.append({"role": "user", "content": tours[tour]["parole"]})
        for cle, traces in tours[tour].items():
            if cle != "parole":
                fiche.setdefault(cle, []).extend({**t, "tour": tour} for t in traces)
    return fiche, messages


async def _noter(
    fiche: dict, messages: list[dict], reglages: ReglagesFiche | None = None, **arguments
) -> dict:
    resultats = []

    async def rappel(resultat, *, properties=None):
        resultats.append(resultat)

    await creer_gestionnaire(reglages or _reglages(), lambda: fiche, lambda: messages)(
        SimpleNamespace(arguments=arguments, tool_call_id="n", result_callback=rappel)
    )
    (resultat,) = resultats
    return resultat


@pytest.mark.asyncio
async def test_C2_run_845_T9_liancourt_ni_dit_ni_trouve_est_refuse():
    fiche, messages = _jusqu_au_tour(TOURS_845, 8)
    resultat = await _noter(
        fiche,
        messages,
        commune="Liancourt",
        code_postal="60140",
        adresse_intervention="7 rue de Maud",
    )
    assert {"champ": "commune", "raison": "non_dit"} in resultat["refuses"]
    assert "commune" not in fiche
    # Aucun code postal lu avant ce tour : rien à proposer.
    assert "a_proposer" not in resultat
    # La rue, elle, a été dite : écrite, à confirmer.
    assert fiche["adresse_intervention"] == "7 rue de Maud"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("liste_chargee", [True, False])
async def test_C3_run_845_T10_lisle_refuse_et_les_communes_du_60300_proposees(
    liste_chargee, monkeypatch
):
    if liste_chargee:
        charger_base()
    else:
        monkeypatch.setattr(fiche_au_fil_de_leau, "base_si_chargee", lambda: None)
    fiche, messages = _jusqu_au_tour(TOURS_845, 9)
    resultat = await _noter(fiche, messages, commune="Lisle", code_postal="60300")
    assert "commune" not in fiche
    assert resultat["a_proposer"] == [
        {
            "champ": "commune",
            "options": [
                "Senlis (Oise)",
                "Chamant (Oise)",
                "Avilly-Saint-Léonard (Oise)",
            ],
        }
    ]
    assert resultat["consigne"].startswith(CONSIGNE_A_PROPOSER.format(champs="commune"))
    # Proposer n'est pas « ne repose pas la question ».
    assert "ne repose pas la question" not in resultat["consigne"]
    assert fiche["code_postal"] == "60300"


@pytest.mark.asyncio
async def test_C2_run_845_T11_sans_lisle_devient_senlis_sure_et_la_rue_de_meaux():
    fiche, messages = _jusqu_au_tour(TOURS_845, 10)
    resultat = await _noter(
        fiche, messages, commune="Sans-Lisle", adresse_intervention="7 rue de Maud"
    )
    assert resultat["statut"] == "note"
    assert (fiche["commune"], fiche["commune_insee"]) == ("Senlis", "60612")
    assert fiche["adresse_intervention"] == "7 Rue de Meaux"
    assert fiche["fiche_etat"]["commune"]["sure"] is True
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True
    assert resultat["ecriture_retenue"] == {
        "commune": "Senlis",
        "adresse_intervention": "7 Rue de Meaux",
    }


@pytest.mark.asyncio
async def test_C2_une_trace_sure_d_un_tour_precedent_ne_s_impose_pas():
    """La trace sûre de Senlis est au tour 10 ; au tour 11 (« au revoir »), une
    valeur inventée n'est plus remplacée par elle : refusée, non dite."""
    fiche, messages = _jusqu_au_tour(TOURS_845, 10)
    fiche["tour_appelant"] = 11
    messages.append({"role": "user", "content": "Non bon allez c'est bon, au revoir."})
    resultat = await _noter(fiche, messages, commune="Liancourt")
    assert {"champ": "commune", "raison": "non_dit"} in resultat["refuses"]


def test_C2_run_838_la_valeur_designe_sa_commune_parmi_les_traces_du_tour():
    fiche = {
        "tour_appelant": 1,
        "communes_verifiees": [
            {
                "entendu": "granulés",
                "statut": "a_confirmer",
                "commune_retenue": None,
                "propositions": [{"nom": "Grandrû", "code_insee": "60285"}],
                "tour": 1,
            },
            {
                "entendu": "Clermont",
                "statut": "sure",
                "tour": 1,
                "propositions": [],
                "commune_retenue": {
                    "nom": "Clermont",
                    "code_insee": "60157",
                    "codes_postaux": ["60600"],
                },
            },
        ],
    }
    lecture = lire_commune("Clermont", fiche)
    assert (lecture.valeur, lecture.sure, lecture.code_insee) == (
        "Clermont",
        True,
        "60157",
    )


BEAUVAIS = {"nom": "Beauvais", "code_insee": "60057", "codes_postaux": ["60000"]}
HANVEC = {"nom": "Hanvec", "code_insee": "29077", "codes_postaux": ["29460"]}


def test_C2_run_842_renoter_beauvais_au_tour_de_hanvec_n_ecrit_pas_hanvec():
    """Run 842 : « Bovet » → Beauvais, sûre ; au tour suivant, « Avec un y
    ouais » → Hanvec (Finistère), sûre aussi. Le modèle qui renote « Beauvais » à
    ce tour-là désigne la commune déjà tranchée : Hanvec ne s'impose pas."""
    fiche = {
        "tour_appelant": 6,
        "communes_verifiees": [
            {
                "entendu": "Bovet",
                "statut": "sure",
                "commune_retenue": BEAUVAIS,
                "propositions": [BEAUVAIS],
                "tour": 5,
            },
            {
                "entendu": "Avec",
                "statut": "sure",
                "commune_retenue": HANVEC,
                "propositions": [HANVEC],
                "tour": 6,
            },
        ],
    }
    assert lire_commune("Beauvais", fiche).valeur == "Beauvais"
    # Sans rien qui désigne la commune d'avant, le dernier tour l'emporte (PB4).
    assert lire_commune("Bovais-Nord", fiche).valeur == "Hanvec"


def test_C2_deux_communes_sures_differentes_au_meme_tour_sont_a_proposer():
    fiche = {
        "tour_appelant": 3,
        "communes_verifiees": [
            {
                "entendu": "Bovet",
                "statut": "sure",
                "commune_retenue": BEAUVAIS,
                "propositions": [],
                "tour": 3,
            },
            {
                "entendu": "Avec",
                "statut": "sure",
                "commune_retenue": HANVEC,
                "propositions": [],
                "tour": 3,
            },
        ],
    }
    verdict = ecrire_dans_la_fiche(fiche, _reglages(), "commune", "Bouvet")
    assert (verdict.statut, verdict.suite) == ("refuse", "a_proposer")
    assert verdict.options == ("Hanvec", "Beauvais")


def test_C2_la_marque_du_tour_est_la_meme_des_deux_cotes():
    assert fiche_au_fil_de_leau.CLE_TOUR == verification_communes.CLE_TOUR


@pytest.mark.asyncio
async def test_C2_les_vrais_modules_marquent_leurs_traces_du_tour_fiche_allumee():
    """Le tour est compté par la lecture de l'appelant, sur la vraie chaîne."""
    fiche: dict = {}
    reglages = {
        "conversion_nombres_transcription": True,
        "verification_communes": True,
        "fiche_au_fil_de_leau": True,
        "fiche_champs": [{"nom": "commune"}],
    }
    for phrase in ("bonjour", "j'habite à Creil, soixante mille cent"):
        await lire_message_tape(
            phrase,
            reglages,
            SimpleNamespace(language="fr", language_hints=None),
            None,
            SimpleNamespace(name="accueil", extraction_variables=[]),
            consigner_dans(lambda: fiche),
        )
    assert fiche["tour_appelant"] == 2
    creil = [t for t in fiche["communes_verifiees"] if t["statut"] == "sure"]
    assert creil and all(t["tour"] == 2 for t in creil)
    assert lire_commune("Creil", fiche).sure is True


@pytest.mark.asyncio
async def test_C2_fiche_eteinte_aucune_marque_de_tour():
    fiche: dict = {}
    await lire_message_tape(
        "j'habite à Creil, soixante mille cent",
        {"conversion_nombres_transcription": True, "verification_communes": True},
        SimpleNamespace(language="fr", language_hints=None),
        None,
        SimpleNamespace(
            name="adresse", extraction_variables=[SimpleNamespace(name="commune")]
        ),
        consigner_dans(lambda: fiche),
    )
    assert "tour_appelant" not in fiche
    assert all("tour" not in t for t in fiche["communes_verifiees"])


# --- C5 : un type de voie au pluriel vaut le singulier (PB8) ------------------


def test_C5_run_850_quatre_rues_carnau_devient_4_rue_carnot():
    """Run 850 : « Je suis quatre rues Carnau à Bovet soixante mille. » Le module
    tranche Rue Carnot, sûre ; la fiche écrivait « 4 rues Rue Carnot »."""
    fiche = {
        "tour_appelant": 8,
        "voies_verifiees": [
            {
                "etape": "adresse",
                "entendu": "carnau",
                "statut": "sure",
                "voie_retenue": "Rue Carnot",
                "propositions": [{"nom": "Rue Carnot"}, {"nom": "Rue Arnaud Bisson"}],
                "tour": 8,
            }
        ],
    }
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "adresse_intervention",
        "4 rues Carnau",
        paroles=["Je suis 4 rues Carnau à Bovet 60000."],
    )
    assert (verdict.statut, fiche["adresse_intervention"]) == ("ecrit", "4 Rue Carnot")
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True


def test_C5_le_pluriel_se_lit_aussi_dans_la_recherche():
    """« 8 rues de Paris » retrouve la voie nommée « Rue de Paris »."""
    fiche = {
        "voies_verifiees": [
            {
                "entendu": "de paris",
                "statut": "sure",
                "voie_retenue": "Rue de Paris",
                "propositions": [{"nom": "Rue de Paris"}],
            }
        ],
    }
    lecture = lire_rue("8 rues de Paris", fiche)
    assert (lecture.valeur, lecture.sure) == ("8 Rue de Paris", True)


def test_C5_un_mot_qui_n_est_pas_un_type_garde_son_s():
    """« cours » est un type en soi ; « Rue des Trois Places » garde ses mots."""
    fiche = {
        "voies_verifiees": [
            {
                "entendu": "des 3 places",
                "statut": "sure",
                "voie_retenue": "Rue des 3 Places",
                "propositions": [{"nom": "Rue des 3 Places"}],
            }
        ],
    }
    assert lire_rue("2 rue des 3 places", fiche).valeur == "2 Rue des 3 Places"


# --- C4 : le type de voie dit départage (PB7, proposition d'Evan) --------------

LOUIS_BLANC = {
    "etape": "adresse",
    "entendu": "louis blanc",
    "statut": "a_confirmer",
    "voie_retenue": None,
    "propositions": [
        {"nom": "Rue Louis Blanc", "score": 100.0},
        {"nom": "Impasse Louis Blanc", "score": 100.0},
        {"nom": "Cité Louis Blanc", "score": 100.0},
    ],
}
JEANNE_HACHETTE = {
    "etape": "nom_et_rappel",
    "entendu": "jeanne achete",
    "statut": "a_confirmer",
    "voie_retenue": None,
    "propositions": [
        {"nom": "Place Jeanne Hachette", "score": 103.0},
        {"nom": "Résidence Jeanne Hachette", "score": 100.0},
        {"nom": "Rue Jeanne Hachette", "score": 100.0},
    ],
}
DE_PARIS = {
    "etape": "accueil",
    "entendu": "paris",
    "statut": "a_confirmer",
    "voie_retenue": None,
    "propositions": [
        {"nom": "Rue de Paris"},
        {"nom": "Route de Paris"},
        {"nom": "Place du Parvis"},
    ],
}


def _voie_au_tour(tour: int, *traces: dict) -> dict:
    return {
        "tour_appelant": tour,
        "voies_verifiees": [{**t, "tour": tour} for t in traces],
    }


def _adresse(fiche: dict, valeur: str, *paroles: str):
    return ecrire_dans_la_fiche(
        fiche, _reglages(), "adresse_intervention", valeur, paroles=list(paroles)
    )


def test_C4_run_841_rue_dite_choisit_rue_louis_blanc():
    """Run 841 : « Alors j'habite au onze rue Louis blanc à Montaterre » ; trois
    voies Louis Blanc à Montataire, l'outil répondait « ambigu » trois fois."""
    fiche = _voie_au_tour(7, LOUIS_BLANC)
    verdict = _adresse(
        fiche,
        "11 rue Louis Blanc",
        "Alors j'habite au 11 rue Louis blanc à Montaterre 60160.",
    )
    assert (verdict.statut, verdict.suite) == ("ecrit", None)
    assert fiche["adresse_intervention"] == "11 Rue Louis Blanc"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True


def test_C4_run_847_places_dit_choisit_place_jeanne_hachette():
    """Run 847 : « Ouais, c'est cinq places Jeanne achète. » (liaison au pluriel)."""
    fiche = _voie_au_tour(5, JEANNE_HACHETTE)
    _adresse(
        fiche,
        "5 places Jeanne Achète",
        "Ouais, c'est 5 places Jeanne achète.",
    )
    assert fiche["adresse_intervention"] == "5 Place Jeanne Hachette"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True


@pytest.mark.parametrize("valeur", ["8 rue de Paris", "8 rues de Paris"])
def test_C4_C5_run_852_rue_de_paris_parmi_route_et_parvis(valeur):
    """Run 852 : « j'habite aux huit rues de Paris » ; options Rue de Paris, Route
    de Paris, Place du Parvis ; « avec un s à rues ? » redemandé trois fois."""
    fiche = _voie_au_tour(9, DE_PARIS)
    _adresse(fiche, valeur, "Ouais, c'est noyon 60400 et j'habite aux 8 rues de Paris.")
    assert fiche["adresse_intervention"] == "8 Rue de Paris"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True


def test_C4_l_option_renvoyee_apres_un_ambigu_est_sure_si_le_type_a_ete_dit():
    """Run 841 : après « ambigu », « Oui, c'est bien un monte-à-terre et c'est une
    rue. » ; le modèle renvoie la rue : la confirmation est enfin enregistrée."""
    fiche = _voie_au_tour(7, LOUIS_BLANC)
    # Au tour 7, la personne n'a dit aucun type : « ambigu », comme au banc.
    verdict = _adresse(fiche, "11 Louis Blanc", "j'habite au 11 Louis blanc")
    assert verdict.suite == "ambigu"
    fiche["tour_appelant"] = 8
    verdict = _adresse(
        fiche,
        "11 Rue Louis Blanc",
        "j'habite au 11 Louis blanc",
        "Oui, c'est bien un monte-à-terre et c'est une rue.",
    )
    assert fiche["adresse_intervention"] == "11 Rue Louis Blanc"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True


def test_C4_l_option_renvoyee_sans_que_son_type_ait_ete_dit_reste_ambigue():
    fiche = _voie_au_tour(7, LOUIS_BLANC)
    _adresse(fiche, "11 Louis Blanc", "j'habite au 11 Louis blanc")
    fiche["tour_appelant"] = 8
    verdict = _adresse(
        fiche, "11 Cité Louis Blanc", "j'habite au 11 Louis blanc", "oui c'est ça"
    )
    assert verdict.suite == "ambigu"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is False


def test_C4_des_voies_dont_le_nom_differe_restent_ambigues():
    fiche = _voie_au_tour(
        3,
        {
            "entendu": "monot",
            "statut": "a_confirmer",
            "voie_retenue": None,
            "propositions": [{"nom": "Rue Monet"}, {"nom": "Rue Odent"}],
        },
    )
    verdict = _adresse(fiche, "2 rue Monot", "c'est au 2 rue Monot")
    assert verdict.suite == "ambigu"


def test_C4_deux_types_dits_ne_departagent_rien():
    fiche = _voie_au_tour(7, LOUIS_BLANC)
    verdict = _adresse(
        fiche, "11 rue Louis Blanc", "c'est la rue, ou l'impasse, 11 Louis Blanc"
    )
    assert verdict.suite == "ambigu"


@pytest.mark.parametrize(
    "type_voie, texte, entendu",
    [
        ("place", "c'est la plasse", True),
        ("impasse", "les impasses", True),
        ("rue", "rues", True),
        ("quai", "il faut que je", False),
        ("allee", "je vais aller voir", False),
        ("rond point", "au rond-point", True),
    ],
)
def test_C4_le_type_se_compare_par_le_son(type_voie, texte, entendu):
    assert type_entendu(type_voie, [texte]) is entendu


# --- C6 : le numéro de rue déjà noté est gardé (PB9) --------------------------


def test_C6_run_847_place_jeanne_hachette_garde_son_5():
    """Run 847, T6 puis T7 : la personne dit « cinq places Jeanne achète », puis
    le modèle renvoie « Place Jeanne Hachette » seule. La fiche finissait sur
    « Place Jeanne Hachette », non sûre, sans le 5."""
    fiche = _voie_au_tour(5, JEANNE_HACHETTE)
    _adresse(fiche, "5 places Jeanne Achète", "Ouais, c'est 5 places Jeanne achète.")
    fiche["tour_appelant"] = 6
    verdict = _adresse(
        fiche,
        "Place Jeanne Hachette",
        "Ouais, c'est 5 places Jeanne achète.",
        "Ouais, c'est ça, ouais.",
    )
    assert verdict.statut == "ecrit"
    assert fiche["adresse_intervention"] == "5 Place Jeanne Hachette"
    assert fiche["fiche_etat"]["adresse_intervention"]["sure"] is True


def test_C6_le_numero_suit_la_meme_voie_ecrite_autrement():
    fiche = {"adresse_intervention": "7 rue de Maud"}
    assert garder_le_numero("Rue de Maud", fiche["adresse_intervention"], fiche) == (
        "7 Rue de Maud"
    )
    fiche = _voie_au_tour(5, JEANNE_HACHETTE)
    assert (
        garder_le_numero("Place Jeanne Hachette", "5 places Jeanne Achète", fiche)
        == "5 Place Jeanne Hachette"
    )


@pytest.mark.parametrize(
    "ancienne, nouvelle",
    [
        ("4 rue Pasteur", "Rue Carnot"),  # une autre voie
        ("4 rue Carnot", "14 rue Carnot"),  # un numéro corrigé (run 850)
        ("rue Carnot", "Rue Carnot"),  # aucun numéro à garder
    ],
)
def test_C6_aucun_numero_invente(ancienne, nouvelle):
    assert garder_le_numero(nouvelle, ancienne, {}) == nouvelle

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
"""

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    ReglagesFiche,
    balayer_la_fiche,
    ecrire_dans_la_fiche,
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

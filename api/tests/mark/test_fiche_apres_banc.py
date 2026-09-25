"""[.mark] Le patch de la fiche après le banc de sortie (runs 838 à 852, 25/09/2026).

Plan : `Labo-agent-vocal/plans/patch-fiche-banc/2026-09-25-plan-patch-fiche-banc.md`.
Données : `Labo-agent-vocal/carnet/2026-09-25-banc-sortie-fiche.md` et les runs bruts.

⛔ Chaque correction a au moins un test bâti sur les données RÉELLES de son run
(phrase de l'appelant, traces des modules, valeur envoyée par le modèle) ET un
test dans l'autre sens : ce qui doit toujours être refusé (PB15).

| Test | Ce qu'il prouve |
|---|---|
| C1 | Un déduit n'est refusé comme recopie que s'il est la MÊME suite de mots qu'un autre champ |
"""

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    ReglagesFiche,
    balayer_la_fiche,
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

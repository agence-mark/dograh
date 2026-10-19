"""[.mark] Chantier fiabilite-orchestration, lot 6 (R8, R9, G1 à G3) : la fiche qui refuse l'illisible.

Banc au casque du 19/10. Run 1466 : le « non » répondu à « avez-vous une adresse mail ? » écrit dans
`email`, marqué sûr, puis la bonne adresse refusée trois fois (D6, `non_sure_sur_sure`). Run 1468 :
un « oui » au même endroit, et le nom « Flamand » tiré de l'adresse par le balayage de fin d'appel.
Run 1466 encore : `verbatim_demande` pris sur la réplique qui répondait au jour.

| Test | La garantie |
|---|---|
| 1466 | « non » refusé pour le mail (greffier et outil), la vraie adresse écrite ensuite |
| 1468 | « oui » refusé pour le mail ; la vraie adresse, même non sûre, passe |
| D6 | une valeur illisible déjà écrite (avant ce contrôle) ne protège plus le champ |
| refus | « refusé » (le refus de la personne) reste permis pour le mail |
| fermée | « oui » / « non » jamais écrit dans un champ lu par un module (commune, rue, lexique) |
| nom | le nom jamais tiré du mail, ni par le greffier ni par le balayage ; dit pour lui, il passe |
| verbatim | la phrase prise sur la réplique du jour est refusée par le balayage ; une vraie demande passe |
| route | le balayage de fin d'appel passe par les mêmes contrôles que le greffier |
"""

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_JOURNAL,
    MODE_GREFFIER,
    ReglagesFiche,
    balayer_la_fiche,
    ecrire_dans_la_fiche,
)

CONFIG = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "description": "Nom de famille"},
        {"nom": "email", "description": "Adresse mail"},
        {"nom": "commune", "description": "Commune"},
        {"nom": "jour", "description": "Le jour"},
        {"nom": "verbatim_demande", "description": "La demande, mot pour mot"},
    ],
}


def _reglages() -> ReglagesFiche:
    reglages = ReglagesFiche.depuis(CONFIG)
    assert reglages is not None
    return reglages


def _raisons(fiche, champ):
    return [e["raison"] for e in fiche.get(CLE_JOURNAL, []) if e["champ"] == champ]


# --- 1466 et 1468 : le mail ---------------------------------------------------


@pytest.mark.parametrize("reponse", ["non", "oui", "Non.", "ouais"])
@pytest.mark.parametrize("source", [MODE_GREFFIER, "outil", "balayage"])
def test_un_oui_ou_un_non_n_est_jamais_une_adresse(reponse, source):
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "email", reponse, source=source, paroles=[reponse]
    )
    assert verdict.statut == "refuse" and verdict.raison == "pas_un_courriel"
    assert "email" not in fiche
    assert "email" not in fiche.get(CLE_ETAT, {})


def test_1466_le_non_refuse_puis_la_bonne_adresse_ecrite():
    """Avant : « non » écrit sûr, puis l'adresse refusée trois fois (`non_sure_sur_sure`)."""
    fiche: dict = {}
    reglages = _reglages()
    paroles = ["non", "flamantpierre5@gmail.com"]
    ecrire_dans_la_fiche(fiche, reglages, "email", "non", source=MODE_GREFFIER, paroles=paroles[:1])
    # Le greffier relit l'adresse : à faire confirmer (non sûre), mais écrite.
    verdict = ecrire_dans_la_fiche(
        fiche,
        reglages,
        "email",
        "flamantpierre5@gmail.com",
        sure=False,
        source=MODE_GREFFIER,
        paroles=paroles,
    )
    assert verdict.statut == "ecrit"
    assert fiche["email"] == "flamantpierre5@gmail.com"
    assert "non_sure_sur_sure" not in _raisons(fiche, "email")


def test_d6_une_valeur_illisible_deja_ecrite_ne_protege_plus_le_champ():
    """Une fiche née avant le contrôle : « non » sûr dans `email`. L'adresse arrive non sûre."""
    fiche = {
        "email": "non",
        "extracted_variables": {"email": "non"},
        CLE_ETAT: {"email": {"sure": True, "source": MODE_GREFFIER}},
    }
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "email",
        "flamantpierre5@gmail.com",
        sure=False,
        source=MODE_GREFFIER,
        paroles=["flamantpierre5@gmail.com"],
    )
    assert verdict.statut == "ecrit" and fiche["email"] == "flamantpierre5@gmail.com"


def test_d6_une_adresse_valide_et_sure_reste_protegee():
    fiche = {
        "email": "paul@gmail.com",
        "extracted_variables": {"email": "paul@gmail.com"},
        CLE_ETAT: {"email": {"sure": True, "source": "outil"}},
    }
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "email",
        "pierre@gmail.com",
        sure=False,
        source=MODE_GREFFIER,
        paroles=["pierre@gmail.com"],
    )
    assert verdict.statut == "refuse" and verdict.raison == "non_sure_sur_sure"
    assert fiche["email"] == "paul@gmail.com"


def test_le_refus_de_la_personne_reste_permis_pour_le_mail():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "email", "refusé", source="outil", paroles=["je préfère pas"]
    )
    assert verdict.statut == "ecrit" and fiche["email"] == "refusé"


def test_un_oui_ou_un_non_n_est_jamais_une_commune():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "commune", "oui", source="outil", paroles=["oui"]
    )
    assert verdict.statut == "refuse" and verdict.raison == "reponse_a_une_question_fermee"
    assert "commune" not in fiche


# --- 1468 : le nom tiré du mail -------------------------------------------------

PAROLES_1468 = [
    "oui j'ai une adresse mail",
    "c'est flamand pierre 5 arobase gmail point com",
]


def test_le_greffier_ne_tire_pas_le_nom_du_mail():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "nom", "Flamand", source=MODE_GREFFIER, paroles=PAROLES_1468
    )
    assert verdict.statut == "refuse" and verdict.raison == "non_dit"
    assert "nom" not in fiche


@pytest.mark.asyncio
async def test_1468_le_balayage_ne_tire_pas_le_nom_du_mail():
    class Extracteur:
        async def __call__(self, variables, consigne):
            return {"nom": "Flamand"}

    fiche: dict = {"email": "flamandpierre5@gmail.com"}
    messages = [{"role": "user", "content": p} for p in PAROLES_1468]
    ecrits = await balayer_la_fiche(_reglages(), Extracteur(), fiche, messages)
    assert "nom" not in ecrits and "nom" not in fiche
    assert "non_dit" in _raisons(fiche, "nom")


def test_le_nom_dit_pour_lui_passe_meme_s_il_est_dans_le_mail():
    fiche: dict = {"email": "flamandpierre5@gmail.com"}
    paroles = [*PAROLES_1468, "mon nom de famille c'est Flamand"]
    verdict = ecrire_dans_la_fiche(
        fiche, _reglages(), "nom", "Flamand", source=MODE_GREFFIER, paroles=paroles
    )
    assert verdict.statut == "ecrit" and fiche["nom"] == "Flamand"


def test_le_nom_tire_de_l_adresse_deja_ecrite_est_refuse_meme_sans_adresse_dans_les_paroles():
    """L'adresse est dans la fiche (écrite par l'outil) ; la parole qui la portait n'est plus lue
    comme une adresse : le nom n'a de source que cette adresse."""
    fiche: dict = {"email": "flamandpierre5@gmail.com"}
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "nom",
        "Flamand",
        source="balayage",
        paroles=["flamandpierre5 chez gmail"],
    )
    assert verdict.statut == "refuse"
    assert "nom" not in fiche


# --- 1466 : le verbatim de la demande ------------------------------------------


class _Extracteur:
    def __init__(self, reponse):
        self.reponse = reponse

    async def __call__(self, variables, consigne):
        return dict(self.reponse)


@pytest.mark.asyncio
async def test_1466_le_verbatim_n_est_pas_pris_sur_la_replique_du_jour():
    fiche = {"jour": "2026-10-22", "jour_dit": "jeudi prochain"}
    messages = [
        {"role": "assistant", "content": "Quel jour vous arrange ?"},
        {"role": "user", "content": "jeudi prochain, si c'est possible"},
    ]
    ecrits = await balayer_la_fiche(
        _reglages(), _Extracteur({"verbatim_demande": "jeudi prochain, si c'est possible"}), fiche, messages
    )
    assert "verbatim_demande" not in ecrits and "verbatim_demande" not in fiche
    assert "reponse_a_jour" in _raisons(fiche, "verbatim_demande")


@pytest.mark.asyncio
async def test_une_vraie_demande_est_gardee_par_le_balayage():
    fiche = {"jour": "2026-10-22", "jour_dit": "jeudi prochain"}
    demande = "je voudrais faire entretenir mon poêle avant l'hiver, il siffle depuis une semaine"
    messages = [
        {"role": "user", "content": demande},
        {"role": "user", "content": "jeudi prochain, si c'est possible"},
    ]
    ecrits = await balayer_la_fiche(
        _reglages(), _Extracteur({"verbatim_demande": demande}), fiche, messages
    )
    assert ecrits == {"verbatim_demande": demande}
    assert fiche["verbatim_demande"] == demande

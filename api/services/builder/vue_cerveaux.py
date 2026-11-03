"""[.mark] Builder, K7 : ce que les onglets « Builder IA », « Appelant simulé » et « Juge » des Réglages du Labo lisent de chaque cerveau.

Tout vient des vraies données : le prompt système est l'élément de la bibliothèque que le code lit vraiment (``methode``, ``consigne``,
``grille-juge``) avec sa version et son statut ; « ce qu'il reçoit » est la liste des blocs que le code injecte (chaque ligne renvoie au
module qui la fabrique) et, quand la donnée existe, si elle est présente ; les portes comptent les actions du registre de chaque porte ;
les limites du juge sont les constantes du juge.

Les identifiants (``cle``) sont des mots courts : l'écran les met en phrases, en deux langues.
"""

from __future__ import annotations

from loguru import logger
from pydantic import BaseModel

from api.services import sources_cerveaux
from api.services.builder import consignes, contexte, depense, options
from api.services.builder.actions.registre import REGISTRE
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.familles import FAMILLE_CONVENTIONS, FAMILLE_METHODE, FAMILLES
from api.services.builder.cerveau import reglages as reglages_cerveau
from api.services.builder.tests_agent import juge as juge_des_tests


class VuePrompt(BaseModel):
    famille: str
    libelle_famille: str
    slug: str
    titre: str | None = None  # None : l'élément n'est pas en bibliothèque, le texte du code sert de secours
    version: int | None = None
    statut: str | None = None


class VueRecu(BaseModel):
    cle: str
    present: bool | None = None  # None : toujours injecté, rien à constater


class VueCerveauLu(BaseModel):
    prompt: VuePrompt
    recoit: list[VueRecu]


class VuePorte(BaseModel):
    ouverte: bool
    actions: int


class VuePortes(BaseModel):
    ecran: VuePorte
    claude_code: VuePorte
    source_du_builder: str  # « cle_api » ou « claude_code » (Réglages > Sources)


class VueLimitesDuJuge(BaseModel):
    passes_max: int
    seuil_de_confiance: float
    notes_min: int
    accord_min: float


class VueCerveaux(BaseModel):
    builder: VueCerveauLu
    appelant: VueCerveauLu
    juge: VueCerveauLu
    builder_actif: bool
    portes: VuePortes
    depense_du_mois: float
    plafond_du_mois: float
    limites_du_juge: VueLimitesDuJuge


# Ce que le code injecte, et où il le fabrique (le test relit ces correspondances).
# Appelant : tests_agent/jeu.py (consigne_de_l_appelant, jouer_une_conversation). Juge : tests_agent/juge.py (_une_passe) ; le verdict
# du code est posé avant lui (verdict.py).
RECU_DE_L_APPELANT = ("personnage", "comportements", "scenario", "repliques")
RECU_DU_JUGE = ("transcription", "criteres", "verdict_du_code")


async def _prompt(famille: str, slug: str) -> VuePrompt:
    base = VuePrompt(famille=famille, libelle_famille=FAMILLES[famille].libelle, slug=slug)
    try:
        element = await service.element_ou_none(famille, slug)
    except Exception as erreur:  # noqa: BLE001 -- une bibliothèque illisible ne coupe pas l'écran des réglages
        logger.debug(f"[cerveaux] {famille}/{slug} illisible : {type(erreur).__name__}")
        return base
    if element is None:
        return base
    return base.model_copy(update={"titre": element.titre, "version": element.courante.numero, "statut": element.courante.statut.value})


async def _present(famille: str, slug: str) -> bool:
    try:
        element = await service.element_ou_none(famille, slug)
    except Exception:  # noqa: BLE001
        return False
    return element is not None and element.courante.statut.value != "rejete"


async def lire(user, organisation: int) -> VueCerveaux:
    reglages = await reglages_cerveau.lire(organisation)
    o = await options.lire(organisation)
    preferences = await contexte.preferences(getattr(user, "id", None))
    builder = VueCerveauLu(
        prompt=await _prompt(FAMILLE_METHODE, "methode"),
        recoit=[
            VueRecu(cle="methode"),
            VueRecu(cle="conventions", present=await _present(FAMILLE_CONVENTIONS, contexte.CONVENTIONS_SLUG)),
            VueRecu(cle="recette_de_l_agent"),  # methode.section_de_la_recette : la recette indiquée sur l'agent
            VueRecu(cle="preferences", present=bool((preferences or "").strip())),
            VueRecu(cle="etat_de_l_agent"),  # contexte.etat_du_disque : fiche, conception, changements, derniers tests
            VueRecu(cle="recettes_a_la_demande", present="recette_lire" in REGISTRE),
        ],
    )
    appelant = VueCerveauLu(
        prompt=await _prompt(consignes.FAMILLE_APPELANT, consignes.SLUG_APPELANT), recoit=[VueRecu(cle=c) for c in RECU_DE_L_APPELANT]
    )
    juge = VueCerveauLu(prompt=await _prompt(consignes.FAMILLE_JUGE, consignes.SLUG_JUGE), recoit=[VueRecu(cle=c) for c in RECU_DU_JUGE])
    portes = VuePortes(
        ecran=VuePorte(ouverte=not o.builder_coupe and not o.porte_ecran_coupee, actions=len([a for a in REGISTRE.values() if a.moteur])),
        claude_code=VuePorte(
            ouverte=not o.builder_coupe and not o.porte_claude_code_coupee, actions=len([a for a in REGISTRE.values() if a.mcp])
        ),
        source_du_builder=await sources_cerveaux.source_de(organisation, "builder", reglages.source),
    )
    return VueCerveaux(
        builder=builder,
        appelant=appelant,
        juge=juge,
        builder_actif=not o.builder_coupe,
        portes=portes,
        depense_du_mois=await depense.du_mois(organisation),
        plafond_du_mois=reglages.plafond_mois,
        limites_du_juge=VueLimitesDuJuge(
            passes_max=juge_des_tests.PASSES_MAX,
            seuil_de_confiance=juge_des_tests.SEUIL_DE_CONFIANCE,
            notes_min=juge_des_tests.NOTES_MIN,
            accord_min=juge_des_tests.ACCORD_MIN,
        ),
    )


__all__ = ["VueCerveaux", "lire"]

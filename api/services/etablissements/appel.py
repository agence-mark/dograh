"""[.mark] Which establishment a call serves, and what it inherits (E2, E3, E4).

Read once when the call is set up, BEFORE the opening state, the address and
the announcement are injected: those three keep their own functions, they are
simply handed the values the inheritance resolved.

The inheritance (E2): the most precise value wins, agent > establishment >
organization.

- hours: the agent's own if it has any, else the establishment's;
- address: the agent's, else the establishment's, else the organization's (the
  last step is ``resoudre_adresse``, unchanged);
- announcement: each sentence of the establishment replaces the organization's;
  the forced state stays the organization's.

Which establishment (E3):

- a phone call: the one whose numbers hold the CALLED number. A number attached
  to no establishment: no establishment, the call is the call of before;
- a test (browser, keyboard, simulated caller -- no called number): the one
  chosen in the test window (``etablissement_id`` in the context), else the
  first the agent serves through its numbers, else the organization's first.

⛔ Zero loss (E4, X2): an organization with no establishment, or a call that
matches none, gets back exactly the configuration and context it gave. Nothing
here raises: on any problem, no establishment.

[.mark] Chantier agents-specialises, lot 1 (= lot 1 du plan fiche-etablissement,
F1, F3, F4, C2, C3, C5). The order a call's establishment is resolved in:

1. the FICHE the agent chose (``etablissement_id`` in its settings) -- source
   ``fiche_de_lagent``; a chosen fiche that no longer exists = no establishment,
   with a warning, never an error;
2. else the fiche the call already carries (``etablissement_de_lappel`` in the call
   context, written at pick-up when the first agent has a fiche, read by an agent
   reached through a handoff and by the tools) -- source ``appel``;
3. else the old path above (called number, test window, first), for an agent not
   yet taken over;
4. else none: the call of before.

A fiche (1 or 2) inherits NOTHING (C3): its hours, address and announcements are
what the agent reads, an empty field is empty. Its immediate closure wins for its
agents, else the organization's « close everything » applies (C5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from api.schemas.base_client import Equipe
from api.schemas.etablissements import (
    CatalogueEtablissements,
    Etablissement,
    EtablissementsDeLagent,
    EtablissementServi,
    ValeurHeritee,
)
from api.schemas.phrases import CataloguePhrases

CLE_ETABLISSEMENT_CHOISI = "etablissement_id"
# [.mark] Lot 1 (F1) : la fiche choisie par l'agent, dans SES réglages (même nom de clé
# que le choix de la fenêtre d'essai, mais dans un autre dictionnaire).
CLE_FICHE_DE_LAGENT = "etablissement_id"
# [.mark] Lot 1 (C2 ②) : la fiche que l'appel porte, dans le contexte de l'appel.
CLE_FICHE_DE_LAPPEL = "etablissement_de_lappel"
# Les sources d'une fiche, qui n'hérite de rien (C3).
SOURCES_FICHE = ("fiche_de_lagent", "appel")
# Clé interne de la configuration résolue : l'adresse ne retombe pas sur l'organisation.
CLE_SANS_HERITAGE = "_mark_fiche_sans_heritage"
CLE_NOM = "etablissement"
CLE_NUMERO_TRANSFERT = "numero_transfert"
CLE_HORAIRES = "horaires_ouverture"
CLE_ADRESSE = "adresse_etablissement"


@dataclass
class EtablissementDeLappel:
    """The establishment a call serves, and how it was found."""

    etablissement: Etablissement
    source: str  # fiche_de_lagent | appel | numero_appele | essai | premier_de_lagent | premier
    lu_depuis: str  # copie | stockage
    origines: dict[str, str] = field(default_factory=dict)

    @property
    def sans_heritage(self) -> bool:
        """[.mark] Lot 1 (C3) : une fiche (choisie par l'agent, ou portée par l'appel)
        n'hérite de rien."""
        return self.source in SOURCES_FICHE

    def estampille(self) -> dict:
        return {
            "id": self.etablissement.id,
            "nom": self.etablissement.nom,
            "source": self.source,
            "lu_depuis": self.lu_depuis,
            "origines": dict(self.origines),
        }


def _vide(valeur) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def _normaliser(numero) -> str | None:
    if not isinstance(numero, str) or not numero.strip():
        return None
    try:
        from api.utils.telephony_address import normalize_telephony_address

        return normalize_telephony_address(numero, country_hint="FR").canonical
    except Exception:  # noqa: BLE001
        return numero.strip()


def par_numero_appele(
    catalogue: CatalogueEtablissements, numero_appele
) -> Etablissement | None:
    cible = _normaliser(numero_appele)
    if not cible:
        return None
    for etablissement in catalogue.etablissements:
        if cible in etablissement.numeros:
            return etablissement
    return None


def choisir_etablissement(
    catalogue: CatalogueEtablissements,
    contexte: dict,
    numeros_de_lagent: list[str] | None = None,
    fiche_choisie: str | None = None,
) -> tuple[Etablissement, str] | None:
    """E3, pure. ``numeros_de_lagent``: the canonical numbers whose inbound agent
    is this one (used for tests only). ``fiche_choisie``: the fiche the agent chose
    in its settings ([.mark] lot 1, F1), tried first."""
    if not catalogue.etablissements:
        return None
    # [.mark] Lot 1 (C2 ①) : la fiche de l'agent. Disparue : aucune fiche, jamais d'erreur.
    if isinstance(fiche_choisie, str) and fiche_choisie.strip():
        for etablissement in catalogue.etablissements:
            if etablissement.id == fiche_choisie.strip():
                return etablissement, "fiche_de_lagent"
        logger.warning(
            f"[.mark] The agent's fiche « {fiche_choisie} » no longer exists: no establishment"
        )
        return None
    # [.mark] Lot 1 (C2 ②) : la fiche que l'appel porte déjà (passation, outils).
    de_lappel = contexte.get(CLE_FICHE_DE_LAPPEL)
    if isinstance(de_lappel, str) and de_lappel:
        for etablissement in catalogue.etablissements:
            if etablissement.id == de_lappel:
                return etablissement, "appel"
    numero_appele = contexte.get("called_number")
    if not _vide(numero_appele):
        trouve = par_numero_appele(catalogue, numero_appele)
        return (trouve, "numero_appele") if trouve else None
    # No called number: a test, or a call type that never carries one.
    choisi = contexte.get(CLE_ETABLISSEMENT_CHOISI)
    if isinstance(choisi, str) and choisi:
        for etablissement in catalogue.etablissements:
            if etablissement.id == choisi:
                return etablissement, "essai"
    for numero in numeros_de_lagent or []:
        trouve = par_numero_appele(catalogue, numero)
        if trouve:
            return trouve, "premier_de_lagent"
    return catalogue.etablissements[0], "premier"


def configuration_heritee(
    run_configs: dict | None,
    etablissement: Etablissement | None,
    *,
    sans_heritage: bool = False,
) -> tuple[dict, dict]:
    """The agent's configuration with the establishment's values where the agent
    has none, and the origin of each. A copy: the agent's dict is never changed.
    Without an establishment, the SAME dict comes back (zero loss).

    [.mark] Lot 1 (F3, C3) : ``sans_heritage`` (une fiche) : les horaires et l'adresse de
    la fiche SEULE, même si l'agent a les siens ; un champ vide de la fiche est vide."""
    configs = run_configs or {}
    if etablissement is None:
        return run_configs, {}
    effective = dict(configs)
    origines: dict[str, str] = {}
    if sans_heritage:
        if etablissement.horaires_ouverture:
            effective[CLE_HORAIRES] = etablissement.horaires_ouverture
            origines["horaires_ouverture"] = "fiche"
        else:
            effective.pop(CLE_HORAIRES, None)
            origines["horaires_ouverture"] = "aucune"
        if etablissement.adresse is not None:
            effective[CLE_ADRESSE] = etablissement.adresse.model_dump(mode="json")
            origines["adresse"] = "fiche"
        else:
            effective.pop(CLE_ADRESSE, None)
            origines["adresse"] = "aucune"
        effective[CLE_SANS_HERITAGE] = True
        return effective, origines
    if not _vide(configs.get(CLE_HORAIRES)):
        origines["horaires_ouverture"] = "agent"
    elif etablissement.horaires_ouverture:
        effective[CLE_HORAIRES] = etablissement.horaires_ouverture
        origines["horaires_ouverture"] = "etablissement"
    else:
        origines["horaires_ouverture"] = "aucune"
    if configs.get(CLE_ADRESSE):
        origines["adresse"] = "agent"
    elif etablissement.adresse is not None:
        effective[CLE_ADRESSE] = etablissement.adresse.model_dump(mode="json")
        origines["adresse"] = "etablissement"
    else:
        origines["adresse"] = "organisation"
    return effective, origines


def annonce_heritee(reglages, etablissement: Etablissement | None, *, sans_heritage: bool = False):
    """The organization's announcement with the establishment's sentences.

    [.mark] Lot 1 (C3, C5) : ``sans_heritage`` (une fiche) : les annonces de la fiche
    seule (vide = rien n'est annoncé) ; sa fermeture immédiate l'emporte, sinon celle de
    l'organisation (« tout fermer ») reste."""
    if etablissement is None or reglages is None:
        return reglages
    if sans_heritage:
        surcharge = {
            "annonce_fermeture": etablissement.annonce_fermeture or "",
            "annonce_pause": etablissement.annonce_pause or "",
        }
        if getattr(etablissement, "etat_force", None):
            surcharge["etat_force"] = etablissement.etat_force
            surcharge["etat_force_jusqu_a"] = etablissement.etat_force_jusqu_a
        try:
            return reglages.model_copy(update=surcharge)
        except Exception:  # noqa: BLE001
            return reglages
    surcharge = {
        cle: getattr(etablissement, cle)
        for cle in ("annonce_fermeture", "annonce_pause")
        if getattr(etablissement, cle) is not None
    }
    if not surcharge:
        return reglages
    try:
        return reglages.model_copy(update=surcharge)
    except Exception:  # noqa: BLE001
        return reglages


def injecter_etablissement(contexte: dict, servi: EtablissementDeLappel | None) -> dict:
    """``etablissement`` (its name) and ``numero_transfert`` in the context.
    A value already there is kept (a replay, a pre-call fetch). Never raises."""
    if servi is None:
        return contexte
    try:
        enrichi = dict(contexte)
        valeurs = {CLE_NOM: servi.etablissement.nom}
        # [.mark] Lot 1 (C2 ②) : l'appel porte sa fiche, pour l'agent appelé et les outils.
        if servi.sans_heritage:
            valeurs[CLE_FICHE_DE_LAPPEL] = servi.etablissement.id
        if servi.etablissement.numero_transfert:
            valeurs[CLE_NUMERO_TRANSFERT] = servi.etablissement.numero_transfert
        for cle, valeur in valeurs.items():
            if _vide(enrichi.get(cle)):
                enrichi[cle] = valeur
        return enrichi
    except Exception as erreur:  # noqa: BLE001
        logger.error(f"[.mark] Establishment not injected, the call goes on without it: {erreur!r}")
        return contexte


async def _numeros_de_lagent(organization_id: int, workflow_id: int | None) -> list[str]:
    if workflow_id is None:
        return []
    from api.db import db_client

    lignes = await db_client.lister_numeros_de_lorganisation(organization_id)
    return [adresse for adresse, _libelle, agent, _nom, actif in lignes if agent == workflow_id and actif]


@dataclass
class LectureDeLappel:
    """What a call reads at pick-up from the copy: its establishment (or none) and the
    organization's catalogue of sentences (E5), which applies with or without one."""

    servi: EtablissementDeLappel | None = None
    phrases: CataloguePhrases = field(default_factory=CataloguePhrases)
    # l-agent-collegue, C3: the team read with them (empty without a client database).
    equipe: Equipe = field(default_factory=Equipe)
    lu_depuis: str = "aucune"
    # [.mark] Lot 5 (M5): the name of each fiche, for the places on the team's lines.
    noms_des_lieux: dict[str, str] = field(default_factory=dict)

    @property
    def etablissement_id(self) -> str | None:
        return self.servi.etablissement.id if self.servi else None


async def lire_lappel(
    organization_id: int | None,
    workflow_id: int | None,
    contexte: dict,
    *,
    fiche_choisie: str | None = None,
) -> LectureDeLappel:
    """Read the copy once, choose the establishment. Never raises: on any problem,
    no establishment and no sentence -- the call of before. ``fiche_choisie``: the
    fiche in the agent's settings ([.mark] lot 1, F1)."""
    try:
        from api.services.etablissements.copie import lire_copie_complete

        copie = await lire_copie_complete(organization_id)
        lecture = LectureDeLappel(
            phrases=copie.phrases, equipe=copie.equipe, lu_depuis=copie.lu_depuis
        )
        catalogue = copie.etablissements
        lecture.noms_des_lieux = {e.id: e.nom for e in catalogue.etablissements}
        if not catalogue.etablissements:
            return lecture
        numeros = []
        if (
            not fiche_choisie
            and not (contexte or {}).get(CLE_FICHE_DE_LAPPEL)
            and _vide((contexte or {}).get("called_number"))
            and not (contexte or {}).get(CLE_ETABLISSEMENT_CHOISI)
        ):
            numeros = await _numeros_de_lagent(organization_id, workflow_id)
        choix = choisir_etablissement(catalogue, contexte or {}, numeros, fiche_choisie)
        if choix is not None:
            etablissement, source = choix
            lecture.servi = EtablissementDeLappel(
                etablissement=etablissement, source=source, lu_depuis=copie.lu_depuis
            )
        return lecture
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Establishment of the call not resolved, none used: {erreur!r}")
        return LectureDeLappel()


async def etablissement_de_lappel(
    organization_id: int | None,
    workflow_id: int | None,
    contexte: dict,
    *,
    fiche_choisie: str | None = None,
) -> EtablissementDeLappel | None:
    """The establishment alone (screen and tools). ``None`` on any problem."""
    return (
        await lire_lappel(organization_id, workflow_id, contexte, fiche_choisie=fiche_choisie)
    ).servi


# --------------------------------------------------------------------------- #
# The agent's screen: the establishments it serves, values resolved (E2, E8)
# --------------------------------------------------------------------------- #


def _valeur(agent, etablissement, organisation) -> ValeurHeritee:
    for valeur, origine in ((agent, "agent"), (etablissement, "etablissement"), (organisation, "organisation")):
        if not _vide(valeur):
            return ValeurHeritee(valeur=valeur, origine=origine)
    return ValeurHeritee()


def etablissements_de_lagent(
    catalogue: CatalogueEtablissements,
    numeros_de_lagent: list[str],
    run_configs: dict | None,
    adresse_organisation: str | None,
    annonce_organisation,
) -> EtablissementsDeLagent:
    """The same resolution as the call, for the screen: one source of truth."""
    from api.services.communes.adresse import _adresse_de, texte_adresse

    configs = run_configs or {}
    # [.mark] Lot 1 (F1, C3) : un agent qui a choisi sa fiche lit la fiche seule.
    fiche = configs.get(CLE_FICHE_DE_LAGENT)
    if isinstance(fiche, str) and fiche.strip():
        trouvee = next((e for e in catalogue.etablissements if e.id == fiche.strip()), None)
        if trouvee is None:
            return EtablissementsDeLagent(
                fiche_de_lagent=fiche.strip(), fiche_introuvable=True, numeros_de_lagent=list(numeros_de_lagent)
            )

        def de_la_fiche(valeur) -> ValeurHeritee:
            return ValeurHeritee(valeur=valeur, origine="fiche") if not _vide(valeur) else ValeurHeritee()

        return EtablissementsDeLagent(
            fiche_de_lagent=trouvee.id,
            numeros_de_lagent=list(numeros_de_lagent),
            etablissements=[
                EtablissementServi(
                    id=trouvee.id,
                    nom=trouvee.nom,
                    numeros=trouvee.numeros,
                    horaires_ouverture=de_la_fiche(trouvee.horaires_ouverture),
                    adresse=de_la_fiche(texte_adresse(trouvee.adresse) if trouvee.adresse else None),
                    annonce_fermeture=de_la_fiche(trouvee.annonce_fermeture),
                    annonce_pause=de_la_fiche(trouvee.annonce_pause),
                    numero_transfert=de_la_fiche(trouvee.numero_transfert),
                )
            ],
        )
    adresse_agent = _adresse_de(configs.get(CLE_ADRESSE), "Agent")
    servis: list[EtablissementServi] = []
    sans: list[str] = []
    for numero in numeros_de_lagent:
        etablissement = par_numero_appele(catalogue, numero)
        if etablissement is None:
            sans.append(numero)
            continue
        if any(s.id == etablissement.id for s in servis):
            continue
        servis.append(
            EtablissementServi(
                id=etablissement.id,
                nom=etablissement.nom,
                numeros=etablissement.numeros,
                horaires_ouverture=_valeur(configs.get(CLE_HORAIRES), etablissement.horaires_ouverture, None),
                adresse=_valeur(
                    texte_adresse(adresse_agent) if adresse_agent else None,
                    texte_adresse(etablissement.adresse) if etablissement.adresse else None,
                    adresse_organisation,
                ),
                annonce_fermeture=_valeur(
                    None, etablissement.annonce_fermeture, getattr(annonce_organisation, "annonce_fermeture", None)
                ),
                annonce_pause=_valeur(
                    None, etablissement.annonce_pause, getattr(annonce_organisation, "annonce_pause", None)
                ),
                numero_transfert=_valeur(None, etablissement.numero_transfert, None),
            )
        )
    return EtablissementsDeLagent(
        etablissements=servis, numeros_sans_etablissement=sans, numeros_de_lagent=list(numeros_de_lagent)
    )

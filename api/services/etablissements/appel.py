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
CLE_NOM = "etablissement"
CLE_NUMERO_TRANSFERT = "numero_transfert"
CLE_HORAIRES = "horaires_ouverture"
CLE_ADRESSE = "adresse_etablissement"


@dataclass
class EtablissementDeLappel:
    """The establishment a call serves, and how it was found."""

    etablissement: Etablissement
    source: str  # numero_appele | essai | premier_de_lagent | premier
    lu_depuis: str  # copie | stockage
    origines: dict[str, str] = field(default_factory=dict)

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
) -> tuple[Etablissement, str] | None:
    """E3, pure. ``numeros_de_lagent``: the canonical numbers whose inbound agent
    is this one (used for tests only)."""
    if not catalogue.etablissements:
        return None
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


def configuration_heritee(run_configs: dict | None, etablissement: Etablissement | None) -> tuple[dict, dict]:
    """The agent's configuration with the establishment's values where the agent
    has none, and the origin of each. A copy: the agent's dict is never changed.
    Without an establishment, the SAME dict comes back (zero loss)."""
    configs = run_configs or {}
    if etablissement is None:
        return run_configs, {}
    effective = dict(configs)
    origines: dict[str, str] = {}
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


def annonce_heritee(reglages, etablissement: Etablissement | None):
    """The organization's announcement with the establishment's sentences."""
    if etablissement is None or reglages is None:
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

    @property
    def etablissement_id(self) -> str | None:
        return self.servi.etablissement.id if self.servi else None


async def lire_lappel(
    organization_id: int | None,
    workflow_id: int | None,
    contexte: dict,
) -> LectureDeLappel:
    """Read the copy once, choose the establishment. Never raises: on any problem,
    no establishment and no sentence -- the call of before."""
    try:
        from api.services.etablissements.copie import lire_copie_complete

        copie = await lire_copie_complete(organization_id)
        lecture = LectureDeLappel(
            phrases=copie.phrases, equipe=copie.equipe, lu_depuis=copie.lu_depuis
        )
        catalogue = copie.etablissements
        if not catalogue.etablissements:
            return lecture
        numeros = []
        if _vide((contexte or {}).get("called_number")) and not (contexte or {}).get(CLE_ETABLISSEMENT_CHOISI):
            numeros = await _numeros_de_lagent(organization_id, workflow_id)
        choix = choisir_etablissement(catalogue, contexte or {}, numeros)
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
) -> EtablissementDeLappel | None:
    """The establishment alone (screen and tools). ``None`` on any problem."""
    return (await lire_lappel(organization_id, workflow_id, contexte)).servi


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
    return EtablissementsDeLagent(etablissements=servis, numeros_sans_etablissement=sans)

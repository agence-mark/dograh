"""[.mark] The after-call settings (chantier l-agent-travaille, L4, A1 to A10).

Two levels (A6):

- ``ReglagesApresAppel``: the ORGANIZATION's settings, ``organization_configurations``
  key ``APRES_APPEL`` (no migration): the summary model and its key, the mail server,
  the recap hours, and each module's settings (custom webhook; SMS and connectors
  arrive with L5 and L6).
- ``ApresAppelAgent``: what an AGENT switches on (``workflow_configurations.apres_appel``).
  ⛔ Off by default (X2): an agent that switches nothing on is not touched; the
  after-call of before (webhooks, QA) runs as it did.

Passwords and secrets are never stored here: a reference ``mark-cle:<uuid>`` to the
« Keys » library (A4 SMTP password, A7 webhook secret, A3 summary key).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from api.services.cles_reference import est_reference

_ADRESSE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
MODULES_CONNUS = ("webhook", "connecteurs", "sms")

# The names of the steps, in their order on screen (A9).
ETAPES = ("ecriture", "synthese", "mail")

MODELE_SYNTHESE_DEFAUT = "mistral-small-latest"


def verifier_adresses(valeurs: list[str]) -> list[str]:
    """Trimmed, de-duplicated, each a plausible mail address (refused otherwise)."""
    propres: list[str] = []
    for brute in valeurs or []:
        adresse = (brute or "").strip()
        if not adresse:
            continue
        if len(adresse) > 254 or not _ADRESSE.match(adresse):
            raise ValueError(f"« {adresse} » is not a mail address.")
        if adresse.lower() not in {a.lower() for a in propres}:
            propres.append(adresse)
    if len(propres) > 20:
        raise ValueError("At most 20 addresses.")
    return propres


def _reference_ou_vide(valeur: str | None) -> str | None:
    if valeur is None or not str(valeur).strip():
        return None
    if not est_reference(valeur):
        raise ValueError("Choose the key in the « Keys » library (never typed here).")
    return valeur


class ReglagesSynthese(BaseModel):
    modele: str = Field(
        default=MODELE_SYNTHESE_DEFAUT,
        min_length=1,
        max_length=100,
        description="Mistral model of the summary (A3): a smaller one than the agent's, its own rate limit.",
    )
    cle: str | None = Field(
        default=None,
        description="The client's Mistral key, a reference to the « Keys » library.",
    )
    nom_assistant: str | None = Field(
        default=None,
        max_length=60,
        description="How the summary names the voice assistant. Empty: « the voice assistant ».",
    )
    nom_entreprise: str | None = Field(
        default=None,
        max_length=120,
        description="The company the assistant answers for. Empty: not named.",
    )
    consigne: str | None = Field(
        default=None,
        max_length=8000,
        description="The summary's instructions. Empty: the generic instructions written in the code.",
    )

    @field_validator("cle")
    @classmethod
    def _cle(cls, valeur: str | None) -> str | None:
        return _reference_ou_vide(valeur)


class ReglagesSmtp(BaseModel):
    """A generic mail server (Q1: the service is chosen at the Scaleway migration)."""

    hote: str | None = Field(default=None, max_length=200)
    port: int = Field(default=587, ge=1, le=65535)
    securite: Literal["starttls", "ssl", "aucune"] = "starttls"
    utilisateur: str | None = Field(default=None, max_length=200)
    mot_de_passe: str | None = Field(
        default=None, description="A reference to the « Keys » library."
    )
    expediteur: str | None = Field(default=None, max_length=254)
    nom_expediteur: str | None = Field(default=None, max_length=120)

    @field_validator("mot_de_passe")
    @classmethod
    def _mdp(cls, valeur: str | None) -> str | None:
        return _reference_ou_vide(valeur)

    @field_validator("expediteur")
    @classmethod
    def _expediteur(cls, valeur: str | None) -> str | None:
        if valeur is None or not valeur.strip():
            return None
        return verifier_adresses([valeur])[0]

    @property
    def configure(self) -> bool:
        return bool(self.hote and self.expediteur)


class ReglagesRecapitulatif(BaseModel):
    actif: bool = False
    heures: list[int] = Field(
        default_factory=lambda: [8],
        max_length=24,
        description="Hours of the day (0-23, the organization's timezone) the recap leaves.",
    )

    @field_validator("heures")
    @classmethod
    def _heures(cls, valeurs: list[int]) -> list[int]:
        for h in valeurs:
            if not 0 <= h <= 23:
                raise ValueError("An hour is between 0 and 23.")
        return sorted(set(valeurs))


class ReglagesWebhook(BaseModel):
    """A7: a custom n8n workflow after the call. The organization travels in the secret
    of the header, never as a field the model fills."""

    url: str | None = Field(default=None, max_length=2000)
    secret: str | None = Field(
        default=None, description="A reference to the « Keys » library."
    )

    @field_validator("secret")
    @classmethod
    def _secret(cls, valeur: str | None) -> str | None:
        return _reference_ou_vide(valeur)

    @field_validator("url")
    @classmethod
    def _url(cls, valeur: str | None) -> str | None:
        if valeur is None or not valeur.strip():
            return None
        valeur = valeur.strip()
        if not re.match(r"^https?://[^\s]+$", valeur):
            raise ValueError(
                "The address starts with https:// (or http:// on a local network)."
            )
        return valeur


class ReglagesApresAppel(BaseModel):
    format: Literal["apres-appel-mark"] = "apres-appel-mark"
    version: Literal[1] = 1
    synthese: ReglagesSynthese = Field(default_factory=ReglagesSynthese)
    smtp: ReglagesSmtp = Field(default_factory=ReglagesSmtp)
    recapitulatif: ReglagesRecapitulatif = Field(default_factory=ReglagesRecapitulatif)
    webhook: ReglagesWebhook = Field(default_factory=ReglagesWebhook)


# --------------------------------------------------------------------------- #
# What an agent switches on
# --------------------------------------------------------------------------- #

# The record's fields the after-call reads, by role. Default: a field of the same name.
ROLES_DE_LA_FICHE = (
    "nom",
    "prenom",
    "mail",
    "motif",
    "degre_urgence",
    "type_demande",
    "numero_rappel",
)


# --------------------------------------------------------------------------- #
# The SMS of an agent (L6, plan sms-recapitulatif D1 to D11)
# --------------------------------------------------------------------------- #

LONGUEUR_SMS = 160
# A sender name Twilio accepts in France: 1 to 11 letters, digits or spaces, one letter at least.
_EXPEDITEUR = re.compile(r"^(?=.*[A-Za-z])[A-Za-z0-9 ]{1,11}$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def numero_e164(brut: str | None) -> str | None:
    """« 06 12 34 56 78 », « +33 6… », « 0033 6… » → « +33612345678 »; None when it is
    not a number. A national number without its country is read as French."""
    if not brut:
        return None
    chiffres = re.sub(r"[\s.\-()]", "", str(brut))
    if chiffres.startswith("00"):
        chiffres = "+" + chiffres[2:]
    elif re.fullmatch(r"0[1-9]\d{8}", chiffres):
        chiffres = "+33" + chiffres[1:]
    return chiffres if _E164.match(chiffres) else None


def est_un_mobile(e164: str | None) -> bool:
    """D4: a French mobile (06, 07). A foreign number is not taken (no SMS): telling a
    foreign mobile from a landline needs ``phonenumbers``, not in the image (R5)."""
    return bool(e164 and re.fullmatch(r"\+33[67]\d{8}", e164))


class SmsEnvoi(BaseModel):
    actif: bool = Field(default=False, description="Send this SMS after each call (off by default).")
    texte: str | None = Field(
        default=None,
        max_length=480,
        description="The text with blanks ({{nom}}, {{motif}}…), filled by the record. Cut to 160 characters once filled.",
    )

    @model_validator(mode="after")
    def _texte_si_actif(self):
        self.texte = (self.texte or "").strip() or None
        if self.actif and not self.texte:
            raise ValueError("An SMS switched on needs its text.")
        return self


class SmsEquipe(SmsEnvoi):
    numeros: list[str] = Field(default_factory=list, max_length=5, description="The team's mobile numbers.")

    @field_validator("numeros")
    @classmethod
    def _numeros(cls, valeurs: list[str]) -> list[str]:
        propres = []
        for brut in valeurs:
            numero = numero_e164(brut)
            if numero is None:
                raise ValueError(f"« {brut} » is not a phone number.")
            if not est_un_mobile(numero):
                raise ValueError(f"« {brut} » is not a French mobile number (06, 07).")
            if numero not in propres:
                propres.append(numero)
        return propres

    @model_validator(mode="after")
    def _numeros_si_actif(self):
        if self.actif and not self.numeros:
            raise ValueError("The team SMS needs one number at least.")
        return self


class SmsAgent(BaseModel):
    """D1 to D11: sent by the client's Twilio after the call, never written by the model."""

    expediteur: str | None = Field(
        default=None,
        description="The sender name (« NUANCESFEU », 11 characters at most). Empty: the number of « Telephony ».",
    )
    appelant: SmsEnvoi = Field(default_factory=SmsEnvoi)
    equipe: SmsEquipe = Field(default_factory=SmsEquipe)

    @field_validator("expediteur")
    @classmethod
    def _expediteur(cls, valeur: str | None) -> str | None:
        valeur = (valeur or "").strip() or None
        if valeur and not _EXPEDITEUR.match(valeur):
            raise ValueError("A sender name is 1 to 11 letters, digits or spaces, with one letter at least.")
        return valeur


class ApresAppelAgent(BaseModel):
    """What this agent's calls do after the call (A6). Off by default (X2)."""

    actif: bool = Field(
        default=False,
        description=(
            "Write each call in the client's database, then summarise it and mail the "
            "request, in the background after the call. Off: nothing is written, nothing "
            "is sent, the agent behaves exactly as before."
        ),
    )
    synthese: bool = Field(default=True, description="Summarise the call (A3).")
    mail: bool = Field(
        default=True, description="Mail each request to its recipients (A4)."
    )
    modules: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="The organization's modules this agent uses (custom webhook…).",
    )
    champs: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Which field of the record holds each role (name, first name, mail, reason, "
            "urgency, request type, call-back number). Empty: the field of the same name."
        ),
    )

    sms: SmsAgent = Field(default_factory=SmsAgent, description="The SMS of the module « sms » (L6).")

    @field_validator("modules")
    @classmethod
    def _modules(cls, valeurs: list[str]) -> list[str]:
        propres = []
        for nom in valeurs:
            if nom not in MODULES_CONNUS:
                raise ValueError(f"Unknown module « {nom} ».")
            if nom not in propres:
                propres.append(nom)
        return propres

    @field_validator("champs")
    @classmethod
    def _champs(cls, valeurs: dict[str, str]) -> dict[str, str]:
        propres = {}
        for role, champ in (valeurs or {}).items():
            if role not in ROLES_DE_LA_FICHE:
                raise ValueError(f"Unknown role « {role} ».")
            champ = (champ or "").strip()
            if champ and champ != role:
                if not re.match(r"^[A-Za-z][A-Za-z0-9_]{0,63}$", champ):
                    raise ValueError(f"« {champ} » is not a field name.")
                propres[role] = champ
        return propres

    def champ(self, role: str) -> str:
        return self.champs.get(role) or role


# --------------------------------------------------------------------------- #
# The section « After the call » of the run window (A9)
# --------------------------------------------------------------------------- #

StatutEtape = Literal["en_attente", "en_cours", "ok", "echec", "ignoree"]


class EtapeApresAppel(BaseModel):
    nom: str
    statut: StatutEtape
    tentatives: int = 0
    definitive: bool = False
    detail: str | None = None
    le: datetime | None = None
    envois: list[dict] = Field(default_factory=list)


class ApresAppelDuRun(BaseModel):
    actif: bool = Field(
        description="False: this run's agent does not use the after-call."
    )
    etapes: list[EtapeApresAppel] = Field(default_factory=list)
    appel_id: int | None = None
    demande_id: int | None = None
    synthese: str | None = None
    autre_demande_ouverte_id: int | None = None


class AdressesNotification(BaseModel):
    """A5, PN6: the organization's addresses (only its own calls) and the .mark ones of
    the installation (everything, read-only on screen)."""

    organisation: list[str] = Field(default_factory=list)
    installation: list[str] = Field(default_factory=list)


class EssaiMail(BaseModel):
    destinataire: str

    @model_validator(mode="after")
    def _adresse(self):
        self.destinataire = verifier_adresses([self.destinataire])[0]
        return self

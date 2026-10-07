"""[.mark] The common .mark model, the objects the first connector needs (plan connecteurs-agent D16).

An action reads THIS, never the agent's raw record: one translator per software, from the
common model to the software. The full model (the hub) is a later chantier; here, the contact,
its address and the appointment's reason. Which record field holds each one is the agent's
setting (``apres_appel.champs``, L4): no trade word in the code.
"""

from __future__ import annotations

from dataclasses import dataclass

from api.schemas.apres_appel import ApresAppelAgent


@dataclass(frozen=True)
class Contact:
    nom: str | None = None
    prenom: str | None = None
    mail: str | None = None
    telephone: str | None = None


@dataclass(frozen=True)
class Adresse:
    voie: str | None = None
    code_postal: str | None = None
    commune: str | None = None

    def texte(self) -> str | None:
        morceaux = [
            m
            for m in (
                self.voie,
                " ".join(x for x in (self.code_postal, self.commune) if x),
            )
            if m
        ]
        return ", ".join(morceaux) or None


@dataclass(frozen=True)
class ModeleDeLAppel:
    contact: Contact
    adresse: Adresse
    motif: str | None = None
    urgence: str | None = None


def _texte(valeur) -> str | None:
    if valeur in (None, "", [], {}):
        return None
    return str(valeur)


def depuis_la_fiche(
    fiche: dict, agent: ApresAppelAgent | None, numero: str | None = None
) -> ModeleDeLAppel:
    agent = agent or ApresAppelAgent()
    lire = lambda role: _texte(fiche.get(agent.champ(role)))
    return ModeleDeLAppel(
        contact=Contact(
            nom=lire("nom"),
            prenom=lire("prenom"),
            mail=lire("mail"),
            telephone=lire("numero_rappel") or numero,
        ),
        adresse=Adresse(
            voie=_texte(fiche.get("voie") or fiche.get("adresse")),
            code_postal=_texte(fiche.get("code_postal")),
            commune=_texte(fiche.get("commune")),
        ),
        motif=lire("motif"),
        urgence=lire("degre_urgence"),
    )

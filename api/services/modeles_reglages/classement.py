"""[.mark] Settings templates: which setting goes in a template, which stays with the agent (M6).

⛔ ONE list of keys, never two: the keys of a template are read from ``groupe/reglages.py``
(``CLES_THEME_*``, whose union is ``CLES_COMMUNES``, and ``CLES_PROPRES``). This module only adds
what those lists cannot say:

- the SECTION a key belongs to (its screen theme, so the sections ticked at application are the
  themes the user knows);
- the keys M6 keeps with the agent although the group copies them (prompts, tools, the client's
  data, lists tied to the graph), each with its reason;
- the sub-keys kept with the agent inside a key that is otherwise a template setting.

A key neither in a section, nor excluded, nor "own to the agent" is an unclassified key: the sweep
test (``test_modeles_de_reglages.py``) fails on it, so a setting added tomorrow is made to be sorted.
Sorting rule (M6): a BEHAVIOUR setting goes to the template; a piece of the client's DATA stays with
the agent. The ambiguous cases are listed below with their reason and reported in the journal.

Pure: no database, nothing raised, no business word -- setting names only.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

from api.services.groupe.reglages import (
    CLES_COMMUNES,
    CLES_PROPRES,
    CLES_THEME_AGENT,
    CLES_THEME_BRIQUES,
    CLES_THEME_DONNEES,
    CLES_THEME_ECOUTE,
    CLES_THEME_ETABLISSEMENT,
    CLES_THEME_INTERVENTIONS,
    CLES_THEME_MODULES,
    CLES_THEME_RYTHME,
    CLES_THEME_TOUR,
    CLES_THEME_VOIX,
)

# The sections, in screen order. The identifiers are those of the screen themes
# (``ui/src/components/mark/reglages-agent/Theme*.tsx``, ``ID_THEME_*``).
SECTIONS: dict[str, tuple[str, ...]] = {
    "agent": CLES_THEME_AGENT,
    "briques": CLES_THEME_BRIQUES,
    "ecoute": CLES_THEME_ECOUTE,
    # cloture-code, F8 (M4): the modules' keys, moved out of « Écoute » and « Données de l'appel ».
    "modules": CLES_THEME_MODULES,
    "tour": CLES_THEME_TOUR,
    "voix": CLES_THEME_VOIX,
    "rythme": CLES_THEME_RYTHME,
    "donnees": CLES_THEME_DONNEES,
    "etablissement": CLES_THEME_ETABLISSEMENT,
    # Lot 8 de builder-agent-vocal : les interventions du moteur.
    "interventions": CLES_THEME_INTERVENTIONS,
}

# M6: the keys the group copies (so "common") that a template nevertheless leaves to the agent.
EXCLUES_DU_MODELE: dict[str, str] = {
    # Prompts and the agent's own sentences.
    "travail_consigne": "prompt",
    "greffier_consigne": "prompt",
    "user_idle_prompt": "prompt",
    "user_idle_goodbye_prompt": "prompt",
    "transfert_humain": "phrase",
    # Tools of the organization (identifiers that mean nothing elsewhere).
    "travail_outils": "outils",
    # The client's data: vocabulary, names of the graph's variables, fields of the record, outcomes.
    "dictionary": "donnee-client",
    "tts_replacements": "donnee-client",
    "variables_reference": "variables-du-graphe",
    "variables_commune": "variables-du-graphe",
    "variables_telephone": "variables-du-graphe",
    "variables_code_postal": "variables-du-graphe",
    "variables_courriel": "variables-du-graphe",
    "variables_date": "variables-du-graphe",
    "fiche_champs": "variables-du-graphe",
    "call_dispositions": "donnee-client",
    "external_pbx_field_mappings": "donnee-client",
    "external_pbx_lead_headers": "donnee-client",
    # Recipients, mail server, second number, answer messages and recordings, classifier credentials.
    "apres_appel": "donnee-client",
    "panne": "donnee-client",
    "voicemail_detection": "messages-enregistrements-et-cles",
}

# Inside a key that is a template setting, the sub-keys that stay with the agent (the client's words).
SOUS_CLES_EXCLUES: dict[str, tuple[str, ...]] = {
    "attente": ("phrase_pont",),
}

# These keys exclude one another on an agent (a full configuration, or per-service overlays): a
# template sets them together or not at all, so the agent never ends up with half of a pair.
GROUPES_ATOMIQUES: tuple[tuple[str, ...], ...] = (
    ("model_overrides", "model_configuration_v2_override", "mark_per_service_override"),
)

# Names of the secret fields. The first five are the fork's (``masking.SERVICE_SECRET_FIELDS``);
# the others are belt and braces for a provider block that would carry a secret under another name.
CHAMPS_SECRETS: tuple[str, ...] = (
    "api_key",
    "credentials",
    "aws_access_key",
    "aws_secret_key",
    "aws_session_token",
    "secret",
    "client_secret",
    "password",
    "token",
)
# Review of the chantier: a secret under another name (``auth_token``, ``access_token``, ``api_secret``,
# ``private_key``…) is recognised by a word of its name, never let through by an exact list.
MOTS_SECRETS: frozenset[str] = frozenset({"key", "token", "secret", "password", "credentials", "credential"})


def est_un_champ_secret(nom: Any) -> bool:
    if not isinstance(nom, str):
        return False
    return nom in CHAMPS_SECRETS or any(mot in MOTS_SECRETS for mot in nom.lower().split("_"))


def section_de(cle: str) -> str | None:
    """The section of a template setting, or ``None`` (excluded, own to the agent, unknown)."""
    if cle in EXCLUES_DU_MODELE:
        return None
    for section, cles in SECTIONS.items():
        if cle in cles:
            return section
    return None


def cles_de_la_section(section: str) -> list[str]:
    """The settings a template can hold in this section (the excluded ones left out)."""
    return [c for c in SECTIONS.get(section, ()) if c not in EXCLUES_DU_MODELE]


def cles_du_modele() -> list[str]:
    """Every setting a template can hold, in screen order."""
    return [c for section in SECTIONS for c in cles_de_la_section(section)]


def est_classee(cle: str) -> bool:
    """Template setting, kept by the agent for a reason, or own to the agent."""
    return section_de(cle) is not None or cle in EXCLUES_DU_MODELE or cle in CLES_PROPRES


def cles_sans_classement(cles: Iterable[str]) -> list[str]:
    """The given keys that are classified nowhere: what the sweep test refuses."""
    return sorted(c for c in cles if not est_classee(c))


def groupe_atomique_de(cle: str) -> tuple[str, ...] | None:
    for groupe in GROUPES_ATOMIQUES:
        if cle in groupe:
            return groupe
    return None


# --------------------------------------------------------------------------- #
# Keys of access: a template never carries one (M3)
# --------------------------------------------------------------------------- #


def retirer_les_cles(valeur: Any) -> Any:
    """A deep copy of ``valeur`` without any secret field, at any depth. A reference to a key of the
    organization's library lives in ``api_key``: it goes with it (a reference means nothing elsewhere)."""
    if isinstance(valeur, Mapping):
        return {k: retirer_les_cles(v) for k, v in valeur.items() if not est_un_champ_secret(k)}
    if isinstance(valeur, list):
        return [retirer_les_cles(v) for v in valeur]
    return copy.deepcopy(valeur)


def premiere_cle_trouvee(valeur: Any, chemin: str = "") -> str | None:
    """The path of the first secret field found in ``valeur`` (a file that carries one is refused)."""
    if isinstance(valeur, Mapping):
        for k, v in valeur.items():
            ici = f"{chemin}.{k}" if chemin else str(k)
            if est_un_champ_secret(k):
                return ici
            trouve = premiere_cle_trouvee(v, ici)
            if trouve:
                return trouve
    elif isinstance(valeur, list):
        for i, v in enumerate(valeur):
            trouve = premiere_cle_trouvee(v, f"{chemin}[{i}]")
            if trouve:
                return trouve
    return None


def reporter_les_cles(entrant: Any, existant: Any) -> None:
    """Copies, into ``entrant``, the secret fields ``existant`` holds at the same place, when the same
    provider is meant (or none is named): the agent keeps its OWN keys when a template is applied (M3).
    Fields ``entrant`` already has are never replaced. Mutates ``entrant``."""
    if not isinstance(entrant, dict) or not isinstance(existant, Mapping):
        return
    if entrant.get("provider") == existant.get("provider"):
        for champ in [c for c in existant if est_un_champ_secret(c)]:
            if existant.get(champ) is not None and champ not in entrant:
                entrant[champ] = copy.deepcopy(existant[champ])
    for cle, valeur in entrant.items():
        if isinstance(valeur, dict) and isinstance(existant.get(cle), Mapping):
            reporter_les_cles(valeur, existant[cle])


def fournisseurs_sans_cle(valeur: Any) -> list[str]:
    """The providers named in ``valeur`` (a block with a ``provider``) that hold no secret field."""
    trouves: list[str] = []

    def _parcourir(noeud: Any) -> None:
        if isinstance(noeud, Mapping):
            fournisseur = noeud.get("provider")
            if isinstance(fournisseur, str) and not any(est_un_champ_secret(c) for c in noeud):
                if fournisseur not in trouves:
                    trouves.append(fournisseur)
            for v in noeud.values():
                _parcourir(v)
        elif isinstance(noeud, list):
            for v in noeud:
                _parcourir(v)

    _parcourir(valeur)
    return trouves


# --------------------------------------------------------------------------- #
# What a template keeps of one setting
# --------------------------------------------------------------------------- #


def valeur_pour_le_modele(cle: str, valeur: Any) -> Any:
    """The value as a template holds it: no key of access, no sub-key left to the agent."""
    propre = retirer_les_cles(valeur)
    if isinstance(propre, dict):
        for sous_cle in SOUS_CLES_EXCLUES.get(cle, ()):
            propre.pop(sous_cle, None)
    return propre


def valeur_pour_lagent(cle: str, valeur_du_modele: Any, valeur_de_lagent: Any) -> Any:
    """The value an agent receives: the template's, with the sub-keys it keeps (its own words) put back."""
    nouvelle = copy.deepcopy(valeur_du_modele)
    if isinstance(nouvelle, dict):
        for sous_cle in SOUS_CLES_EXCLUES.get(cle, ()):
            if isinstance(valeur_de_lagent, Mapping) and sous_cle in valeur_de_lagent:
                nouvelle[sous_cle] = copy.deepcopy(valeur_de_lagent[sous_cle])
    return nouvelle


def sections_presentes(valeurs: Mapping[str, Any]) -> list[str]:
    """The sections that hold at least one setting, in screen order."""
    return [s for s in SECTIONS if any(c in valeurs for c in cles_de_la_section(s))]


__all__ = [
    "CLES_COMMUNES",
    "CLES_PROPRES",
    "SECTIONS",
    "EXCLUES_DU_MODELE",
    "SOUS_CLES_EXCLUES",
    "GROUPES_ATOMIQUES",
    "CHAMPS_SECRETS",
    "section_de",
    "cles_de_la_section",
    "cles_du_modele",
    "est_classee",
    "cles_sans_classement",
    "groupe_atomique_de",
    "retirer_les_cles",
    "premiere_cle_trouvee",
    "reporter_les_cles",
    "fournisseurs_sans_cle",
    "valeur_pour_le_modele",
    "valeur_pour_lagent",
    "sections_presentes",
]

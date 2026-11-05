"""[.mark] L6+ (audit 01 A8, décision du lot L6) : la PORTE à identifiant stable.

Avant : le nom de la fonction qu'un modèle appelle pour passer une liaison venait du LIBELLÉ (``transition_tool_name``).
Renommer une liaison changeait ce que le modèle, l'arbitre, la fiche, les traces et les tests appellent, sans erreur.

Maintenant : une liaison porte ``data.identifiant``, posé UNE fois (égal au nom que le libellé donnait à ce moment, donc le
comportement ne change pas) et gardé quand on renomme le libellé, qui n'est plus qu'un nom affiché. Sans identifiant (un ancien
graphe pas encore migré), le nom vient du libellé, exactement comme avant.

* ``nom_de_porte`` : le nom de la fonction d'une liaison (identifiant, sinon libellé) ;
* ``renommer`` : un changement de libellé pose l'identifiant manquant (le nom d'avant) : l'écran, les opérations du builder et le
  code du builder (champs cachés) passent par là ;
* ``poser_les_identifiants`` : pure, idempotente ; jouée par le script de migration douce
  ``scripts/mark/poser_identifiants_des_portes.py``. Les écritures ne touchent pas un graphe non renommé (il se lit comme avant).
"""

from __future__ import annotations

import copy
import re
from typing import Any

MOTIF_IDENTIFIANT = r"^[a-z0-9_]{1,200}$"


def transition_tool_name(label: str) -> str:
    """Le nom que le libellé donnait à la fonction (règle d'origine, gardée pour les graphes sans identifiant)."""
    return re.sub(r"[^a-z0-9]", "_", (label or "").lower())


def nom_de_porte(donnees: Any) -> str:
    """``donnees`` : le ``data`` d'une liaison (objet ou dictionnaire)."""
    identifiant = donnees.get("identifiant") if isinstance(donnees, dict) else getattr(donnees, "identifiant", None)
    if isinstance(identifiant, str) and re.match(MOTIF_IDENTIFIANT, identifiant):
        return identifiant
    label = donnees.get("label") if isinstance(donnees, dict) else getattr(donnees, "label", "")
    return transition_tool_name(label or "")


def renommer(donnees: dict, label: str) -> dict:
    """Le ``data`` d'une liaison au nouveau libellé : la porte garde le nom qu'elle avait (son identifiant, posé ici s'il manquait).
    Pur ; un libellé inchangé ne pose rien."""
    sortie = dict(donnees or {})
    if label != sortie.get("label") and not sortie.get("identifiant") and sortie.get("label"):
        nom = transition_tool_name(sortie["label"])
        if re.match(MOTIF_IDENTIFIANT, nom):
            sortie["identifiant"] = nom
    sortie["label"] = label
    return sortie


def poser_les_identifiants(definition: Any) -> tuple[Any, int]:
    """Rend (copie de la définition, nombre d'identifiants posés). Une liaison qui a déjà le sien n'est jamais touchée ; une liaison
    sans libellé non plus. Rejouer ne change rien (idempotente). Une définition illisible ressort telle quelle."""
    if not isinstance(definition, dict) or not isinstance(definition.get("edges"), list):
        return definition, 0
    sortie = copy.deepcopy(definition)
    poses = 0
    for arete in sortie["edges"]:
        if not isinstance(arete, dict):
            continue
        donnees = arete.get("data")
        if not isinstance(donnees, dict):
            continue
        if isinstance(donnees.get("identifiant"), str) and donnees["identifiant"]:
            continue
        label = donnees.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        nom = transition_tool_name(label)
        if not re.match(MOTIF_IDENTIFIANT, nom):
            continue
        donnees["identifiant"] = nom
        poses += 1
    return sortie, poses

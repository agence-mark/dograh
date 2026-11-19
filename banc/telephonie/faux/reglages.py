"""Les réglages des faux fournisseurs : délais, durée du son, textes joués.

Tout délai vaut zéro par défaut : le banc mesure alors le plancher du fork.
Les réglages se changent en cours de route par la route /reglages, sans
redémarrer, et chaque changement est écrit au journal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any


@dataclass(frozen=True)
class Reglages:
    # Transcription : du premier bloc sonore reçu au premier mot provisoire rendu.
    delai_premier_mot_ms: int = 0
    # Transcription : du premier bloc de silence reçu aux mots définitifs et à
    # la fin de tour. Si la parole reprend avant, la fin de tour est annulée.
    delai_fin_de_tour_ms: int = 0
    # Modèle : de la requête reçue au premier morceau du flux.
    delai_modele_ms: int = 0
    # Modèle : entre deux morceaux du flux.
    delai_entre_morceaux_ms: int = 0
    # Voix : du texte reçu au premier son rendu.
    delai_voix_ms: int = 0
    # Voix : durée du son rendu pour chaque texte reçu.
    duree_voix_ms: int = 1200
    # Transcription : le texte rendu au tour n de l'appel (repris en boucle).
    paroles: tuple[str, ...] = ("Bonjour, ceci est un essai.",)
    # Modèle : la phrase rendue à chaque tour, et celle rendue après un outil.
    phrase: str = "Bien noté, je vous écoute."
    phrase_apres_outil: str = "C'est fait."

    def en_dictionnaire(self) -> dict[str, Any]:
        valeurs = asdict(self)
        valeurs["paroles"] = list(self.paroles)
        return valeurs

    def avec(self, modifications: dict[str, Any]) -> Reglages:
        """Une copie modifiée. Un nom inconnu ou une valeur du mauvais type est
        refusé : un réglage mal écrit ne doit pas passer pour un réglage pris."""
        connus = {champ.name: champ for champ in fields(self)}
        propres: dict[str, Any] = {}
        for nom, valeur in modifications.items():
            if nom not in connus:
                raise ValueError(f"réglage inconnu : {nom}")
            if nom == "paroles":
                if not isinstance(valeur, list) or not valeur:
                    raise ValueError("paroles : une liste de textes non vide")
                if not all(
                    isinstance(texte, str) and texte.strip() for texte in valeur
                ):
                    raise ValueError("paroles : chaque texte doit être non vide")
                propres[nom] = tuple(valeur)
            elif nom in ("phrase", "phrase_apres_outil"):
                if not isinstance(valeur, str) or not valeur.strip():
                    raise ValueError(f"{nom} : un texte non vide")
                propres[nom] = valeur
            else:
                if (
                    isinstance(valeur, bool)
                    or not isinstance(valeur, int)
                    or valeur < 0
                ):
                    raise ValueError(
                        f"{nom} : un nombre entier de millisecondes, zéro ou plus"
                    )
                propres[nom] = valeur
        return replace(self, **propres)


class ReglagesCourants:
    """Les réglages en vigueur, partagés par les trois faux fournisseurs."""

    def __init__(self) -> None:
        self._valeur = Reglages()

    @property
    def valeur(self) -> Reglages:
        return self._valeur

    def modifier(self, modifications: dict[str, Any]) -> Reglages:
        self._valeur = self._valeur.avec(modifications)
        return self._valeur

    def remettre_a_zero(self) -> Reglages:
        self._valeur = Reglages()
        return self._valeur

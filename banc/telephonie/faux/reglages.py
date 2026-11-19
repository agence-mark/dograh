"""Les réglages des faux fournisseurs : délais, durée du son, textes joués.

Tout délai vaut zéro par défaut : le banc mesure alors le plancher du fork.
Les réglages se changent en cours de route par la route /reglages, sans
redémarrer, et chaque changement est écrit au journal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any

# Huit textes différents de chaque côté : un appelant ou un agent qui répète la
# même phrase déclenche dans le fork la sortie d'impasse (« Reprenons, je n'ai
# pas bien compris. »), qui fausserait la mesure d'un tour sur quatre.
PAROLES = (
    "Bonjour, ceci est un essai.",
    "Je voudrais un renseignement.",
    "Pouvez-vous me donner une précision ?",
    "Merci, j'ai une autre question.",
    "Est-ce que vous m'entendez bien ?",
    "Je formule ma demande autrement.",
    "D'accord, je comprends mieux.",
    "Encore un point, s'il vous plaît.",
)
PHRASES = (
    "Bonjour, je vous écoute.",
    "Bien sûr, je regarde cela.",
    "Voici la précision demandée.",
    "Avec plaisir, dites-moi tout.",
    "Oui, je vous entends très bien.",
    "Entendu, je note votre demande.",
    "Parfait, poursuivons ensemble.",
    "C'est noté, je m'en occupe.",
)


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
    paroles: tuple[str, ...] = PAROLES
    # Modèle : la phrase rendue au tour n de l'appel (reprise en boucle), que le
    # tour passe ou non par un outil.
    phrases: tuple[str, ...] = PHRASES

    def en_dictionnaire(self) -> dict[str, Any]:
        valeurs = asdict(self)
        valeurs["paroles"] = list(self.paroles)
        valeurs["phrases"] = list(self.phrases)
        return valeurs

    def avec(self, modifications: dict[str, Any]) -> Reglages:
        """Une copie modifiée. Un nom inconnu ou une valeur du mauvais type est
        refusé : un réglage mal écrit ne doit pas passer pour un réglage pris."""
        connus = {champ.name: champ for champ in fields(self)}
        propres: dict[str, Any] = {}
        for nom, valeur in modifications.items():
            if nom not in connus:
                raise ValueError(f"réglage inconnu : {nom}")
            if nom in ("paroles", "phrases"):
                if not isinstance(valeur, list) or not valeur:
                    raise ValueError(f"{nom} : une liste de textes non vide")
                if not all(
                    isinstance(texte, str) and texte.strip() for texte in valeur
                ):
                    raise ValueError(f"{nom} : chaque texte doit être non vide")
                propres[nom] = tuple(valeur)
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

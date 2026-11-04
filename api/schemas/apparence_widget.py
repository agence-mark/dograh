"""[.mark] S2 / D160 / D198 / D199 : le schéma de l'apparence d'un widget de site.

Rangé dans ``embed_tokens.settings["apparence"]`` (les réglages historiques du widget, à la racine de ``settings``,
ne bougent pas : l'ancien script par jeton marche toujours). Une couleur de base (bleu .mark par défaut), fond et
texte de la fenêtre, d'où se tirent les couleurs de chaque élément ; des retouches facultatives par élément (changer
l'une ne touche aucune autre, aucun contrôle de lisibilité) ; les 18 textes lus par le visiteur (français par défaut) ;
police dans une liste fermée ou « celle du site ». Réglages .mark (domaines, plafonds, durée, limite par adresse)
à part : ``schemas/reglages_site_mark``. Logo : une adresse d'image, pas un dépôt de fichier.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

COULEUR_MARK = "#1b5fb0"
FOND_DEFAUT = "#ffffff"
TEXTE_DEFAUT = "#0f1c2e"
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

ROUGE_RACCROCHER = "#dc2626"
GRIS_BULLE = "#f1f1f1"


def _luminance(couleur: str) -> float:
    n = couleur.lstrip("#")
    if len(n) == 3:
        n = "".join(c * 2 for c in n)
    r, g, b = (int(n[i : i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contraste(a: str, b: str) -> float:
    haut, bas = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (haut + 0.05) / (bas + 0.05)


def sur_couleur(fond: str) -> str:
    """Texte blanc ou presque noir, le plus lisible sur ``fond`` : sert seulement de valeur par défaut."""
    return "#ffffff" if _contraste(fond, "#ffffff") >= _contraste(fond, "#111111") else "#111111"


ELEMENTS_COULEUR = (
    "rond_accroche",
    "fenetre",
    "orbe",
    "boutons",
    "raccrocher",
    "champ_saisie",
    "bulles_ecrit",
    "etoiles",
    "reponses_choisies",
    "icones",
    # V5 : la moitié « texte » de chaque couleur de la maquette, et les bulles de l'assistant.
    "rond_accroche_texte",
    "boutons_texte",
    "raccrocher_texte",
    "champ_saisie_texte",
    "bulle_agent",
    "bulle_agent_texte",
    "bulles_ecrit_texte",
    "reponses_choisies_texte",
)

# Les 18 textes lus par le visiteur (D199). Aucun texte fixe dans le widget : ce sont les valeurs par défaut.
TEXTES_DEFAUT: dict[str, str] = {
    "accroche": "Une question ?\nParlez-moi.",
    "bouton_demarrer": "Parler",
    "annonce_ia": "Vous parlez à un assistant virtuel (intelligence artificielle).",
    "case_confidentialite": "J'ai lu la politique de confidentialité.",
    "case_micro": "J'accepte que ma voix soit transmise pour cette conversation.",
    "ecoute": "Je vous écoute",
    "reflexion": "Je réfléchis",
    "parle": "Je vous réponds",
    "champ_saisie": "Écrire un message",
    "envoyer": "Envoyer",
    "raccrocher": "Raccrocher",
    "fermer": "Fermer",
    "erreur_micro": "Le micro n'est pas disponible. Vous pouvez m'écrire.",
    "avis_question": "Cette conversation vous a-t-elle aidé ?",
    "avis_envoyer": "Envoyer mon avis",
    "merci": "Merci, à bientôt.",
    "plafond_message": "Je ne suis pas disponible pour le moment. Laissez vos coordonnées, vous serez rappelé.",
    "plafond_bouton": "Être rappelé",
    # V5 (maquette `editeur-widget`) : le titre de la fenêtre, l'avis en entier, les deux cases, l'écrit.
    "titre": "Assistant",
    "avis_titre": "Donnez votre avis",
    "avis_passer": "Passer",
    "case_rappel": "Je souhaite qu'un conseiller me rappelle",
    "case_publication": "J'accepte que mon avis soit affiché",
    "ecrire": "Écrire un message",
}
ACCROCHE_LIGNES_MAX = 3
ACCROCHE_LONGUEUR_MAX = 120
TEXTE_LONGUEUR_MAX = 200

Police = Literal["switzer", "inter", "systeme", "site"]  # « site » : celle du site (hérite de la page)


def _couleur(valeur: str | None) -> str | None:
    if valeur is None:
        return None
    if not isinstance(valeur, str) or not _HEX.match(valeur.strip()):
        raise ValueError("a colour is written #rgb or #rrggbb")
    return valeur.strip().lower()


class CouleursParElement(BaseModel):
    """Une clé par élément, chacune facultative : absente = valeur tirée de la couleur de base."""

    model_config = ConfigDict(extra="forbid")

    rond_accroche: str | None = None
    fenetre: str | None = None
    orbe: str | None = None
    boutons: str | None = None
    raccrocher: str | None = None
    champ_saisie: str | None = None
    bulles_ecrit: str | None = None
    etoiles: str | None = None
    reponses_choisies: str | None = None
    icones: str | None = None
    rond_accroche_texte: str | None = None
    boutons_texte: str | None = None
    raccrocher_texte: str | None = None
    champ_saisie_texte: str | None = None
    bulle_agent: str | None = None
    bulle_agent_texte: str | None = None
    bulles_ecrit_texte: str | None = None
    reponses_choisies_texte: str | None = None

    @field_validator(*ELEMENTS_COULEUR, mode="before")
    @classmethod
    def _verifier(cls, valeur):
        return _couleur(valeur)


class TextesWidget(BaseModel):
    """Les 24 textes ; un texte absent prend son défaut français, un texte vide est refusé."""

    model_config = ConfigDict(extra="forbid")

    accroche: str = TEXTES_DEFAUT["accroche"]
    bouton_demarrer: str = TEXTES_DEFAUT["bouton_demarrer"]
    annonce_ia: str = TEXTES_DEFAUT["annonce_ia"]
    case_confidentialite: str = TEXTES_DEFAUT["case_confidentialite"]
    case_micro: str = TEXTES_DEFAUT["case_micro"]
    ecoute: str = TEXTES_DEFAUT["ecoute"]
    reflexion: str = TEXTES_DEFAUT["reflexion"]
    parle: str = TEXTES_DEFAUT["parle"]
    champ_saisie: str = TEXTES_DEFAUT["champ_saisie"]
    envoyer: str = TEXTES_DEFAUT["envoyer"]
    raccrocher: str = TEXTES_DEFAUT["raccrocher"]
    fermer: str = TEXTES_DEFAUT["fermer"]
    erreur_micro: str = TEXTES_DEFAUT["erreur_micro"]
    avis_question: str = TEXTES_DEFAUT["avis_question"]
    avis_envoyer: str = TEXTES_DEFAUT["avis_envoyer"]
    merci: str = TEXTES_DEFAUT["merci"]
    plafond_message: str = TEXTES_DEFAUT["plafond_message"]
    plafond_bouton: str = TEXTES_DEFAUT["plafond_bouton"]
    titre: str = TEXTES_DEFAUT["titre"]
    avis_titre: str = TEXTES_DEFAUT["avis_titre"]
    avis_passer: str = TEXTES_DEFAUT["avis_passer"]
    case_rappel: str = TEXTES_DEFAUT["case_rappel"]
    case_publication: str = TEXTES_DEFAUT["case_publication"]
    ecrire: str = TEXTES_DEFAUT["ecrire"]

    @field_validator("*", mode="before")
    @classmethod
    def _borner(cls, valeur, info):
        if not isinstance(valeur, str) or not valeur.strip():
            raise ValueError("a text cannot be empty")
        if info.field_name == "accroche":
            # Retours à la ligne gardés, aucun ajouté ; bornée en lignes et en longueur.
            if len(valeur) > ACCROCHE_LONGUEUR_MAX or len(valeur.split("\n")) > ACCROCHE_LIGNES_MAX:
                raise ValueError(
                    f"the hook is at most {ACCROCHE_LIGNES_MAX} lines and {ACCROCHE_LONGUEUR_MAX} characters"
                )
            return valeur
        if len(valeur) > TEXTE_LONGUEUR_MAX:
            raise ValueError(f"a text is at most {TEXTE_LONGUEUR_MAX} characters")
        return valeur.strip()


class ApparenceWidget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    couleur_base: str = COULEUR_MARK
    fond_fenetre: str = FOND_DEFAUT
    texte_fenetre: str = TEXTE_DEFAUT
    couleurs: CouleursParElement = Field(default_factory=CouleursParElement)
    police: Police = "switzer"
    embleme: Literal["orbe", "logo"] = "orbe"
    logo_url: str | None = None
    orbe_animee: bool = True
    position: Literal["bas-droite", "bas-gauche"] = "bas-droite"
    fenetre: Literal["centree", "ancree"] = "ancree"
    # « clic » (le défaut d'avant) et « survol » : l'accroche s'affiche au survol du rond ; « delai » : après ``delai_s`` ;
    # « toujours » : tout de suite ; « jamais » : le rond seul.
    declenchement: Literal["clic", "survol", "delai", "toujours", "jamais"] = "clic"
    delai_s: int = Field(default=0, ge=0, le=120)
    textes: TextesWidget = Field(default_factory=TextesWidget)
    lien_confidentialite: str | None = None
    avis: bool = True

    @field_validator("couleur_base", "fond_fenetre", "texte_fenetre", mode="before")
    @classmethod
    def _couleurs_de_base(cls, valeur):
        return _couleur(valeur)

    @field_validator("logo_url", "lien_confidentialite", mode="before")
    @classmethod
    def _adresse_https(cls, valeur):
        if valeur in (None, ""):
            return None
        if not isinstance(valeur, str) or not valeur.startswith("https://") or len(valeur) > 500:
            raise ValueError("an address starts with https:// (500 characters at most)")
        return valeur.strip()

    def couleurs_resolues(self) -> dict[str, str]:
        """La couleur de chaque élément : la retouche, sinon la valeur tirée de la base (texte noir ou blanc, le plus lisible)."""
        base = self.couleur_base
        tirees = {
            "rond_accroche": base,
            "fenetre": self.fond_fenetre,
            "orbe": base,
            "boutons": base,
            "raccrocher": ROUGE_RACCROCHER,
            "champ_saisie": self.fond_fenetre,
            "bulles_ecrit": base,
            "etoiles": base,
            "reponses_choisies": base,
            "icones": base,
            "bulle_agent": GRIS_BULLE,
            "bulle_agent_texte": self.texte_fenetre,
            "champ_saisie_texte": self.texte_fenetre,
        }
        retouches = self.couleurs.model_dump(exclude_none=True)
        resolues = {nom: retouches.get(nom, tirees[nom]) for nom in tirees}
        # Un texte qui n'a pas sa propre couleur prend le plus lisible sur son fond (valeur par défaut seulement).
        for texte, fond in (
            ("rond_accroche_texte", "rond_accroche"),
            ("boutons_texte", "boutons"),
            ("bulles_ecrit_texte", "bulles_ecrit"),
            ("reponses_choisies_texte", "reponses_choisies"),
        ):
            resolues[texte] = retouches.get(texte, sur_couleur(resolues[fond]))
        resolues["raccrocher_texte"] = retouches.get("raccrocher_texte", "#ffffff")
        return {nom: resolues[nom] for nom in ELEMENTS_COULEUR}

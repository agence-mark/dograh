"""[.mark] Chantier fiabilite-orchestration (F23, F24, F25) : le catalogue des motifs.

Un motif est une **attente** ou un **problème** que le code sait détecter, jamais du contenu de
conversation (l'agent reste souple). Un motif nouveau s'ajoute ici quand une cause devient
détectable. Chaque motif porte sa famille :

- *attente* (la passation, le modèle, un outil, le travail de fond, le silence de l'appelant) :
  une seule à la fois, puis un repos ; son délai ne court que pendant une attente **du système**,
  sauf « l'appelant se tait », le seul motif qui répond au silence de l'appelant ;
- *annonce* (mise en relation, transfert échoué, connecteur échoué, réponse perdue) : passe
  toujours, à la suite de la phrase en cours.

Les textes par défaut sont **neutres et sans métier** : ce sont des valeurs pré-remplies, visibles à
l'écran, jamais des constantes cachées. ``actif_par_defaut`` reprend le comportement d'avant le
chantier (zéro perte), sauf décision d'Evan (F7, F20, C1).
"""

from __future__ import annotations

from dataclasses import dataclass

FAMILLE_ATTENTE = "attente"
FAMILLE_ANNONCE = "annonce"


@dataclass(frozen=True)
class Motif:
    id: str
    famille: str
    libelle_fr: str
    libelle_en: str
    # Le déclencheur en clair, pour la carte (F16).
    quand_fr: str
    quand_en: str
    a_un_delai: bool
    variantes_defaut: tuple[str, ...]
    delai_defaut_s: float | None
    actif_par_defaut: bool
    # Ce qui se passe quand la phrase est éteinte (aide de l'écran, F16).
    eteinte_fr: str
    eteinte_en: str
    # Le motif répond au silence de l'appelant (F24 : le seul permis).
    silence_de_l_appelant: bool = False


PASSATION_TARDE = "passation_tarde"
MODELE_TARDE = "modele_tarde"
OUTIL_TARDE = "outil_tarde"
TRAVAIL_DURE = "travail_dure"
APPELANT_SE_TAIT = "appelant_se_tait"
REPONSE_PERDUE = "reponse_perdue"
MISE_EN_RELATION = "mise_en_relation"
TRANSFERT_ECHOUE = "transfert_echoue"
CONNECTEUR_ECHOUE = "connecteur_echoue"

_UN_INSTANT = "Un instant, s'il vous plaît."

MOTIFS: dict[str, Motif] = {
    m.id: m
    for m in (
        Motif(
            id=PASSATION_TARDE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="La passation tarde",
            libelle_en="The handover takes time",
            quand_fr="Un collègue prend la main et n'a pas encore parlé après le délai.",
            quand_en="A colleague takes over and has not spoken yet after the delay.",
            a_un_delai=True,
            variantes_defaut=(_UN_INSTANT,),
            delai_defaut_s=2.0,
            actif_par_defaut=False,
            eteinte_fr="Rien n'est dit : l'appelant attend la première phrase du collègue.",
            eteinte_en="Nothing is said: the caller waits for the colleague's first sentence.",
        ),
        Motif(
            id=MODELE_TARDE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="Le modèle tarde à répondre",
            libelle_en="The model is slow to answer",
            quand_fr=(
                "Après la fin de la réplique de l'appelant, le modèle n'a pas commencé à "
                "répondre dans le délai de garde."
            ),
            quand_en=(
                "After the caller's reply, the model has not started answering within the "
                "guard delay."
            ),
            a_un_delai=True,
            variantes_defaut=(_UN_INSTANT,),
            delai_defaut_s=4.0,
            actif_par_defaut=True,
            eteinte_fr="Rien n'est dit pendant la seconde tentative.",
            eteinte_en="Nothing is said during the second attempt.",
        ),
        Motif(
            id=OUTIL_TARDE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="Un outil tarde",
            libelle_en="A tool takes time",
            quand_fr="Un outil du tour (hors portes, passations et fin) tourne au-delà du délai.",
            quand_en="A tool of the turn (not a step change, handover or end) runs past the delay.",
            a_un_delai=True,
            variantes_defaut=("Je vérifie, un instant.",),
            delai_defaut_s=3.0,
            actif_par_defaut=False,
            eteinte_fr="Rien n'est dit : l'appelant attend le résultat de l'outil.",
            eteinte_en="Nothing is said: the caller waits for the tool's result.",
        ),
        Motif(
            id=TRAVAIL_DURE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="Le travail de fond dure",
            libelle_en="The background work takes time",
            quand_fr="Un travail confié au cerveau de fond n'a pas rendu son résultat après le délai.",
            quand_en="A request given to the background brain has no result yet after the delay.",
            a_un_delai=True,
            variantes_defaut=("C'est presque bon, merci de patienter.",),
            delai_defaut_s=8.0,
            actif_par_defaut=True,
            eteinte_fr="Rien n'est dit jusqu'au résultat.",
            eteinte_en="Nothing is said until the result.",
        ),
        Motif(
            id=APPELANT_SE_TAIT,
            famille=FAMILLE_ATTENTE,
            libelle_fr="L'appelant se tait",
            libelle_en="The caller is silent",
            quand_fr="L'agent a fini de parler et l'appelant ne dit rien pendant le délai.",
            quand_en="The agent has finished speaking and the caller says nothing for the delay.",
            a_un_delai=True,
            variantes_defaut=("Êtes-vous toujours là ?", "Allô ?"),
            delai_defaut_s=10.0,
            actif_par_defaut=True,
            eteinte_fr="Le modèle relance lui-même la conversation, comme avant le chantier.",
            eteinte_en="The model prompts the caller itself, as before.",
            silence_de_l_appelant=True,
        ),
        Motif(
            id=REPONSE_PERDUE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="La réponse du modèle est perdue",
            libelle_en="The model's answer is lost",
            quand_fr="La réponse du modèle n'a rien donné de dicible, même après la relance du filet.",
            quand_en="The model's answer produced nothing to say, even after the safety retry.",
            a_un_delai=False,
            variantes_defaut=("Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Silence : l'appelant reprend la parole.",
            eteinte_en="Silence: the caller speaks again.",
        ),
        Motif(
            id=MISE_EN_RELATION,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Mise en relation avant un transfert d'appel",
            libelle_en="Before an outbound call transfer",
            quand_fr=(
                "Un agent arrive sur une étape qui porte un transfert d'appel, entreprise "
                "ouverte, juste avant de lancer le transfert."
            ),
            quand_en=(
                "An agent reaches a step with a call transfer, business open, right before "
                "starting the transfer."
            ),
            a_un_delai=False,
            variantes_defaut=("Je vous mets en relation, un instant.",),
            delai_defaut_s=None,
            actif_par_defaut=False,
            eteinte_fr="Le modèle annonce lui-même la mise en relation.",
            eteinte_en="The model announces the transfer itself.",
        ),
        Motif(
            id=TRANSFERT_ECHOUE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Le transfert d'appel échoue",
            libelle_en="The call transfer fails",
            quand_fr="Un transfert vers une personne n'aboutit pas (pas de réponse, répondeur).",
            quand_en="A transfer to a person does not go through (no answer, voicemail).",
            a_un_delai=False,
            variantes_defaut=("Je n'ai pas pu vous mettre en relation.",),
            delai_defaut_s=None,
            actif_par_defaut=False,
            eteinte_fr="Le modèle dit lui-même que le transfert n'a pas abouti.",
            eteinte_en="The model says itself that the transfer failed.",
        ),
        Motif(
            id=CONNECTEUR_ECHOUE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Un connecteur échoue",
            libelle_en="A connector fails",
            quand_fr="Une action d'un connecteur échoue ou dépasse son délai.",
            quand_en="A connector action fails or runs past its deadline.",
            a_un_delai=False,
            variantes_defaut=("Je transmets votre demande, on vous rappelle pour la confirmer.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Rien n'est dit par le code : le modèle lit l'échec et répond.",
            eteinte_en="The code says nothing: the model reads the failure and answers.",
        ),
    )
}


def motif(identifiant: str) -> Motif | None:
    return MOTIFS.get(identifiant)

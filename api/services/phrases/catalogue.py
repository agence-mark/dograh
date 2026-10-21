"""[.mark] Chantier fiabilite-orchestration (F23, F24, F25) puis correctifs-apres-banc-v4 (lot 4) :
le catalogue des motifs.

Un motif est une **attente** ou un **problème** que le code sait détecter, jamais du contenu de
conversation (l'agent reste souple). Un motif nouveau s'ajoute ici quand une cause devient
détectable. Chaque motif porte sa famille et son moment :

- *attente* (la passation, le modèle, un outil, le travail de fond, le silence de l'appelant) :
  une seule à la fois, puis un repos ; son délai ne court que pendant une attente **du système**,
  sauf « l'appelant se tait », le seul motif qui répond au silence de l'appelant ;
- *annonce* (mise en relation, transfert échoué, outil échoué, travail de fond échoué, réponse
  perdue) : passe toujours, à la suite de la phrase en cours. Un problème est déclenché par un
  **fait**, pas par du temps : il n'a ni délai ni redite, seulement un compteur dans l'appel.

Chaque motif dit **les cases qu'il permet** (``delai_min_s``, ``peut_redire``, ``filtre_outil``,
``sorties_permises``, ``sortie_defaut``, ``texte_de_l_agent``) et **la fin de l'attente lue ailleurs** :
l'écran n'affiche que ces cases et recopie ce catalogue (``catalogue_pour_l_ecran``, comparé au JSON
de l'écran par un test).

Les textes par défaut sont **neutres et sans métier** : ce sont des valeurs pré-remplies, visibles à
l'écran, jamais des constantes cachées. ``actif_par_defaut`` reprend le comportement d'avant le
chantier (zéro perte), sauf décision d'Evan (F7, F20, C1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FAMILLE_ATTENTE = "attente"
FAMILLE_ANNONCE = "annonce"

MOMENT_ATTENTE = "attente"
MOMENT_PROBLEME = "probleme"
MOMENT_ACTION = "action"

SORTIE_CONTINUER = "continuer"
SORTIE_MODELE = "modele"
SORTIE_TRANSFERER = "transferer"
SORTIE_RACCROCHER = "raccrocher"


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
    # -- les cases permises (correctifs-apres-banc-v4, 4.4) --
    moment: str = MOMENT_ATTENTE
    delai_min_s: float = 0.0
    peut_redire: bool = False
    filtre_outil: bool = False
    texte_de_l_agent: bool = False
    sorties_permises: tuple[str, ...] = (SORTIE_CONTINUER,)
    sortie_defaut: str = SORTIE_CONTINUER
    # La fin de l'attente, lue ailleurs (texte, et le réglage où elle se pose).
    fin_d_attente_fr: str = ""
    fin_d_attente_en: str = ""
    fin_d_attente_reglage: str | None = None
    # Le fait, dit au modèle dans le compte rendu qui suit une phrase du code (4.10) : une phrase du
    # catalogue, jamais un mot de métier.
    fait_fr: str = ""


PASSATION_TARDE = "passation_tarde"
MODELE_TARDE = "modele_tarde"
OUTIL_TARDE = "outil_tarde"
TRAVAIL_DURE = "travail_dure"
APPELANT_SE_TAIT = "appelant_se_tait"
REPONSE_PERDUE = "reponse_perdue"
MISE_EN_RELATION = "mise_en_relation"
TRANSFERT_ECHOUE = "transfert_echoue"
OUTIL_ECHOUE = "outil_echoue"
TRAVAIL_ECHOUE = "travail_echoue"
# Ancien identifiant du motif « un outil échoue » : les règles d'avant se lisent comme les nouvelles
# (``schemas.phrases_du_code.ALIAS_DE_MOTIFS``).
CONNECTEUR_ECHOUE = "connecteur_echoue"

_UN_INSTANT = "Un instant, s'il vous plaît."

_TOUTES_LES_SORTIES = (SORTIE_CONTINUER, SORTIE_MODELE, SORTIE_TRANSFERER, SORTIE_RACCROCHER)
_SORTIES_DES_ECHECS = _TOUTES_LES_SORTIES

MOTIFS: dict[str, Motif] = {
    m.id: m
    for m in (
        Motif(
            id=OUTIL_TARDE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="Un outil travaille",
            libelle_en="A tool is working",
            quand_fr="L'agent a lancé un outil (hors portes, passations et fin) et n'a pas encore son résultat.",
            quand_en="The agent started a tool (not a step change, handover or end) and has no result yet.",
            a_un_delai=True,
            variantes_defaut=("Je vérifie, un instant.",),
            delai_defaut_s=3.0,
            actif_par_defaut=False,
            eteinte_fr="Rien n'est dit : l'appelant attend le résultat de l'outil.",
            eteinte_en="Nothing is said: the caller waits for the tool's result.",
            moment=MOMENT_ATTENTE,
            delai_min_s=0.0,
            peut_redire=True,
            filtre_outil=True,
            fin_d_attente_fr=(
                "L'outil abandonne à son délai (réglé sur l'outil, essais compris), puis la règle "
                "« un outil échoue »."
            ),
            fin_d_attente_en=(
                "The tool gives up at its deadline (set on the tool, retries included), then the "
                "rule \"a tool fails\"."
            ),
            fin_d_attente_reglage="outil",
        ),
        Motif(
            id=TRAVAIL_DURE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="Le travail de fond travaille",
            libelle_en="The background work is working",
            quand_fr="L'agent a confié un travail au cerveau de fond et n'a pas encore son résultat.",
            quand_en="The agent handed a job to the background brain and has no result yet.",
            a_un_delai=True,
            variantes_defaut=("C'est presque bon, merci de patienter.",),
            delai_defaut_s=8.0,
            actif_par_defaut=True,
            eteinte_fr="Rien n'est dit jusqu'au résultat.",
            eteinte_en="Nothing is said until the result.",
            moment=MOMENT_ATTENTE,
            delai_min_s=0.0,
            peut_redire=True,
            texte_de_l_agent=True,
            fin_d_attente_fr=(
                "Le travail abandonne à son délai maximal (réglé dans Travail en arrière-plan), "
                "puis la règle « le travail de fond échoue »."
            ),
            fin_d_attente_en=(
                "The job gives up at its maximum delay (set in Background work), then the rule "
                "\"the background work fails\"."
            ),
            fin_d_attente_reglage="travail",
        ),
        Motif(
            id=PASSATION_TARDE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="Un collègue prend la main",
            libelle_en="A colleague takes over",
            quand_fr="Une passation est lancée et le collègue n'a pas encore parlé.",
            quand_en="A handover is under way and the colleague has not spoken yet.",
            a_un_delai=True,
            variantes_defaut=(_UN_INSTANT,),
            delai_defaut_s=2.0,
            actif_par_defaut=False,
            eteinte_fr="Rien n'est dit : l'appelant attend la première phrase du collègue.",
            eteinte_en="Nothing is said: the caller waits for the colleague's first sentence.",
            moment=MOMENT_ATTENTE,
            delai_min_s=0.5,
            peut_redire=True,
            fin_d_attente_fr="Le collègue parle.",
            fin_d_attente_en="The colleague speaks.",
        ),
        Motif(
            id=MODELE_TARDE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="Le modèle tarde à répondre",
            libelle_en="The model is slow to answer",
            quand_fr=(
                "Le modèle n'a pas commencé à répondre dans son délai de garde (réglé dans "
                "Models, sous le cerveau) : la phrase, puis une seconde tentative."
            ),
            quand_en=(
                "The model has not started answering within its guard delay (set in Models, "
                "under the brain): the sentence, then a second try."
            ),
            # Le délai est celui de la garde (Models, F20) : un seul réglage, jamais deux.
            a_un_delai=False,
            variantes_defaut=(_UN_INSTANT,),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Rien n'est dit pendant la seconde tentative.",
            eteinte_en="Nothing is said during the second attempt.",
            moment=MOMENT_ATTENTE,
            fin_d_attente_fr=(
                "Le délai est celui de la garde du modèle (Modèles, Garde) ; une seule fois, puis la "
                "seconde tentative et le mode panne."
            ),
            fin_d_attente_en=(
                "The delay is the model guard's (Models, Guard); once, then the second attempt and "
                "the outage mode."
            ),
            fin_d_attente_reglage="garde",
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
            moment=MOMENT_ATTENTE,
            delai_min_s=2.0,
            peut_redire=True,
            sorties_permises=(SORTIE_CONTINUER, SORTIE_TRANSFERER, SORTIE_RACCROCHER),
            sortie_defaut=SORTIE_RACCROCHER,
            fin_d_attente_fr=(
                "Le nombre de relances est celui de « au plus, par attente » quand la règle le pose, "
                "sinon celui de Rythme ; la sortie part au silence qui suit la dernière relance."
            ),
            fin_d_attente_en=(
                "The number of prompts is \"at most, per wait\" when the rule sets it, else Pace's; "
                "the exit goes at the silence that follows the last prompt."
            ),
            fin_d_attente_reglage="rythme",
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
            fait_fr="la réponse a été perdue",
            moment=MOMENT_PROBLEME,
            sorties_permises=_TOUTES_LES_SORTIES,
            sortie_defaut=SORTIE_CONTINUER,
        ),
        Motif(
            id=OUTIL_ECHOUE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Un outil échoue",
            libelle_en="A tool fails",
            quand_fr="Un outil ou un connecteur échoue, après ses essais, ou dépasse son délai.",
            quand_en="A tool or a connector fails, after its retries, or runs past its deadline.",
            a_un_delai=False,
            variantes_defaut=("Je transmets votre demande, on vous rappelle pour la confirmer.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Rien n'est dit par le code : le modèle lit l'échec et répond.",
            eteinte_en="The code says nothing: the model reads the failure and answers.",
            fait_fr="l'outil n'a pas abouti",
            moment=MOMENT_PROBLEME,
            filtre_outil=True,
            sorties_permises=_SORTIES_DES_ECHECS,
            sortie_defaut=SORTIE_MODELE,
        ),
        Motif(
            id=TRAVAIL_ECHOUE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Le travail de fond échoue",
            libelle_en="The background work fails",
            quand_fr=(
                "Le travail de fond rend un échec, dépasse son délai, ou rend un résultat sans avoir "
                "appelé aucun outil."
            ),
            quand_en=(
                "The background work returns a failure, runs past its deadline, or returns a result "
                "without having called any tool."
            ),
            a_un_delai=False,
            variantes_defaut=("Je n'arrive pas à finaliser pour le moment.",),
            delai_defaut_s=None,
            actif_par_defaut=False,
            eteinte_fr="Le modèle lit « Échec : rien n'a été fait » et répond.",
            eteinte_en="The model reads the failure and answers.",
            fait_fr="le travail de fond n'a pas abouti",
            moment=MOMENT_PROBLEME,
            sorties_permises=_SORTIES_DES_ECHECS,
            sortie_defaut=SORTIE_MODELE,
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
            fait_fr="le transfert n'a pas abouti",
            moment=MOMENT_PROBLEME,
            # M4 : jamais « transférer » ici (un renvoi vient d'échouer ; décision d'Evan).
            sorties_permises=(SORTIE_CONTINUER, SORTIE_MODELE, SORTIE_RACCROCHER),
            sortie_defaut=SORTIE_MODELE,
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
            moment=MOMENT_ACTION,
        ),
    )
}

# Les motifs d'un problème (déclenchés par un fait) : un compteur dans l'appel, jamais de délai.
MOTIFS_DE_PROBLEME = tuple(m.id for m in MOTIFS.values() if m.moment == MOMENT_PROBLEME)


def motif(identifiant: str) -> Motif | None:
    return MOTIFS.get(identifiant)


def catalogue_pour_l_ecran() -> dict[str, Any]:
    """Le catalogue tel que l'écran le lit (``catalogue-des-phrases.json``) : recopié dans l'écran,
    comparé au code par un test. Aucun texte ne s'écrit à la main de l'autre côté."""
    from api.schemas.phrases_du_code import (
        DELAI_MAX_S,
        DELAI_MIN_S,
        MAX_LONGUEUR_PHRASE,
        MAX_PAR_APPEL,
        MAX_PAR_ATTENTE,
        MAX_REGLES,
        MAX_VARIANTES,
        REDITE_MAX_S,
        REDITE_MIN_S,
    )
    from api.services.phrases.diseur import REPOS_ATTENTE_S

    return {
        "bornes": {
            "variantes_max": MAX_VARIANTES,
            "longueur_max": MAX_LONGUEUR_PHRASE,
            "regles_max": MAX_REGLES,
            "delai_min_s": DELAI_MIN_S,
            "delai_max_s": DELAI_MAX_S,
            "redite_min_s": REDITE_MIN_S,
            "redite_max_s": REDITE_MAX_S,
            "max_par_attente": MAX_PAR_ATTENTE,
            "max_par_appel": MAX_PAR_APPEL,
            "repos_defaut_s": REPOS_ATTENTE_S,
        },
        "motifs": [
            {
                "id": m.id,
                "famille": m.famille,
                "moment": m.moment,
                "libelle": {"en": m.libelle_en, "fr": m.libelle_fr},
                "quand": {"en": m.quand_en, "fr": m.quand_fr},
                "a_un_delai": m.a_un_delai,
                "delai_min_s": m.delai_min_s,
                "peut_redire": m.peut_redire,
                "filtre_outil": m.filtre_outil,
                "texte_de_l_agent": m.texte_de_l_agent,
                "sorties_permises": list(m.sorties_permises),
                "sortie_defaut": m.sortie_defaut,
                "fin_d_attente": {"en": m.fin_d_attente_en, "fr": m.fin_d_attente_fr},
                "fin_d_attente_reglage": m.fin_d_attente_reglage,
                "variantes_defaut": list(m.variantes_defaut),
                "delai_defaut_s": m.delai_defaut_s,
                "actif_par_defaut": m.actif_par_defaut,
                "eteinte": {"en": m.eteinte_en, "fr": m.eteinte_fr},
                "silence_de_l_appelant": m.silence_de_l_appelant,
            }
            for m in MOTIFS.values()
        ],
    }

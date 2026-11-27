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
# fiabilite-de-la-conversation, lot A : les deux suites du garde-fou de sortie d'impasse.
SORTIE_RENDRE_LA_MAIN = "rendre_la_main"
SORTIE_ALLER_A_UNE_ETAPE = "aller_a_une_etape"


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
    # Le code prend sa sortie par défaut même quand la règle n'en pose aucune (lot A : le garde-fou de sortie
    # d'impasse rend la main de lui-même, c'est son rôle). ``False`` : une sortie ne part que si la règle la pose.
    sortie_par_le_code: bool = False
    # L3e : un motif verrouillé ne s'éteint jamais et n'est jamais vide (l'annonce « vous parlez à une IA ») : on change son texte, pas son existence.
    verrouille: bool = False
    # C6 (Q1 = A, Pierre 25/11) : les variables que le CODE remplace dans la phrase (« {total} »). Une variante réglée qui en perd une est refusée (schemas.phrases_du_code) ;
    # l'écran les montrera comme étiquettes avec la ligne S de la Partie 2 (la Partie 1 ne touche pas l'écran, F14).
    variables: tuple[str, ...] = ()


PASSATION_TARDE = "passation_tarde"
MODELE_TARDE = "modele_tarde"
OUTIL_TARDE = "outil_tarde"
TRAVAIL_DURE = "travail_dure"
APPELANT_SE_TAIT = "appelant_se_tait"
# passages-fiables (lot E) : la personne a demandé du temps (outil « laisser la parole ») et se tait.
ATTENTE_ACCORDEE = "attente_accordee"
REPONSE_PERDUE = "reponse_perdue"
MISE_EN_RELATION = "mise_en_relation"
TRANSFERT_ECHOUE = "transfert_echoue"
OUTIL_ECHOUE = "outil_echoue"
TRAVAIL_ECHOUE = "travail_echoue"
# Ancien identifiant du motif « un outil échoue » : les règles d'avant se lisent comme les nouvelles
# (``schemas.phrases_du_code.ALIAS_DE_MOTIFS``).
CONNECTEUR_ECHOUE = "connecteur_echoue"
# fiabilite-de-la-conversation, lot A : le garde-fou de sortie d'impasse. Les deux premiers temps de la riposte
# sont des notices au modèle (jamais dites) ; le troisième dit la phrase de ce motif, puis change l'étape.
IMPASSE = "impasse"
IMPASSE_REPETEE = "impasse_repetee"
# RA-B (R5) : la phrase de fin d'une conversation du widget à sa durée maximale (``site_mark/duree_max.py``).
FIN_DE_DUREE_MAX = "fin_duree_max"
# L3e : l'annonce « vous parlez à une IA » en tête de chaque appel et la phrase du garde-fou urgence. Clôture, lot B (D1) : l'annonce est une phrase comme
# les autres : allumée par défaut avec son texte, activable et modifiable (plus de verrou).
ANNONCE_IA = "annonce_ia"
URGENCE_VITALE = "urgence_vitale"
# M98 : la question qui finit la relecture quand le numéro qui s'affiche est gardé (commande et réservation) : dite DANS le résultat de l'outil,
# à la place du « C'est bon ? » final, jamais en plus. Un « oui » vaut pour la relecture et le numéro.
NUMERO_AFFICHE_GARDE = "numero_affiche_garde"
# M108 : la question qui finit la confirmation d'un enregistrement dite par le code : la personne répond avant que l'appel se termine (une question
# du code rend la parole, M92 ; la fin d'appel attend sa réponse). Dite DANS le résultat de l'outil, jamais en plus.
APRES_ENREGISTREMENT = "apres_enregistrement"
# C6 (décision d'Evan 25/11 9 h 30, § 8 bis) : le total reste dit par le code, mot pour mot, après la phrase du modèle (la relecture, puis la correction) ; le modèle ne le dit jamais.
TOTAL_RELECTURE = "total_relecture"
TOTAL_APRES_CORRECTION = "total_apres_correction"
TOTAL_APRES_CHANGEMENT = "total_apres_changement"  # C6 n° 6 : le nouveau total d'une commande enregistrée puis changée, dit après la phrase du modèle
# Reprise R1 de 8b-1b (exception « le numéro » d'Evan, 25/11 9 h 30) : le numéro de commande changé par un changement après le « oui » (son préfixe suit le mode), dit après la phrase du modèle
NUMERO_DE_COMMANDE_CHANGE = "numero_de_commande_change"
RENDU_DE_MONNAIE = "rendu_de_monnaie"  # C6 n° 5 : le rendu calculé par le code, dit après la confirmation du modèle et avant la question M108
CONFIRMATION_REGLEE = "confirmation_reglee"  # PE-2 (Q4, point d'étape du 26/11) : « C'est enregistré. », dite par le code seulement quand la relance de la confirmation du modèle a échoué (commande seulement)
NUMERO_DICTE_RELU = "numero_dicte_relu"  # DC10 (Evan, 22/11) : le numéro dicté relu avant l'enregistrement, réglable, allumé par défaut
# C6 n° 10 (§ 8 bis) : le numéro dicté et retenu, dit par le code après la phrase du modèle et avant la suite du code (total, rendu, question) ; sa forme qui pose la question est
# ``numero_dicte_relu`` (DC10). Le modèle ne dit jamais le numéro.
NUMERO_RETENU = "numero_retenu"

_UN_INSTANT = "Un instant, s'il vous plaît."

_TOUTES_LES_SORTIES = (SORTIE_CONTINUER, SORTIE_MODELE, SORTIE_TRANSFERER, SORTIE_RACCROCHER)
_SORTIES_DES_ECHECS = _TOUTES_LES_SORTIES
_SORTIES_DE_L_IMPASSE = (
    SORTIE_RENDRE_LA_MAIN,
    SORTIE_ALLER_A_UNE_ETAPE,
    SORTIE_MODELE,
    SORTIE_TRANSFERER,
    SORTIE_RACCROCHER,
)

MOTIFS: dict[str, Motif] = {
    m.id: m
    for m in (
        # ⛔ Libellé PROVISOIRE, à valider sur le texte officiel (AI Act art. 50) avant d'être figé : voir ``18-a-exposer.md``.
        Motif(
            id=ANNONCE_IA,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Annonce : vous parlez à une IA",
            libelle_en="Announcement: you are talking to an AI",
            quand_fr="Au début de chaque appel (téléphone, widget, campagne), avant l'accueil. Allumée par défaut : le texte se change, et elle s'éteint si le client l'a décidé (la ligne « Annonce » de « Prêt à publier » le signale).",
            quand_en="At the start of every call (phone, widget, campaign), before the greeting. On by default: the text can change, and it can be turned off if the client decided so (the « Announcement » line of « Ready to publish » flags it).",
            a_un_delai=False,
            variantes_defaut=("Vous êtes en communication avec un assistant virtuel, une intelligence artificielle.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="L'appelant n'entend plus l'annonce : la ligne « Annonce » de « Prêt à publier » le signale (réglable).",
            eteinte_en="The caller no longer hears the announcement: the « Announcement » line of « Ready to publish » flags it (adjustable).",
            moment=MOMENT_ACTION,
        ),
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
            id=ATTENTE_ACCORDEE,
            famille=FAMILLE_ATTENTE,
            libelle_fr="L'appelant prend son temps",
            libelle_en="The caller is taking their time",
            quand_fr=(
                "L'agent a laissé la parole (l'appelant cherche ou vérifie quelque chose, case « Laisser l'appelant "
                "prendre son temps » de Rythme de l'appel) et il reste muet pendant le délai."
            ),
            quand_en=(
                "The agent let the caller take their time (looking something up or checking, switch \"Let the caller "
                "take their time\" in Call pace) and the caller stays silent for the delay."
            ),
            a_un_delai=True,
            variantes_defaut=("Prenez votre temps, je suis toujours là.",),
            delai_defaut_s=45.0,
            actif_par_defaut=True,
            eteinte_fr="Rien n'est dit : l'attente se termine sans phrase, et l'appel n'est jamais raccroché pendant elle.",
            eteinte_en="Nothing is said: the wait ends without a sentence, and the call is never hung up during it.",
            silence_de_l_appelant=True,
            moment=MOMENT_ATTENTE,
            delai_min_s=5.0,
            peut_redire=False,
            fin_d_attente_fr=(
                "La personne reparle, ou la phrase est dite : le comportement normal de « L'appelant se tait » reprend."
            ),
            fin_d_attente_en=(
                "The caller speaks again, or the sentence is said: the normal \"The caller is silent\" behaviour resumes."
            ),
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
            id=IMPASSE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="La conversation tourne en rond",
            libelle_en="The conversation goes in circles",
            quand_fr=(
                "Le code compte des signes d'impasse (l'agent redit la même réplique, renvoie la même "
                "demande au travail de fond, ne sort de rien en trois tours, revient une troisième fois "
                "dans une étape). Au deuxième signe le modèle reçoit une consigne, au suivant une "
                "seconde ; au quatrième le code dit cette phrase et reprend la main."
            ),
            quand_en=(
                "The code counts signs of a dead end (the agent repeats the same reply, sends the same "
                "request to the background work, gets nowhere in three turns, enters a step a third "
                "time). At the second sign the model gets a note, at the next another one; at the "
                "fourth the code says this sentence and takes the call back."
            ),
            a_un_delai=False,
            variantes_defaut=("Reprenons, je n'ai pas bien compris. En quoi puis-je vous aider ?",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr=(
                "Le code ne dit rien et ne change pas d'étape : le modèle garde la main (les deux "
                "consignes qui lui sont destinées restent)."
            ),
            eteinte_en=(
                "The code says nothing and keeps the step: the model keeps the call (the two notes "
                "meant for it stay)."
            ),
            fait_fr="la conversation tournait en rond",
            moment=MOMENT_PROBLEME,
            sorties_permises=_SORTIES_DE_L_IMPASSE,
            sortie_defaut=SORTIE_RENDRE_LA_MAIN,
            sortie_par_le_code=True,
        ),
        Motif(
            id=IMPASSE_REPETEE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="La conversation tourne en rond une deuxième fois",
            libelle_en="The conversation goes in circles a second time",
            quand_fr=(
                "Une deuxième impasse dans le même appel : le code dit cette phrase, puis change l'étape "
                "de lui-même vers l'étape de l'agent principal choisie dans « Ensuite » (sans étape "
                "choisie : comme la première impasse)."
            ),
            quand_en=(
                "A second dead end in the same call: the code says this sentence, then moves to the step "
                "of the main agent chosen under \"Then\" (no step chosen: as for the first dead end)."
            ),
            a_un_delai=False,
            variantes_defaut=("Je prends votre demande pour qu'on vous rappelle.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Le code ne dit rien et ne change pas d'étape : le modèle garde la main.",
            eteinte_en="The code says nothing and keeps the step: the model keeps the call.",
            fait_fr="la conversation tournait en rond une deuxième fois",
            moment=MOMENT_PROBLEME,
            sorties_permises=_SORTIES_DE_L_IMPASSE,
            sortie_defaut=SORTIE_ALLER_A_UNE_ETAPE,
            sortie_par_le_code=True,
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
        Motif(
            id=FIN_DE_DUREE_MAX,
            famille=FAMILLE_ANNONCE,
            libelle_fr="La conversation du site atteint sa durée maximale",
            libelle_en="The website conversation reaches its maximum duration",
            quand_fr="Une conversation du widget du site arrive à sa durée maximale : le code dit cette phrase puis met fin à l'appel.",
            quand_en="A website widget conversation reaches its maximum duration: the code says this sentence, then ends the call.",
            a_un_delai=False,
            variantes_defaut=("Je dois malheureusement conclure cette conversation. Merci de votre visite et à bientôt.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Le code dit quand même la phrase par défaut : une conversation ne se termine jamais en silence.",
            eteinte_en="The code still says the default sentence: a conversation never ends in silence.",
            moment=MOMENT_ACTION,
        ),
        # ⛔ Phrase et numéro PROVISOIRES, à valider par Evan (voir ``18-a-exposer.md``). ``{{numero}}`` : le numéro d'urgence réglé dans Sécurité.
        Motif(
            id=URGENCE_VITALE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Danger ou urgence médicale détectés",
            libelle_en="Danger or medical emergency detected",
            quand_fr="Le garde-fou urgence (réglé dans Sécurité) reconnaît une détresse ou une urgence médicale dans les mots de l'appelant : le code dit cette phrase, une fois par appel.",
            quand_en="The emergency safeguard (set in Security) recognises distress or a medical emergency in the caller's words: the code says this sentence, once per call.",
            a_un_delai=False,
            variantes_defaut=("Si vous ou une personne près de vous êtes en danger, raccrochez et appelez tout de suite le {{numero}}.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Le garde-fou le détecte et le note, mais l'agent ne dit pas la phrase.",
            eteinte_en="The safeguard detects and notes it, but the agent does not say the sentence.",
            moment=MOMENT_ACTION,
        ),
        Motif(
            id=NUMERO_AFFICHE_GARDE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Relecture : le numéro qui s'affiche est gardé",
            libelle_en="Read-back: the caller's displayed number is kept",
            quand_fr="Après la relecture d'une réservation, quand le numéro d'où la personne appelle est gardé : le code pose cette question à la place du « C'est bon ? » final. Un « oui » vaut pour la relecture et le numéro ; un autre numéro dit à la place est relu par paires.",
            quand_en="After a booking read-back, when the number the person calls from is kept: the agent asks this question instead of the final « Is that right? ». A « yes » covers the read-back and the number; another number given instead is read back in pairs.",
            a_un_delai=False,
            variantes_defaut=("Je note ce numéro de téléphone pour vous joindre en cas de problème, c'est bon ?",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Le modèle finit la relecture de la réservation par sa propre question, sans parler du numéro : il reste gardé.",
            eteinte_en="The model ends the booking read-back with its own question, without mentioning the number: it is still kept.",
            moment=MOMENT_ACTION,
        ),
        Motif(
            id=APRES_ENREGISTREMENT,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Après un enregistrement : la question qui suit",
            libelle_en="After a save: the follow-up question",
            quand_fr="À la fin de la confirmation d'une commande enregistrée, dite par le code : cette question la termine. La personne répond avant que l'appel ne se termine.",
            quand_en="At the end of the confirmation of a saved order, said by the code: this question ends it. The person answers before the call can end.",
            a_un_delai=False,
            variantes_defaut=("Puis-je faire autre chose pour vous ?",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="La confirmation est dite seule ; l'agent reprend la parole après elle.",
            eteinte_en="The confirmation is said alone; the agent speaks again after it.",
            moment=MOMENT_ACTION,
        ),
        Motif(
            id=TOTAL_RELECTURE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Relecture de la commande : le total et la question",
            libelle_en="Order read-back: the total and the question",
            quand_fr="Après la phrase de relecture de l'agent, le code dit le total puis pose la question (« c'est bon ? »). « {total} » est remplacé par le montant en lettres : une phrase sans « {total} » est refusée.",
            quand_en="After the agent's read-back sentence, the code says the total then asks the question (« is that right? »). « {total} » is replaced by the amount in words: a sentence without « {total} » is refused.",
            a_un_delai=False,
            variantes_defaut=("Cela fait {total}, c'est bon pour vous ?", "Ça fait {total}, c'est bon ?"),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Jamais éteinte : sans elle, la personne ne saurait pas le total. On change son texte, pas son existence.",
            eteinte_en="Never off: without it the person would not hear the total. Change its text, not its existence.",
            moment=MOMENT_ACTION,
            verrouille=True,
            variables=("total",),
        ),
        Motif(
            id=TOTAL_APRES_CORRECTION,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Relecture après une correction : le nouveau total et la question",
            libelle_en="Read-back after a correction: the new total and the question",
            quand_fr="Après la phrase de l'agent qui dit ce qui a changé, le code dit le nouveau total puis pose la question. « {total} » est remplacé par le montant en lettres : une phrase sans « {total} » est refusée.",
            quand_en="After the agent's sentence about what changed, the code says the new total then asks the question. « {total} » is replaced by the amount in words: a sentence without « {total} » is refused.",
            a_un_delai=False,
            variantes_defaut=("Ça fait maintenant {total}, c'est bon ?", "Cela fait maintenant {total}, c'est bon pour vous ?"),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Jamais éteinte : sans elle, la personne ne saurait pas le nouveau total. On change son texte, pas son existence.",
            eteinte_en="Never off: without it the person would not hear the new total. Change its text, not its existence.",
            moment=MOMENT_ACTION,
            verrouille=True,
            variables=("total",),
        ),
        Motif(
            id=TOTAL_APRES_CHANGEMENT,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Commande changée après l'enregistrement : le nouveau total",
            libelle_en="Order changed after the save: the new total",
            quand_fr="Après la phrase de l'agent qui dit que la commande enregistrée est changée, quand son total change : le code dit le nouveau total, puis la question qui suit l'enregistrement. « {total} » est remplacé par le montant en lettres : une phrase sans « {total} » est refusée.",
            quand_en="After the agent's sentence saying the saved order is changed, when its total changes: the code says the new total, then the follow-up question. « {total} » is replaced by the amount in words: a sentence without « {total} » is refused.",
            a_un_delai=False,
            variantes_defaut=("Votre commande fait maintenant {total}.", "Elle fait maintenant {total}."),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Jamais éteinte : sans elle, la personne ne saurait pas le nouveau total. On change son texte, pas son existence.",
            eteinte_en="Never off: without it the person would not hear the new total. Change its text, not its existence.",
            moment=MOMENT_ACTION,
            verrouille=True,
            variables=("total",),
        ),
        Motif(
            id=NUMERO_DE_COMMANDE_CHANGE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Commande changée après l'enregistrement : le nouveau numéro",
            libelle_en="Order changed after the save: the new number",
            quand_fr="Après la phrase de l'agent qui dit que la commande enregistrée est changée, quand son numéro de commande change (son préfixe suit le mode, par exemple une commande à emporter passée en livraison) : le code dit le nouveau numéro, avant le nouveau total. « {numero} » est remplacé par le numéro : une phrase sans « {numero} » est refusée.",
            quand_en="After the agent's sentence saying the saved order is changed, when its order number changes (its prefix follows the mode, for example a takeaway order switched to delivery): the code says the new number, before the new total. « {numero} » is replaced by the number: a sentence without « {numero} » is refused.",
            a_un_delai=False,
            variantes_defaut=("Votre numéro de commande devient {numero}.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Jamais éteinte : sans elle, la personne garderait un numéro faux. On change son texte, pas son existence.",
            eteinte_en="Never off: without it the person would keep a wrong number. Change its text, not its existence.",
            moment=MOMENT_ACTION,
            verrouille=True,
            variables=("numero",),
        ),
        Motif(
            id=RENDU_DE_MONNAIE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Après un enregistrement : le rendu de monnaie",
            libelle_en="After a save: the change to give back",
            quand_fr="Après la phrase de l'agent qui confirme l'enregistrement, quand la personne paie en espèces avec un billet : le code dit la monnaie à rendre, puis la question qui suit l'enregistrement. « {billet} » et « {monnaie} » sont remplacés par les montants en lettres : une phrase sans l'un d'eux est refusée.",
            quand_en="After the agent's sentence confirming the save, when the person pays cash with a note: the code says the change to give back, then the follow-up question. « {billet} » and « {monnaie} » are replaced by the amounts in words: a sentence without either is refused.",
            a_un_delai=False,
            variantes_defaut=("Sur votre billet de {billet}, on vous rend {monnaie}.", "Sur votre billet de {billet}, on vous rendra {monnaie}."),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Jamais éteinte : sans elle, la personne ne saurait pas la monnaie à rendre. On change son texte, pas son existence.",
            eteinte_en="Never off: without it the person would not hear the change. Change its text, not its existence.",
            moment=MOMENT_ACTION,
            verrouille=True,
            variables=("billet", "monnaie"),
        ),
        Motif(
            id=CONFIRMATION_REGLEE,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Après un enregistrement : « c'est enregistré », quand l'agent n'a pas pu le dire",
            libelle_en="After a save: « it's saved », when the agent could not say it",
            quand_fr="Quand la commande vient d'être enregistrée et que l'agent, relancé, n'a pas dit sa confirmation : le code dit cette phrase, puis le numéro, le rendu et la question qui suivent l'enregistrement. Jamais dite quand l'agent a confirmé lui-même.",
            quand_en="When the order has just been saved and the agent, asked again, did not say its confirmation: the code says this sentence, then the number, the change and the follow-up question. Never said when the agent confirmed it itself.",
            a_un_delai=False,
            variantes_defaut=("C'est enregistré.",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Jamais éteinte : sans elle, la personne n'entendrait pas que sa commande est enregistrée. On change son texte, pas son existence.",
            eteinte_en="Never off: without it the person would not hear that the order is saved. Change its text, not its existence.",
            moment=MOMENT_ACTION,
            verrouille=True,
        ),
        Motif(
            id=NUMERO_DICTE_RELU,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Avant l'enregistrement : le numéro dicté relu",
            libelle_en="Before the save: the dictated number read back",
            quand_fr="Quand la personne dicte un numéro (autre que celui qui s'affiche), le code le relit par paires avant d'enregistrer et attend son « oui ». « {numero} » est remplacé par le numéro.",
            quand_en="When the person dictates a number (other than the displayed one), the code reads it back in pairs before saving and waits for a « yes ». « {numero} » is replaced by the number.",
            a_un_delai=False,
            variantes_defaut=("Je note le {numero}, c'est bon ?",),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Le numéro dicté est enregistré dès qu'il est dit, sans relecture.",
            eteinte_en="The dictated number is saved as soon as it is said, without read-back.",
            moment=MOMENT_ACTION,
            variables=("numero",),
        ),
        Motif(
            id=NUMERO_RETENU,
            famille=FAMILLE_ANNONCE,
            libelle_fr="Le numéro dicté, retenu",
            libelle_en="The dictated number, kept",
            quand_fr="Quand la personne dicte un numéro et qu'il n'est pas relu avec une question, le code le dit tel que retenu, après la phrase de l'agent et avant la suite. « {numero} » est remplacé par le numéro : une phrase sans « {numero} » est refusée.",
            quand_en="When the person dictates a number that is not read back with a question, the code says it as kept, after the agent's sentence and before what follows. « {numero} » is replaced by the number: a sentence without « {numero} » is refused.",
            a_un_delai=False,
            variantes_defaut=("Je note le {numero}.", "C'est noté, le {numero}."),
            delai_defaut_s=None,
            actif_par_defaut=True,
            eteinte_fr="Jamais éteinte : sans elle, la personne n'entendrait pas le numéro retenu. On change son texte, pas son existence.",
            eteinte_en="Never off: without it the person would not hear the number kept. Change its text, not its existence.",
            moment=MOMENT_ACTION,
            verrouille=True,
            variables=("numero",),
        ),
    )
}

# Les motifs d'un problème (déclenchés par un fait) : un compteur dans l'appel, jamais de délai.
# C6 : la liste FERMÉE des phrases que le code dit encore mot pour mot (les autres sont dites par le modèle d'après les faits). Complétée par chaque commit de C6 qui rend un motif neuf.
PHRASES_DU_CODE = frozenset({TOTAL_RELECTURE, TOTAL_APRES_CORRECTION, TOTAL_APRES_CHANGEMENT, NUMERO_DE_COMMANDE_CHANGE, RENDU_DE_MONNAIE, NUMERO_RETENU, NUMERO_DICTE_RELU, NUMERO_AFFICHE_GARDE,
                             APRES_ENREGISTREMENT, CONFIRMATION_REGLEE})

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
                "sortie_par_le_code": m.sortie_par_le_code,
                "verrouille": m.verrouille,
                "variables": list(m.variables),
            }
            for m in MOTIFS.values()
        ],
    }

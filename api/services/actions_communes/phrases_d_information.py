"""[.mark] Les phrases d'information que le code PROPOSE au modèle quand une donnée manque ou se cite : UNE place (plan final Partie 1, lot 1, n° 82).

Avant : cinq façons de dire « je ne peux pas le garantir » et deux façons de nommer la source (« D'après la fiche », « D'après nos articles »), écrites en dur
dans l'allergie, la lecture d'un article, le socle du moteur et le service client. Le modèle dit ces faits avec ses mots (aucune de ces phrases ne lui est
donnée) ; le code ne les dit lui-même que dans le repli. Les textes sont ceux d'avant, mot pour mot.
"""

from __future__ import annotations

NON_CONFIRMABLE = "Je ne peux pas vous le confirmer."
PAS_SUR = "la fiche ne le précise pas, l'équipe peut vous répondre."
NON_GARANTI = "je ne peux pas le garantir : l'équipe peut vous le confirmer."
# Consigne donnée AU MODÈLE (ligne 82) quand la fiche ne dit rien : il la dit avec ses mots, le code ne la dit jamais.
CONSIGNE_NON_GARANTI = "dis-lui que tu ne peux pas le garantir et que l'équipe pourra le confirmer"
# Consigne donnée AU MODÈLE quand un retour liste des noms (rubrique, « sans », par ingrédient) : la liste complète est dans les faits, il en dit quelques-uns avec ses mots (aucun nombre écrit).
CONSIGNE_QUELQUES_NOMS = "dis-lui quelques noms avec tes mots, puis propose-lui d'en dire plus ; la liste complète est dans les faits"
POUR_LES_AUTRES_NON_GARANTI = "Pour les autres, je ne peux pas le garantir."
POUR_LES_AUTRES_NON_CONFIRMABLE = "Pour les autres, je ne peux pas vous le confirmer."
CA_DEPEND_DU_CHOIX_NON_GARANTI = "ça dépend du choix : je ne peux pas le garantir."

SOURCE_FICHE = "D'après la fiche"
SOURCE_FICHE_DU_RESTAURANT = "D'après la fiche du restaurant"
SOURCE_ARTICLES = "D'après nos articles"

NOUVELLE_COMMANDE_PROPOSEE = "Votre commande est annulée, je ne peux plus rien y ajouter. Voulez-vous en passer une nouvelle ?"  # DC5 : un refus suivi d'une question, proposée au modèle

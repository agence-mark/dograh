# Phrases du code à rendre au modèle (lot 1, I-7)

Chaque ligne est une phrase écrite en dur dans le moteur qui ne relève d'AUCUNE exception du § 2 du plan (relecture, total, numéro, confirmation, fait accompli qui
engage, phrases réglables DC4 et DC10, repli de panne). Le lot 7 les rend au modèle : le code propose un fait et une consigne, le modèle dit la phrase.
Triées par nature. Les phrases qui relèvent d'une exception sont dans `api/services/commande/phrases_dites_par_le_code.py` (texte inchangé, exception nommée) ;
les phrases d'information (« je ne peux pas le garantir », « d'après la fiche ») sont des propositions faites au modèle, rangées une fois dans
`api/services/actions_communes/phrases_d_information.py`.

Lignes lues à la fin du lot 1. Le tri est mécanique (forme de la phrase) : l'auditeur tranche les lignes marquées « à vérifier ».

| Où | Phrase | Nature |
|---|---|---|
| `db/bases_clients/restauration_commande.py:190` | Ce choix n'existe pas pour ce produit. | explication ou refus |
| `db/bases_clients/restauration_commande.py:194` | Quantité de choix invalide. | explication ou refus |
| `db/bases_clients/restauration_commande.py:196` |  n'est plus disponible. | explication ou refus |
| `db/bases_clients/restauration_commande.py:200` |  ne se prend pas plus de  | explication ou refus |
| `db/bases_clients/restauration_commande.py:233` | Il faut choisir :  | explication ou refus |
| `db/bases_clients/restauration_commande.py:235` | Pas plus de  | explication ou refus |
| `db/bases_clients/restauration_commande.py:284` | Quantité de choix invalide. | explication ou refus |
| `db/bases_clients/restauration_commande.py:287` | Ce choix n'existe pas dans cette formule. | explication ou refus |
| `db/bases_clients/restauration_commande.py:289` | Un élément de la formule n'est plus disponible. | explication ou refus |
| `db/bases_clients/restauration_commande.py:292` | Pas plus de  | explication ou refus |
| `db/bases_clients/restauration_commande.py:305` | Une seule alternative. | explication ou refus |
| `db/bases_clients/restauration_commande.py:309` | Il faut choisir :  | explication ou refus |
| `db/bases_clients/restauration_commande.py:320` | On ne peut pas retirer :  | explication ou refus |
| `db/bases_clients/restauration_commande.py:384` | Ce produit n'est pas à la carte. | explication ou refus |
| `db/bases_clients/restauration_commande.py:386` |  n'est plus disponible. | explication ou refus |
| `db/bases_clients/restauration_commande.py:394` | Le prix ne correspond pas à la carte. | explication ou refus |
| `db/bases_clients/restauration_commande.py:399` | On ne peut pas retirer :  | explication ou refus |
| `db/bases_clients/restauration_commande.py:437` | Nous ne livrons pas à cette adresse. | explication ou refus |
| `db/bases_clients/restauration_commande.py:440` | Le minimum de commande est de  | explication ou refus |
| `db/bases_clients/restauration_commande.py:486` | Je n'ai pas compris le mode de la commande. | explication ou refus |
| `db/bases_clients/restauration_commande.py:668` | Je ne prends pas de commande pour plus tard. | explication ou refus |
| `db/bases_clients/restauration_commande.py:674` |  : pour quand la voulez-vous ? | question |
| `db/bases_clients/restauration_commande.py:674` | Je prends les commandes jusqu'à  | explication ou refus |
| `db/bases_clients/restauration_commande.py:676` | C'est trop tôt pour moi. | explication ou refus |
| `db/bases_clients/restauration_commande.py:690` | Ce créneau est complet, je peux vous proposer  | explication ou refus |
| `db/bases_clients/restauration_commande.py:725` | Je n'ai pas compris le mode de la commande. | explication ou refus |
| `db/bases_clients/restauration_commande.py:727` | Qu'est-ce que je vous mets ? | question |
| `db/bases_clients/restauration_commande.py:729` | Quel est votre numéro de téléphone ? | question |
| `db/bases_clients/restauration_commande.py:731` | Quelle est l'adresse de livraison ? | question |
| `db/bases_clients/restauration_commande.py:733` | Je dois situer l'adresse de livraison. | explication ou refus |
| `db/bases_clients/restauration_commande.py:735` | Je vous relis la commande avant de l'enregistrer. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `db/bases_clients/restauration_commande.py:737` | Origine de la commande invalide. | explication ou refus |
| `db/bases_clients/restauration_commande.py:739` | L'heure demandée n'est pas valable. | explication ou refus |
| `db/bases_clients/restauration_commande.py:741` | Prénom trop long. | explication ou refus |
| `db/bases_clients/restauration_commande.py:774` | Cette remise ne s'applique pas à votre commande. | explication ou refus |
| `db/bases_clients/restauration_commande.py:788` | Vous réglez comment ? | question |
| `db/bases_clients/restauration_commande.py:793` | Ce moyen de paiement n'est pas accepté. | explication ou refus |
| `db/bases_clients/restauration_commande.py:797` | Le montant en titres-restaurant dépasse le plafond. | explication ou refus |
| `db/bases_clients/restauration_commande.py:802` | Les titres-restaurant ne paient pas l'alcool. | explication ou refus |
| `db/bases_clients/restauration_commande.py:805` | On ne rend pas la monnaie sur un titre-restaurant. | explication ou refus |
| `db/bases_clients/restauration_commande.py:807` | Montant de paiement invalide. | explication ou refus |
| `db/bases_clients/restauration_commande.py:809` | Le règlement ne couvre pas exactement le total. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `db/bases_clients/restauration_commande.py:841` | Votre commande est déjà enregistrée pour  | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `db/bases_clients/restauration_commande.py:841` | Votre commande est déjà enregistrée. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `db/bases_clients/restauration_commande.py:1017` | Je ne trouve pas cette commande. | explication ou refus |
| `services/actions_communes/parole.py:37` | - Ta réponse précédente n'avait pas d'appel d'outil : elle n'a pas été dite, et rien n'est changé. | explication ou refus |
| `services/actions_communes/repli.py:18` | - Ta réponse précédente n'avait pas d'appel d'outil après le refus de ta fiche : elle n'a pas été dite, et rie | explication ou refus |
| `services/commande/moteur/articles.py:140` |  n'est plus disponible. | explication ou refus |
| `services/commande/moteur/articles.py:150` |  : pas plus de  | explication ou refus |
| `services/commande/moteur/articles.py:150` |  n'est pas pris. | explication ou refus |
| `services/commande/moteur/articles.py:220` |  ne se prend pas avec des choix. | explication ou refus |
| `services/commande/moteur/articles.py:241` | Vous voulez dire :  | explication ou refus |
| `services/commande/moteur/articles.py:249` | Je n'ai pas «  | explication ou refus |
| `services/commande/moteur/articles.py:250` |  Le plus proche :  | explication ou refus |
| `services/commande/moteur/articles.py:276` | Pour quelle étape :  | explication ou refus |
| `services/commande/moteur/articles.py:278` | Je n'ai pas «  | explication ou refus |
| `services/commande/moteur/articles.py:294` | Sur lequel :  | explication ou refus |
| `services/commande/moteur/articles.py:368` | Qu'est-ce qu'il faut retirer ? | question |
| `services/commande/moteur/articles.py:372` |  sur quelle moitié :  | explication ou refus |
| `services/commande/moteur/articles.py:407` | Vous voulez retirer :  | explication ou refus |
| `services/commande/moteur/articles.py:411` | . On peut retirer :  | explication ou refus |
| `services/commande/moteur/articles.py:411` | On ne peut pas retirer «  | explication ou refus |
| `services/commande/moteur/articles.py:423` | Je ne peux pas noter cette demande. | explication ou refus |
| `services/commande/moteur/articles.py:435` | Je ne peux pas noter cette demande. | explication ou refus |
| `services/commande/moteur/articles.py:454` | Je ne connais pas ce code. | explication ou refus |
| `services/commande/moteur/articles.py:463` |  s'appliquera dès que votre commande y donne droit. | explication ou refus |
| `services/commande/moteur/articles.py:641` | Vous voulez dire :  | explication ou refus |
| `services/commande/moteur/articles.py:648` |  Le plus proche :  | explication ou refus |
| `services/commande/moteur/articles.py:648` | Je ne trouve pas «  | explication ou refus |
| `services/commande/moteur/articles.py:652` |  » n'est pas disponible en ce moment. | explication ou refus |
| `services/commande/moteur/articles.py:664` | , c'est beaucoup : je vous mets combien exactement ? | question |
| `services/commande/moteur/articles.py:692` |  Il reste :  | explication ou refus |
| `services/commande/moteur/articles.py:692` |  n'est plus disponible. | explication ou refus |
| `services/commande/moteur/articles.py:808` | Combien exactement ? | question |
| `services/commande/moteur/articles.py:932` |  n'est plus disponible. | explication ou refus |
| `services/commande/moteur/articles.py:949` |  n'est plus au catalogue. | explication ou refus |
| `services/commande/moteur/articles.py:964` |  n'est plus disponible. | explication ou refus |
| `services/commande/moteur/articles.py:1018` | Il n'y a encore rien dans la commande. | explication ou refus |
| `services/commande/moteur/articles.py:1025` | Il n'y a pas de ligne  | explication ou refus |
| `services/commande/moteur/articles.py:1027` | Laquelle voulez-vous changer ? | question |
| `services/commande/moteur/articles.py:1042` |  » dans la commande. | explication ou refus |
| `services/commande/moteur/articles.py:1042` | Je ne trouve pas «  | explication ou refus |
| `services/commande/moteur/articles.py:1077` | Combien exactement ? | question |
| `services/commande/moteur/articles.py:1084` | Combien exactement ? | question |
| `services/commande/moteur/articles.py:1088` | Qu'est-ce que je change ? | question |
| `services/commande/moteur/enregistrement.py:51` | Je n'ai pas bien compris le numéro : vous pouvez le redire ? | question |
| `services/commande/moteur/enregistrement.py:57` | Quel numéro je note ? | question |
| `services/commande/moteur/enregistrement.py:64` | Quel est votre numéro de téléphone ? | question |
| `services/commande/moteur/enregistrement.py:70` | À quel nom je mets la commande ? | question |
| `services/commande/moteur/enregistrement.py:200` | Je n'ai pas bien compris le numéro : vous pouvez le redire ? | question |
| `services/commande/moteur/enregistrement.py:225` | Votre commande est déjà enregistrée. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/commande/moteur/lecture.py:37` | La commande est vide pour le moment. | explication ou refus |
| `services/commande/moteur/lecture.py:117` | Pas d'offre en ce moment. | explication ou refus |
| `services/commande/moteur/lecture.py:155` | Il vous manque encore un article pour avoir  | explication ou refus |
| `services/commande/moteur/lecture.py:166` | Il vous manque  | explication ou refus |
| `services/commande/moteur/lecture.py:182` | Quel est le numéro de la commande ? | question |
| `services/commande/moteur/lecture.py:184` | Je ne trouve pas de commande, ni aujourd'hui ni sous ce numéro. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/commande/moteur/lecture.py:189` | . Laquelle ? | question |
| `services/commande/moteur/lecture.py:189` | Vous en avez plusieurs :  | explication ou refus |
| `services/commande/moteur/prealables.py:330` | Nous ne prenons pas de commande en ce moment. | explication ou refus |
| `services/commande/moteur/prealables.py:345` | Nous ne prenons pas de commande en ce moment. | explication ou refus |
| `services/commande/moteur/prealables.py:349` | Ce sera prêt  | explication ou refus |
| `services/commande/moteur/reglement.py:113` | Vous réglez comment ? | question |
| `services/commande/moteur/reglement.py:119` | Ce moyen de paiement n'est pas accepté. On prend :  | explication ou refus |
| `services/commande/moteur/reglement.py:125` | Quel montant exactement ? | question |
| `services/commande/moteur/reglement.py:127` | Et le reste, vous le réglez comment ? | question |
| `services/commande/moteur/reglement.py:136` | Sur quel règlement le billet ? | question |
| `services/commande/moteur/reglement.py:138` | Le billet ne couvre pas ce règlement. | explication ou refus |
| `services/commande/moteur/reglement.py:210` | Quel montant exactement ? | question |
| `services/commande/porte.py:93` | le code vient de dire le minimum et ce qui manque : ta phrase suit, sans aucun chiffre ; demande-lui ce qu'ell | explication ou refus |
| `services/commande/porte.py:94` | le code vient de lui dire ce qui est refusé et pourquoi : ta phrase suit, sans le redire | explication ou refus |
| `services/commande/porte.py:353` | Pour quel jour et à quelle heure, alors ? | question |
| `services/commande/porte.py:1105` | Je ne l'enregistre pas. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/reservation/moteur.py:72` | Je ne peux prendre qu'une réservation par appel, et celle de cet appel est annulée. Je vous passe à l'équipe p | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/reservation/moteur.py:151` | Pour combien de personnes ? | question |
| `services/reservation/moteur.py:155` | Pour quel jour ? | question |
| `services/reservation/moteur.py:162` | Pour quel jour ? | question |
| `services/reservation/moteur.py:168` | Nous sommes complets ce jour-là. | explication ou refus |
| `services/reservation/moteur.py:175` | Nous sommes complets ce jour-là, pour le  | explication ou refus |
| `services/reservation/moteur.py:181` | Il y a de la place à  | explication ou refus |
| `services/reservation/moteur.py:206` | Vous avez déjà une réservation dans cet appel : pour la changer, dites ce qui change. | explication ou refus |
| `services/reservation/moteur.py:245` | Pour combien de personnes ? | question |
| `services/reservation/moteur.py:249` | Pour quel jour ? | question |
| `services/reservation/moteur.py:261` | À quel nom je mets la réservation ? | question |
| `services/reservation/moteur.py:264` | Quel est votre numéro de téléphone ? | question |
| `services/reservation/moteur.py:268` | Je n'ai pas bien compris le numéro : vous pouvez le redire ? | question |
| `services/reservation/moteur.py:276` | Nous sommes complets ce jour-là. | explication ou refus |
| `services/reservation/moteur.py:280` | Nous ne pouvons pas à cette heure-là. Je peux vous proposer  | explication ou refus |
| `services/reservation/moteur.py:329` | Sous quel nom, et pour quel jour ? | question |
| `services/reservation/moteur.py:333` | Je ne trouve pas de réservation à venir. | explication ou refus |
| `services/reservation/moteur.py:361` | Sous quel nom, et pour quel jour ? | question |
| `services/reservation/moteur.py:374` | Je ne trouve pas de réservation à venir. | explication ou refus |
| `services/reservation/moteur.py:378` | Vous avez une réservation  | explication ou refus |
| `services/reservation/moteur.py:382` | . Laquelle ? | question |
| `services/reservation/moteur.py:382` | Vous en avez plusieurs :  | explication ou refus |
| `services/reservation/moteur.py:436` | Cette réservation est déjà annulée. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/reservation/moteur.py:461` | À quelle heure ? | question |
| `services/reservation/moteur.py:485` | Rien ne change : votre réservation reste  | explication ou refus |
| `services/reservation/moteur.py:487` | Qu'est-ce que je change : l'heure, le nombre de personnes ? | question |
| `services/reservation/moteur.py:492` | . C'est bon ? | question |
| `services/reservation/moteur.py:492` | Je change votre réservation :  | explication ou refus |
| `services/reservation/moteur.py:505` | Cette réservation est déjà annulée. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/reservation/moteur.py:514` | Je peux aussi la déplacer. Vous voulez annuler la réservation  | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/reservation/porte.py:102` | dis-lui ce qu'elle veut changer | explication ou refus |
| `services/reservation/porte.py:121` | propose-lui de laisser un message à l'équipe | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:245` | , la carte est  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:248` | Je ne peux pas vous garantir ce qui est  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:279` | , la carte est  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:280` | Je ne peux pas vous garantir ce qui est  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:358` | Pour cette chose,  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:381` |  ne contient pas  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:387` | Ça dépend : avec  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:391` | Ça dépend du choix, et  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:392` |  ne contient pas  | explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:395` | l'allergie de la personne est connue : réponds-lui avec tes mots d'après faits.allergie ; ce qui est à confirm | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |
| `services/restauration/source_commande.py:134` | Pour quel jour ? | question |
| `services/restauration/source_commande.py:140` |  : pour quel jour ? | question |
| `services/restauration/source_commande.py:140` | Il est déjà plus de  | explication ou refus |
| `services/restauration/source_commande.py:149` | À quelle heure,  | explication ou refus |
| `services/restauration/source_commande.py:152` | À quelle heure exactement ? | question |
| `services/restauration/source_commande.py:159` | Cette heure est déjà passée, pour quelle heure ? | question |
| `services/restauration/source_commande.py:425` | Je ne peux pas envoyer de message pour le moment. | explication ou refus |
| `services/restauration/source_commande.py:427` | C'est déjà parti, ou je ne peux pas l'envoyer à ce numéro. | à vérifier : exception possible (total, numéro, relecture, confirmation, fait accompli) |

Total : 163 phrases.

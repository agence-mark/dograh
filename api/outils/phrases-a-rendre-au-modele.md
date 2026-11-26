# Phrases du code à rendre au modèle (lot 1, I-7)

Chaque ligne est une phrase écrite en dur dans le moteur. La colonne « Nature » dit une chose et une seule : « rendue au modèle (lot 7) » (le code propose un fait et une
consigne, le modèle dit la phrase ; aucune exception) ou « exception du § 2 : <laquelle> » (relecture, total, numéro, confirmation, fait accompli qui engage, phrases
réglables DC4 et DC10 ; DC5 et le repli de panne n'en sont pas). Depuis C6 n° 12 (décision d'Evan 25/11 9 h 30), le code ne dit plus que les motifs réglés de la liste fermée `PHRASES_DU_CODE`
(`api/services/phrases/catalogue.py`) ; les phrases d'information et de proposition (« je ne peux pas le garantir », « d'après la fiche », « voulez-vous en passer une nouvelle ? ») sont des
propositions faites au modèle, rangées une fois dans `api/services/actions_communes/phrases_d_information.py`.

Lignes lues à la fin du lot 1, reprises au lot 2 (audit). Le tri est mécanique (forme de la phrase) ; les anciennes lignes « à vérifier » sont tranchées une par une.

| Où | Phrase | Nature |
|---|---|---|
| `db/bases_clients/restauration_commande.py:190` | Ce choix n'existe pas pour ce produit. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:194` | Quantité de choix invalide. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:196` |  n'est plus disponible. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:200` |  ne se prend pas plus de  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:233` | Il faut choisir :  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:235` | Pas plus de  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:284` | Quantité de choix invalide. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:287` | Ce choix n'existe pas dans cette formule. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:289` | Un élément de la formule n'est plus disponible. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:292` | Pas plus de  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:305` | Une seule alternative. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:309` | Il faut choisir :  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:320` | On ne peut pas retirer :  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:384` | Ce produit n'est pas à la carte. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:386` |  n'est plus disponible. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:394` | Le prix ne correspond pas à la carte. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:399` | On ne peut pas retirer :  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:437` | Nous ne livrons pas à cette adresse. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:440` | Le minimum de commande est de  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:486` | Je n'ai pas compris le mode de la commande. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:668` | Je ne prends pas de commande pour plus tard. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:674` |  : pour quand la voulez-vous ? | rendue au modèle (lot 7) : question |
| `db/bases_clients/restauration_commande.py:674` | Je prends les commandes jusqu'à  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:676` | C'est trop tôt pour moi. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:690` | Ce créneau est complet, je peux vous proposer  | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:725` | Je n'ai pas compris le mode de la commande. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:727` | Qu'est-ce que je vous mets ? | rendue au modèle (lot 7) : question |
| `db/bases_clients/restauration_commande.py:729` | Quel est votre numéro de téléphone ? | rendue au modèle (lot 7) : question |
| `db/bases_clients/restauration_commande.py:731` | Quelle est l'adresse de livraison ? | rendue au modèle (lot 7) : question |
| `db/bases_clients/restauration_commande.py:733` | Je dois situer l'adresse de livraison. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:735` | Je vous relis la commande avant de l'enregistrer. | rendue au modèle (lot 7) |
| `db/bases_clients/restauration_commande.py:737` | Origine de la commande invalide. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:739` | L'heure demandée n'est pas valable. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:741` | Prénom trop long. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:774` | Cette remise ne s'applique pas à votre commande. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:788` | Vous réglez comment ? | rendue au modèle (lot 7) : question |
| `db/bases_clients/restauration_commande.py:793` | Ce moyen de paiement n'est pas accepté. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:797` | Le montant en titres-restaurant dépasse le plafond. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:802` | Les titres-restaurant ne paient pas l'alcool. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:805` | On ne rend pas la monnaie sur un titre-restaurant. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:807` | Montant de paiement invalide. | rendue au modèle (lot 7) : explication ou refus |
| `db/bases_clients/restauration_commande.py:809` | Le règlement ne couvre pas exactement le total. | rendue au modèle (lot 7) |
| `db/bases_clients/restauration_commande.py:841` | Votre commande est déjà enregistrée pour  | exception du § 2 : fait accompli qui engage |
| `db/bases_clients/restauration_commande.py:841` | Votre commande est déjà enregistrée. | exception du § 2 : fait accompli qui engage |
| `db/bases_clients/restauration_commande.py:1017` | Je ne trouve pas cette commande. | rendue au modèle (lot 7) : explication ou refus |
| `services/actions_communes/parole.py:37` | - Ta réponse précédente n'avait pas d'appel d'outil : elle n'a pas été dite, et rien n'est changé. | rendue au modèle (lot 7) : explication ou refus |
| `services/actions_communes/repli.py:18` | - Ta réponse précédente n'avait pas d'appel d'outil après le refus de ta fiche : elle n'a pas été dite, et rie | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:140` |  n'est plus disponible. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:150` |  : pas plus de  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:150` |  n'est pas pris. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:220` |  ne se prend pas avec des choix. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:241` | Vous voulez dire :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:249` | Je n'ai pas «  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:250` |  Le plus proche :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:276` | Pour quelle étape :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:278` | Je n'ai pas «  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:294` | Sur lequel :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:368` | Qu'est-ce qu'il faut retirer ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/articles.py:372` |  sur quelle moitié :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:407` | Vous voulez retirer :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:411` | . On peut retirer :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:411` | On ne peut pas retirer «  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:423` | Je ne peux pas noter cette demande. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:435` | Je ne peux pas noter cette demande. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:454` | Je ne connais pas ce code. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:463` |  s'appliquera dès que votre commande y donne droit. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:641` | Vous voulez dire :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:648` |  Le plus proche :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:648` | Je ne trouve pas «  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:652` |  » n'est pas disponible en ce moment. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:664` | , c'est beaucoup : je vous mets combien exactement ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/articles.py:692` |  Il reste :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:692` |  n'est plus disponible. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:808` | Combien exactement ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/articles.py:932` |  n'est plus disponible. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:949` |  n'est plus au catalogue. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:964` |  n'est plus disponible. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:1018` | Il n'y a encore rien dans la commande. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:1025` | Il n'y a pas de ligne  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:1027` | Laquelle voulez-vous changer ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/articles.py:1042` |  » dans la commande. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:1042` | Je ne trouve pas «  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/articles.py:1077` | Combien exactement ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/articles.py:1084` | Combien exactement ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/articles.py:1088` | Qu'est-ce que je change ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/enregistrement.py:51` | Je n'ai pas bien compris le numéro : vous pouvez le redire ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/enregistrement.py:57` | Quel numéro je note ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/enregistrement.py:64` | Quel est votre numéro de téléphone ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/enregistrement.py:70` | À quel nom je mets la commande ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/enregistrement.py:200` | Je n'ai pas bien compris le numéro : vous pouvez le redire ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/enregistrement.py:225` | Votre commande est déjà enregistrée. | exception du § 2 : fait accompli qui engage |
| `services/commande/moteur/lecture.py:37` | La commande est vide pour le moment. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/lecture.py:117` | Pas d'offre en ce moment. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/lecture.py:155` | Il vous manque encore un article pour avoir  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/lecture.py:166` | Il vous manque  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/lecture.py:182` | Quel est le numéro de la commande ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/lecture.py:184` | Je ne trouve pas de commande, ni aujourd'hui ni sous ce numéro. | rendue au modèle (lot 7) |
| `services/commande/moteur/lecture.py:189` | . Laquelle ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/lecture.py:189` | Vous en avez plusieurs :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/prealables.py:330` | Nous ne prenons pas de commande en ce moment. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/prealables.py:345` | Nous ne prenons pas de commande en ce moment. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/prealables.py:349` | Ce sera prêt  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/reglement.py:113` | Vous réglez comment ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/reglement.py:119` | Ce moyen de paiement n'est pas accepté. On prend :  | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/reglement.py:125` | Quel montant exactement ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/reglement.py:127` | Et le reste, vous le réglez comment ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/reglement.py:136` | Sur quel règlement le billet ? | rendue au modèle (lot 7) : question |
| `services/commande/moteur/reglement.py:138` | Le billet ne couvre pas ce règlement. | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/moteur/reglement.py:210` | Quel montant exactement ? | rendue au modèle (lot 7) : question |
| `services/commande/porte.py:93` | le code vient de dire le minimum et ce qui manque : ta phrase suit, sans aucun chiffre ; demande-lui ce qu'ell | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/porte.py:94` | le code vient de lui dire ce qui est refusé et pourquoi : ta phrase suit, sans le redire | rendue au modèle (lot 7) : explication ou refus |
| `services/commande/porte.py:353` | Pour quel jour et à quelle heure, alors ? | rendue au modèle (lot 7) : question |
| `services/commande/textes_de_secours.py` (`annulee_en_cours`) | Je ne l'enregistre pas. | rendue au modèle (lot 7) : C6 n° 7, texte de secours gardé au journal pour le repli |
| `services/reservation/moteur.py:72` | Je ne peux prendre qu'une réservation par appel, et celle de cet appel est annulée. Je vous passe à l'équipe p | rendue au modèle (lot 7) |
| `services/reservation/moteur.py:151` | Pour combien de personnes ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:155` | Pour quel jour ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:162` | Pour quel jour ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:168` | Nous sommes complets ce jour-là. | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:175` | Nous sommes complets ce jour-là, pour le  | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:181` | Il y a de la place à  | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:206` | Vous avez déjà une réservation dans cet appel : pour la changer, dites ce qui change. | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:245` | Pour combien de personnes ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:249` | Pour quel jour ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:261` | À quel nom je mets la réservation ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:264` | Quel est votre numéro de téléphone ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:268` | Je n'ai pas bien compris le numéro : vous pouvez le redire ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:276` | Nous sommes complets ce jour-là. | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:280` | Nous ne pouvons pas à cette heure-là. Je peux vous proposer  | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:329` | Sous quel nom, et pour quel jour ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:333` | Je ne trouve pas de réservation à venir. | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:361` | Sous quel nom, et pour quel jour ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:374` | Je ne trouve pas de réservation à venir. | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:378` | Vous avez une réservation  | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:382` | . Laquelle ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:382` | Vous en avez plusieurs :  | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:436` | Cette réservation est déjà annulée. | exception du § 2 : fait accompli qui engage |
| `services/reservation/moteur.py:461` | À quelle heure ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:485` | Rien ne change : votre réservation reste  | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:487` | Qu'est-ce que je change : l'heure, le nombre de personnes ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:492` | . C'est bon ? | rendue au modèle (lot 7) : question |
| `services/reservation/moteur.py:492` | Je change votre réservation :  | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/moteur.py:505` | Cette réservation est déjà annulée. | exception du § 2 : fait accompli qui engage |
| `services/reservation/moteur.py:514` | Je peux aussi la déplacer. Vous voulez annuler la réservation  | rendue au modèle (lot 7) |
| `services/reservation/porte.py:102` | dis-lui ce qu'elle veut changer | rendue au modèle (lot 7) : explication ou refus |
| `services/reservation/porte.py:121` | propose-lui de laisser un message à l'équipe | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:245` | , la carte est  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:248` | Je ne peux pas vous garantir ce qui est  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:279` | , la carte est  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:280` | Je ne peux pas vous garantir ce qui est  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:358` | Pour cette chose,  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:381` |  ne contient pas  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:387` | Ça dépend : avec  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:391` | Ça dépend du choix, et  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/allergie_de_la_commande.py:392` |  ne contient pas  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/source_commande.py:134` | Pour quel jour ? | rendue au modèle (lot 7) : question |
| `services/restauration/source_commande.py:140` |  : pour quel jour ? | rendue au modèle (lot 7) : question |
| `services/restauration/source_commande.py:140` | Il est déjà plus de  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/source_commande.py:149` | À quelle heure,  | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/source_commande.py:152` | À quelle heure exactement ? | rendue au modèle (lot 7) : question |
| `services/restauration/source_commande.py:159` | Cette heure est déjà passée, pour quelle heure ? | rendue au modèle (lot 7) : question |
| `services/restauration/source_commande.py:425` | Je ne peux pas envoyer de message pour le moment. | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/source_commande.py:427` | C'est déjà parti, ou je ne peux pas l'envoyer à ce numéro. | rendue au modèle (lot 7) |

Total : 162 phrases (7b-C4 : ``PHRASE_PANNE_*`` retirées au commit 11 de C1, le fichier ne les cite plus ; plus aucun fichier du lot n'est à rendre, ``A_RENDRE`` est vide).
| `services/actions_communes/phrases_d_information.py` (`NOUVELLE_COMMANDE_PROPOSEE`) | Votre commande est annulée, je ne peux plus rien y ajouter. Voulez-vous en passer une nouvelle ? | rendue au modèle (lot 7) : refus suivi d'une question (DC5), proposée par le code ; le code ne la dit que dans le repli |
| `services/restauration/carte_et_allergenes/voir_un_article.py:115` (`INFO.SOURCE_FICHE`) | D'après la fiche, … ne contient pas … | rendue au modèle (lot 7) : explication ou refus, montée d'une constante du module commun |
| `services/restauration/carte_et_allergenes/voir_un_article.py:117` (`INFO.CA_DEPEND_DU_CHOIX_NON_GARANTI`) | Pour …, ça dépend du choix : je ne peux pas le garantir. | rendue au modèle (lot 7) : explication ou refus |
| `services/restauration/carte_et_allergenes/voir_un_article.py:119` (`INFO.POUR_LES_AUTRES_NON_GARANTI`) | Pour les autres, je ne peux pas le garantir. | rendue au modèle (lot 7) : explication ou refus |

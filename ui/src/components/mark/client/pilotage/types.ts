/**
 * [.mark] Partie 3, L5b : la forme de la réponse de la page de pilotage d'un client (`GET /vues-equipe/pilotage/{organisation}`),
 * telle que le serveur la rend (`api/routes/pilotage_client.py`). Le client d'API généré porte la même forme ; ces alias évitent
 * qu'un écran en dépende fichier par fichier.
 */
import type { Pilotage } from "@/client/types.gen";

export type Periode = Pilotage["periode"];
export const PERIODES: Periode[] = ["24h", "7j", "30j", "90j"];
export const PERIODE_PAR_DEFAUT: Periode = "7j";
/** Le libellé court de la maquette (« 24 h », « 7 j »). */
export const LIBELLE_PERIODE: Record<Periode, string> = { "24h": "24 h", "7j": "7 j", "30j": "30 j", "90j": "90 j" };

export type PilotageClient = Pilotage;
export type ChiffrePilotage = NonNullable<Pilotage["chiffres"]>[number];
export type AgentPilotage = NonNullable<Pilotage["agents"]>[number];
export type MotifPilotage = NonNullable<Pilotage["motifs"]>[number];

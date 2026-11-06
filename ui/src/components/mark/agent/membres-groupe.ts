/**
 * [.mark] Les membres d'un groupe d'agents, pour le menu du début de la ligne d'onglets (E37 bis). Pur : la réponse de
 * `GET /workflow/{id}/groupe` entre, la liste ordonnée (principal d'abord) sort. Un agent seul n'a pas de menu.
 */
import type { GroupeResponse } from "@/client/types.gen";

export type MembreMenu = { id: number; nom: string; principal: boolean };

export function membresDuGroupe(groupe: GroupeResponse | null | undefined): MembreMenu[] {
    if (!groupe?.principal) return [];
    return [
        { id: groupe.principal.id, nom: groupe.principal.name, principal: true },
        ...(groupe.specialises ?? []).map((m) => ({ id: m.id, nom: m.name, principal: false })),
    ];
}

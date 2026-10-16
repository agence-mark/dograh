/**
 * [.mark] Chantier agents-specialises, lots 10 et 12 : lire les groupes dans la liste d'agents et les
 * dossiers. Pur (aucun accès réseau) : la liste d'agents et les liens des groupes (route
 * ``GET /workflow/groupes``) entrent, des groupes et un arbre de dossiers sortent.
 */
import type { FolderResponse, LienDeGroupe, WorkflowListResponse } from "@/client/types.gen";

export type LienDuGroupe = Pick<LienDeGroupe, "id" | "role" | "agent_principal_id" | "agents_specialises" | "cerveau_propre">;

export interface GroupeDAgents<A extends { id: number }> {
    principal: A;
    specialises: A[];
}

/**
 * Les groupes dont le principal est parmi ``agents`` (les agents actifs de la liste). Un spécialisé
 * dont le principal n'est pas dans la liste reste un agent seul pour l'écran (jamais caché).
 * L'ordre des spécialisés est celui de la liste ``agents_specialises`` du principal.
 */
export const grouperLesAgents = <A extends { id: number }>(
    agents: A[],
    liens: LienDuGroupe[],
): { groupes: Array<GroupeDAgents<A>>; seuls: A[] } => {
    const parId = new Map(agents.map((a) => [a.id, a]));
    const groupes: Array<GroupeDAgents<A>> = [];
    const dansUnGroupe = new Set<number>();
    for (const lien of liens) {
        if (lien.role !== "principal") continue;
        const principal = parId.get(lien.id);
        if (!principal) continue;
        const specialises = (lien.agents_specialises ?? [])
            .map((id) => parId.get(id))
            .filter((a): a is A => a !== undefined);
        groupes.push({ principal, specialises });
        dansUnGroupe.add(principal.id);
        for (const s of specialises) dansUnGroupe.add(s.id);
    }
    return { groupes, seuls: agents.filter((a) => !dansUnGroupe.has(a.id)) };
};

/** Pour chaque agent d'un groupe : son rôle et le nom de son principal (pour le badge). */
export const rolesDesAgents = (
    liens: LienDuGroupe[],
    nomsParId: Map<number, string>,
): Map<number, { role: "principal" | "specialise"; principalId: number | null; principalNom: string | null; cerveauPropre: boolean; specialises: number[] }> => {
    const sortie = new Map<number, { role: "principal" | "specialise"; principalId: number | null; principalNom: string | null; cerveauPropre: boolean; specialises: number[] }>();
    for (const lien of liens) {
        if (lien.role === "principal") {
            sortie.set(lien.id, {
                role: "principal",
                principalId: null,
                principalNom: null,
                cerveauPropre: false,
                specialises: lien.agents_specialises ?? [],
            });
        } else if (lien.role === "specialise" && typeof lien.agent_principal_id === "number") {
            sortie.set(lien.id, {
                role: "specialise",
                principalId: lien.agent_principal_id,
                principalNom: nomsParId.get(lien.agent_principal_id) ?? null,
                cerveauPropre: lien.cerveau_propre === true,
                specialises: [],
            });
        }
    }
    return sortie;
};

export interface NoeudDeDossier {
    dossier: FolderResponse;
    enfants: NoeudDeDossier[];
}

/**
 * L'arbre des dossiers : les racines sont les dossiers sans parent (ou dont le parent n'est pas dans
 * la liste, jamais caché), triés par nom comme la liste ; les enfants de même. Un cycle (qui ne peut
 * pas arriver, la route le refuse) ne boucle pas : un dossier déjà posé n'est pas posé deux fois.
 */
export const arbreDesDossiers = (dossiers: FolderResponse[]): NoeudDeDossier[] => {
    const ids = new Set(dossiers.map((d) => d.id));
    const enfantsDe = new Map<number | null, FolderResponse[]>();
    for (const d of dossiers) {
        const parent = d.parent_id != null && ids.has(d.parent_id) && d.parent_id !== d.id ? d.parent_id : null;
        enfantsDe.set(parent, [...(enfantsDe.get(parent) ?? []), d]);
    }
    const pose = new Set<number>();
    const construire = (parent: number | null): NoeudDeDossier[] =>
        (enfantsDe.get(parent) ?? [])
            .slice()
            .sort((a, b) => a.name.localeCompare(b.name))
            .filter((d) => !pose.has(d.id))
            .map((d) => {
                pose.add(d.id);
                return { dossier: d, enfants: construire(d.id) };
            });
    return construire(null);
};

/** Les identifiants d'un dossier et de tous ses descendants (pour ne pas déplacer un dossier dans lui-même). */
export const descendants = (dossiers: FolderResponse[], id: number): Set<number> => {
    const sortie = new Set<number>([id]);
    let change = true;
    while (change) {
        change = false;
        for (const d of dossiers) {
            if (d.parent_id != null && sortie.has(d.parent_id) && !sortie.has(d.id)) {
                sortie.add(d.id);
                change = true;
            }
        }
    }
    return sortie;
};

export type AgentDeListe = WorkflowListResponse;

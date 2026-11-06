/**
 * [.mark] Partie 3, sous-lot 20 : « Dupliquer » de la barre au survol d'une étape. Une copie neuve (identifiant neuf, nom
 * « … (copie) », décalée), sans ses liaisons : on la relie ensuite. Les types limités à une seule instance (le début, le
 * prompt général) ne se dupliquent pas.
 */
import type { FlowNode } from "@/components/flow/types";
import { getNextNodeId } from "@/lib/utils";

export const DECALAGE_DE_LA_COPIE = { x: 40, y: 80 };

export function copieDeLEtape(noeuds: FlowNode[], id: string, suffixe: string, maxInstances?: number | null): FlowNode | null {
    const source = noeuds.find((n) => n.id === id);
    if (!source) return null;
    if (maxInstances != null && noeuds.filter((n) => n.type === source.type).length >= maxInstances) return null;
    const data = JSON.parse(JSON.stringify(source.data)) as FlowNode["data"] & { name?: string };
    if (typeof data.name === "string" && data.name) data.name = `${data.name} ${suffixe}`;
    return {
        ...source,
        id: getNextNodeId(noeuds),
        selected: false,
        position: { x: source.position.x + DECALAGE_DE_LA_COPIE.x, y: source.position.y + DECALAGE_DE_LA_COPIE.y },
        data,
    };
}

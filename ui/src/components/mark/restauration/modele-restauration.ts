"use client";

/**
 * [.mark] Module Restauration, lot 13 (F14) : « Nouvel agent › Partir du modèle Restauration ».
 *
 * Le modèle n'est proposé que si le module est allumé pour l'organisation (``GET /restauration/module``). Ce qu'il pose vient du serveur
 * (``GET /restauration/modele-reglages``) : les réglages d'agent à allumer (garde-fous des outils compris) et les kits d'outils à recevoir (lot 11).
 * Il ne pose ni prompt ni test : les prompts viennent du builder. Un kit absent de l'organisation est ignoré, jamais inventé.
 */
import { client } from "@/client/client.gen";

export interface ModeleRestauration {
    reglages: Record<string, unknown>;
    kits: string[];
}
type Entetes = Record<string, string> | undefined;
type Reponse<T> = { data?: T; error?: unknown };

const lire = <T>(p: Promise<unknown>) => p as Promise<Reponse<T>>;

/** Le modèle, ou ``null`` : module éteint, organisation sans base du client, ou serveur qui ne répond pas (le modèle n'est alors pas proposé). */
export async function lireLeModeleRestauration(entetes: Entetes): Promise<ModeleRestauration | null> {
    try {
        const module = await lire<{ actif: boolean }>(client.get({ url: "/api/v1/restauration/module", headers: entetes }));
        if (module.error || !module.data?.actif) return null;
        const modele = await lire<ModeleRestauration>(client.get({ url: "/api/v1/restauration/modele-reglages", headers: entetes }));
        return modele.error || !modele.data ? null : modele.data;
    } catch {
        return null;
    }
}

/** Pose les réglages du modèle sur l'agent (sans toucher aux autres) et reçoit les kits d'outils. Rend vrai si tout a été posé. */
export async function appliquerLeModeleRestauration(workflowId: number, modele: ModeleRestauration, entetes: Entetes): Promise<boolean> {
    const JSON_ENTETE = { "Content-Type": "application/json", ...(entetes ?? {}) };
    let tout = true;
    const lu = await lire<{ workflow_configurations?: Record<string, unknown> | null }>(client.get({ url: `/api/v1/workflow/fetch/${workflowId}`, headers: entetes }));
    const actuelles = lu.data?.workflow_configurations ?? {};
    const ecrit = await lire<unknown>(
        client.put({ url: `/api/v1/workflow/${workflowId}`, body: { workflow_configurations: { ...actuelles, ...modele.reglages } }, headers: JSON_ENTETE }),
    );
    if (ecrit.error) tout = false;
    const kits = await lire<{ id: number; name: string }[]>(client.get({ url: "/api/v1/tools/kits", headers: entetes }));
    if (kits.error || !kits.data) return false;
    for (const nom of modele.kits) {
        const kit = kits.data.find((k) => k.name === nom);
        if (!kit) continue;
        const r = await lire<unknown>(client.post({ url: `/api/v1/tools/kits/${kit.id}/appliquer`, body: {}, headers: JSON_ENTETE }));
        if (r.error) tout = false;
    }
    return tout;
}

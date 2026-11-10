// [.mark] Correctifs d'écran, point 15 : le logo des espaces. `GET /espaces` ne donne que la `logo_version` ; l'image se lit par
// `GET /espaces/{id}/logo` DERRIÈRE la session (jamais un lien public) : on la charge avec le jeton, on la garde en mémoire sous
// forme d'adresse locale (blob), une seule lecture par logo et par version. Un logo changé (autre version) se relit tout seul.
import { useEffect, useState } from "react";

import { lireLeLogoApiV1EspacesOrganizationIdLogoGet } from "@/client/sdk.gen";

type Ecouteur = () => void;
const ecouteurs = new Set<Ecouteur>();
/** La version du logo de chaque espace connu (absent ou null = pas de logo). */
const versions = new Map<number, string | null>();
/** Le logo déjà lu : sa version et son adresse locale (null = la lecture a échoué : on retombe sur l'initiale). */
const lus = new Map<number, { version: string; url: string | null }>();
const enCours = new Map<number, string>();

const prevenir = () => ecouteurs.forEach((e) => e());

async function charger(id: number, version: string) {
    if (enCours.get(id) === version) return;
    enCours.set(id, version);
    let url: string | null = null;
    try {
        const { data, error } = await lireLeLogoApiV1EspacesOrganizationIdLogoGet({ path: { organization_id: id }, parseAs: "blob", cache: "no-store" });
        // no-store : l'adresse est la même d'une version à l'autre ; la mémoire ci-dessus garde déjà une lecture par version.
        if (!error && data instanceof Blob && data.size > 0) url = URL.createObjectURL(data);
    } catch {
        url = null;
    }
    if (enCours.get(id) !== version) {
        if (url) URL.revokeObjectURL(url); // une version plus récente a pris la place, ou le logo a été retiré
        return;
    }
    enCours.delete(id);
    const ancien = lus.get(id);
    lus.set(id, { version, url });
    if (ancien?.url) URL.revokeObjectURL(ancien.url);
    prevenir();
}

/** Appelé à chaque lecture de `GET /espaces` : retient les versions, charge ce qui manque, oublie ce qui a été retiré. */
export function memoriserLogos(espaces: { id: number; logo_version?: string | null }[]): void {
    for (const e of espaces) {
        const v = e.logo_version ?? null;
        versions.set(e.id, v);
        if (v === null) {
            const ancien = lus.get(e.id);
            if (ancien?.url) URL.revokeObjectURL(ancien.url);
            lus.delete(e.id);
            enCours.delete(e.id);
        } else if (lus.get(e.id)?.version !== v) void charger(e.id, v);
    }
    prevenir();
}

function useAbonne(): void {
    const [, relire] = useState(0);
    useEffect(() => {
        const e: Ecouteur = () => relire((n) => n + 1);
        ecouteurs.add(e);
        return () => {
            ecouteurs.delete(e);
        };
    }, []);
}

/** Le client a-t-il un logo (d'après `GET /espaces`) ? Faux tant que la liste n'est pas lue. */
export function useAUnLogo(id: number | null): boolean {
    useAbonne();
    return id !== null && (versions.get(id) ?? null) !== null;
}

/** L'adresse locale du logo d'un espace, ou null (pas de logo, pas encore lu, lecture échouée). */
export function useLogoEspace(id: number | null): string | null {
    useAbonne();
    if (id === null) return null;
    const lu = lus.get(id);
    return lu && lu.version === versions.get(id) ? lu.url : null;
}

/** Pour les tests : repart d'une mémoire vide. */
export function oublierLesLogos(): void {
    versions.clear();
    lus.clear();
    enCours.clear();
}

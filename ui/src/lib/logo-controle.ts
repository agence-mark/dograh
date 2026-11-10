// [.mark] Correctifs d'écran, point 15 : le contrôle d'un logo AVANT l'envoi. Mêmes règles que le serveur
// (`api/services/equipe_mark/image_logo.py`, qui reste le juge : l'écran évite l'aller-retour, il ne le remplace pas).
// Le type est lu dans les octets (jamais l'extension ni `file.type`) ; PNG, JPEG et WebP seulement, un SVG est refusé.
export const LOGO_OCTETS_MAX = 1_048_576;
export const LOGO_COTE_MIN = 128;
export const LOGO_COTE_MAX = 1024;
export const LOGO_RATIO_MAX = 1.25;
export const LOGO_COTE_CONSEILLE = 512;

export type CodeLogo = "logo_vide" | "logo_trop_lourd" | "logo_format" | "logo_illisible" | "logo_dimensions" | "logo_ratio";
export type ResultatLogo =
    | { ok: true; format: "png" | "jpeg" | "webp"; largeur: number; hauteur: number }
    | { ok: false; code: CodeLogo };

const egal = (o: Uint8Array, debut: number, octets: number[]) => octets.every((v, i) => o[debut + i] === v);
const ascii = (s: string) => [...s].map((c) => c.charCodeAt(0));
const u16 = (o: Uint8Array, i: number) => (o[i] << 8) | o[i + 1];
const u32 = (o: Uint8Array, i: number) => ((o[i] << 24) | (o[i + 1] << 16) | (o[i + 2] << 8) | o[i + 3]) >>> 0;
const l16 = (o: Uint8Array, i: number) => o[i] | (o[i + 1] << 8);
const l24 = (o: Uint8Array, i: number) => o[i] | (o[i + 1] << 8) | (o[i + 2] << 16);

function png(o: Uint8Array): [number, number] | null {
    if (o.length < 24 || !egal(o, 12, ascii("IHDR"))) return null;
    return [u32(o, 16), u32(o, 20)];
}

const SOF = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);

function jpeg(o: Uint8Array): [number, number] | null {
    let i = 2;
    while (i + 4 <= o.length) {
        if (o[i] !== 0xff) return null;
        while (i < o.length && o[i] === 0xff) i += 1;
        if (i >= o.length) return null;
        const marqueur = o[i];
        i += 1;
        if (marqueur === 0x01 || marqueur === 0xd8 || (marqueur >= 0xd0 && marqueur <= 0xd7)) continue;
        if (marqueur === 0xd9 || marqueur === 0xda) return null;
        if (i + 2 > o.length) return null;
        if (SOF.has(marqueur)) return i + 7 > o.length ? null : [u16(o, i + 5), u16(o, i + 3)];
        const longueur = u16(o, i);
        if (longueur < 2) return null;
        i += longueur;
    }
    return null;
}

function webp(o: Uint8Array): [number, number] | null {
    if (o.length < 30) return null;
    if (egal(o, 12, ascii("VP8 "))) {
        if (!egal(o, 23, [0x9d, 0x01, 0x2a])) return null;
        return [l16(o, 26) & 0x3fff, l16(o, 28) & 0x3fff];
    }
    if (egal(o, 12, ascii("VP8L"))) {
        if (o[20] !== 0x2f) return null;
        const bits = (o[21] | (o[22] << 8) | (o[23] << 16) | (o[24] << 24)) >>> 0;
        return [(bits & 0x3fff) + 1, ((bits >>> 14) & 0x3fff) + 1];
    }
    if (egal(o, 12, ascii("VP8X"))) return [l24(o, 24) + 1, l24(o, 27) + 1];
    return null;
}

/** Contrôle les octets d'un logo (le fichier entier : sa taille compte). */
export function controlerLogo(octets: Uint8Array): ResultatLogo {
    if (octets.length === 0) return { ok: false, code: "logo_vide" };
    if (octets.length > LOGO_OCTETS_MAX) return { ok: false, code: "logo_trop_lourd" };
    let format: "png" | "jpeg" | "webp";
    let dim: [number, number] | null;
    if (egal(octets, 0, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) {
        format = "png";
        dim = png(octets);
    } else if (egal(octets, 0, [0xff, 0xd8, 0xff])) {
        format = "jpeg";
        dim = jpeg(octets);
    } else if (egal(octets, 0, ascii("RIFF")) && egal(octets, 8, ascii("WEBP"))) {
        format = "webp";
        dim = webp(octets);
    } else return { ok: false, code: "logo_format" };
    if (!dim || dim[0] < 1 || dim[1] < 1) return { ok: false, code: "logo_illisible" };
    const [largeur, hauteur] = dim;
    if (largeur < LOGO_COTE_MIN || hauteur < LOGO_COTE_MIN || largeur > LOGO_COTE_MAX || hauteur > LOGO_COTE_MAX)
        return { ok: false, code: "logo_dimensions" };
    if (largeur / hauteur > LOGO_RATIO_MAX || hauteur / largeur > LOGO_RATIO_MAX) return { ok: false, code: "logo_ratio" };
    return { ok: true, format, largeur, hauteur };
}

/** Lit le fichier choisi (jamais plus que la limite + 1 octet) puis le contrôle. */
export async function controlerFichierLogo(fichier: File): Promise<ResultatLogo> {
    if (fichier.size > LOGO_OCTETS_MAX) return { ok: false, code: "logo_trop_lourd" };
    return controlerLogo(new Uint8Array(await fichier.slice(0, LOGO_OCTETS_MAX + 1).arrayBuffer()));
}

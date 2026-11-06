/**
 * [.mark] U3 ter (E67) : la logique PURE de l'éditeur de tableau, partagée avec le portail. Sans écran, testée seule.
 *
 * Un tableau est la forme « liste » d'une variable (`mark_objets`) : des colonnes (libellé, type, ordre, qui l'a posée) et
 * des lignes (cases rangées par libellé de colonne). Rien n'est inventé : mêmes formes que `ColonneObjet` / `LigneObjet`.
 */
import type { ColonneObjet, LigneObjet } from "@/client/types.gen";

export type TypeColonne = NonNullable<ColonneObjet["type"]>;

export interface Tableau {
    colonnes: ColonneObjet[];
    lignes: LigneObjet[];
}

export const copie = (t: Tableau): Tableau => ({
    colonnes: t.colonnes.map((c) => ({ ...c })),
    lignes: t.lignes.map((l) => ({ ...l, valeurs: { ...(l.valeurs ?? {}) } })),
});

/** Le texte que reçoit l'agent : même règle que `api/services/objets_agent/rendu.py`. */
export const texteRecu = (t: Tableau): string => {
    if (t.colonnes.length === 0) return "";
    const entete = t.colonnes.map((c) => c.libelle).join(" | ");
    const lignes = t.lignes.map((l) => t.colonnes.map((c) => l.valeurs?.[c.libelle] ?? "").join(" | "));
    return [entete, ...lignes].join("\n");
};

const nouveauNom = (colonnes: ColonneObjet[]): string => {
    let n = colonnes.length + 1;
    while (colonnes.some((c) => c.libelle === `Colonne ${n}`)) n += 1;
    return `Colonne ${n}`;
};

export type PosePar = NonNullable<ColonneObjet["pose_par"]>;

/** `posePar` : « mark » dans Dograh, « client » dans le portail (le client ne verrouille pas ce qu'il pose). */
export const ajouterColonne = (t: Tableau, posePar: PosePar = "mark"): Tableau => {
    const c = copie(t);
    c.colonnes.push({ libelle: nouveauNom(c.colonnes), type: "texte", ordre: c.colonnes.length + 1, pose_par: posePar } as ColonneObjet);
    return c;
};

export const ajouterLigne = (t: Tableau): Tableau => {
    const c = copie(t);
    c.lignes.push({ ordre: c.lignes.length + 1, valeurs: {} } as LigneObjet);
    return c;
};

export const poserCase = (t: Tableau, ligne: number, libelle: string, valeur: string): Tableau => {
    const c = copie(t);
    while (c.lignes.length <= ligne) c.lignes.push({ ordre: c.lignes.length + 1, valeurs: {} } as LigneObjet);
    c.lignes[ligne].valeurs = { ...(c.lignes[ligne].valeurs ?? {}), [libelle]: valeur };
    return c;
};

export const renommerColonne = (t: Tableau, i: number, libelle: string): Tableau => {
    const c = copie(t);
    const ancien = c.colonnes[i].libelle;
    c.colonnes[i].libelle = libelle;
    for (const l of c.lignes) {
        const v = l.valeurs ?? {};
        if (ancien in v && ancien !== libelle) {
            v[libelle] = v[ancien];
            delete v[ancien];
        }
    }
    return c;
};

export const retirerColonne = (t: Tableau, i: number): Tableau => {
    const c = copie(t);
    const [ancienne] = c.colonnes.splice(i, 1);
    for (const l of c.lignes) delete (l.valeurs ?? {})[ancienne.libelle];
    return c;
};

export const deplacerColonne = (t: Tableau, i: number, vers: number): Tableau => {
    if (vers < 0 || vers >= t.colonnes.length || vers === i) return t;
    const c = copie(t);
    const [col] = c.colonnes.splice(i, 1);
    c.colonnes.splice(vers, 0, col);
    return c;
};

export const retirerLigne = (t: Tableau, i: number): Tableau => {
    const c = copie(t);
    c.lignes.splice(i, 1);
    return c;
};

export const changerType = (t: Tableau, i: number, type: TypeColonne): Tableau => {
    const c = copie(t);
    c.colonnes[i].type = type;
    return c;
};

/** « 1 234,50 € » devient « 1234.50 » ; un texte qui n'est pas un montant reste tel quel (rogné). */
export const nettoyerMontant = (brut: string): string => {
    const sans = brut.replace(/[\s  €$£]/g, "");
    if (!/^-?[\d.,]+$/.test(sans)) return brut.trim();
    const virgule = sans.lastIndexOf(",");
    const point = sans.lastIndexOf(".");
    const decimale = Math.max(virgule, point);
    if (decimale < 0) return sans;
    const entier = sans.slice(0, decimale).replace(/[.,]/g, "");
    return `${entier}.${sans.slice(decimale + 1)}`;
};

/**
 * Collage depuis Excel ou Google Sheets (cases séparées par des tabulations, lignes par des sauts de ligne), réparti
 * à partir de la case `(ligne, colonne)` ; des colonnes et des lignes sont ajoutées au besoin ; les montants sont nettoyés.
 */
export const coller = (t: Tableau, ligne: number, colonne: number, brut: string, posePar: PosePar = "mark"): Tableau => {
    const rangees = brut.replace(/\r\n?/g, "\n").replace(/\n+$/, "").split("\n").map((r) => r.split("\t"));
    let c = copie(t);
    rangees.forEach((cases, dy) => {
        cases.forEach((valeur, dx) => {
            while (c.colonnes.length <= colonne + dx) c = ajouterColonne(c, posePar);
            const col = c.colonnes[colonne + dx];
            c = poserCase(c, ligne + dy, col.libelle, col.type === "montant" ? nettoyerMontant(valeur) : valeur.trim());
        });
    });
    return c;
};

/** Découpe une rangée de CSV (guillemets doublés pour un guillemet, séparateur dans une case entre guillemets). */
const rangeeCsv = (texte: string, separateur: string): string[][] => {
    const rangees: string[][] = [];
    let rangee: string[] = [];
    let caseEnCours = "";
    let entre = false;
    for (let i = 0; i < texte.length; i++) {
        const car = texte[i];
        if (entre) {
            if (car === '"' && texte[i + 1] === '"') {
                caseEnCours += '"';
                i++;
            } else if (car === '"') entre = false;
            else caseEnCours += car;
        } else if (car === '"') entre = true;
        else if (car === separateur) {
            rangee.push(caseEnCours);
            caseEnCours = "";
        } else if (car === "\n" || car === "\r") {
            if (car === "\r" && texte[i + 1] === "\n") i++;
            rangee.push(caseEnCours);
            rangees.push(rangee);
            rangee = [];
            caseEnCours = "";
        } else caseEnCours += car;
    }
    if (caseEnCours !== "" || rangee.length > 0) {
        rangee.push(caseEnCours);
        rangees.push(rangee);
    }
    return rangees.filter((r) => r.some((x) => x.trim() !== ""));
};

/** Import CSV : la première ligne donne les colonnes, le séparateur (`;` ou `,`) se devine. */
export const importerCsv = (texte: string, posePar: PosePar = "mark"): Tableau => {
    const premiere = texte.split(/\r?\n/)[0] ?? "";
    const separateur = (premiere.match(/;/g)?.length ?? 0) >= (premiere.match(/,/g)?.length ?? 0) && premiere.includes(";") ? ";" : ",";
    const rangees = rangeeCsv(texte.replace(/^﻿/, ""), separateur);
    if (rangees.length === 0) return { colonnes: [], lignes: [] };
    const libelles: string[] = [];
    rangees[0].forEach((brut, i) => {
        let libelle = brut.trim() || `Colonne ${i + 1}`;
        while (libelles.includes(libelle)) libelle += "_";
        libelles.push(libelle);
    });
    return {
        colonnes: libelles.map((libelle, i) => ({ libelle, type: "texte", ordre: i + 1, pose_par: posePar }) as ColonneObjet),
        lignes: rangees.slice(1).map((r, i) => ({ ordre: i + 1, valeurs: Object.fromEntries(libelles.map((l, j) => [l, (r[j] ?? "").trim()])) }) as LigneObjet),
    };
};

/** Les colonnes que le client ne peut ni renommer, ni supprimer, ni changer de type (cadenas, E67). */
export const estVerrouillee = (c: ColonneObjet, verrouillerColonnesMark: boolean): boolean => verrouillerColonnesMark && c.pose_par === "mark";

/** Le résumé du champ « Sa valeur » : 3 premières lignes, « … et N autres lignes », compteur. */
export const resume = (t: Tableau): { apercu: string[][]; autres: number } => ({
    apercu: t.lignes.slice(0, 3).map((l) => t.colonnes.map((c) => l.valeurs?.[c.libelle] ?? "")),
    autres: Math.max(0, t.lignes.length - 3),
});

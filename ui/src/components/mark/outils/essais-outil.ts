/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 5.1) : les essais d'un outil HTTP, lus et écrits sur la
 * configuration de l'outil. Trois clés, dont les défauts sont le comportement d'avant (0 essai) ; une
 * valeur au défaut n'est pas écrite (la définition de l'outil est remplacée en entier à l'enregistrement).
 *
 * Le calcul du délai total reprend `delai_total_s` de `api/services/workflow/tools/custom_tool.py` :
 * (1 + essais) délais et les attentes entre eux. `essais-outil.test.ts` compare les bornes au schéma.
 */
export const ESSAIS_MAX = 2;
export const ATTENTE_MAX_S = 30;
export const ATTENTE_PAR_DEFAUT_S = 1;
export const DELAI_PAR_DEFAUT_MS = 5000;

export interface EssaisOutil {
    essais: number;
    attente_entre_essais_s: number;
    sans_risque_de_doublon: boolean;
}

export const ESSAIS_PAR_DEFAUT: EssaisOutil = {
    essais: 0,
    attente_entre_essais_s: ATTENTE_PAR_DEFAUT_S,
    sans_risque_de_doublon: false,
};

const borne = (valeur: number, min: number, max: number) => Math.max(min, Math.min(max, valeur));

/** Les essais de la configuration d'une définition d'outil (ce que le serveur lit, avec ses défauts). */
export const lireEssais = (config: Record<string, unknown> | null | undefined): EssaisOutil => {
    const essais = Number(config?.essais ?? 0);
    const attente = config?.attente_entre_essais_s;
    return {
        essais: Number.isFinite(essais) ? borne(Math.trunc(essais), 0, ESSAIS_MAX) : 0,
        attente_entre_essais_s:
            attente === undefined || attente === null || !Number.isFinite(Number(attente))
                ? ATTENTE_PAR_DEFAUT_S
                : borne(Number(attente), 0, ATTENTE_MAX_S),
        sans_risque_de_doublon: config?.sans_risque_de_doublon === true,
    };
};

/** Les clés à ajouter à la configuration de l'outil : seulement celles qui ne sont pas au défaut. */
export const chargeEssais = (e: EssaisOutil): Partial<EssaisOutil> => ({
    ...(e.essais > 0 ? { essais: e.essais } : {}),
    ...(e.essais > 0 && e.attente_entre_essais_s !== ATTENTE_PAR_DEFAUT_S
        ? { attente_entre_essais_s: e.attente_entre_essais_s }
        : {}),
    ...(e.sans_risque_de_doublon ? { sans_risque_de_doublon: true } : {}),
});

/** Le temps que l'outil peut durer, essais compris (secondes). */
export const delaiTotalS = (timeoutMs: number, e: EssaisOutil): number => {
    const delai = (Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : DELAI_PAR_DEFAUT_MS) / 1000;
    return delai * (1 + e.essais) + e.attente_entre_essais_s * e.essais;
};

/** Les quatre cas du tableau 5.1 : relancé ou non, selon les réglages. */
export const casRelances = (e: EssaisOutil) => ({
    pasPartie: e.essais > 0,
    delai: e.essais > 0 && e.sans_risque_de_doublon,
    erreur5xx: e.essais > 0 && e.sans_risque_de_doublon,
    refus4xx: false,
});

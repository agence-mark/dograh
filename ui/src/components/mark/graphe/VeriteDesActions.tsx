"use client";

/**
 * [.mark] Lot 5 de correctifs-apres-banc-commun (K7, V4, D-3) : la case « Vérité des actions » d'une étape.
 *
 * Lot 11 (F-2) : allumée par défaut sur une étape qui ÉCRIT (elle confie le travail au fond, ou porte un outil qui
 * remplit ou défait un champ de la fiche) ; ailleurs éteinte, réglable. Vide = ce défaut, ``true`` / ``false`` décident.
 * Le code vérifie alors trois choses : une réservation avec une date que la recherche n'a pas donnée est refusée ;
 * une réplique qui dit une date ou une action faite sans résultat d'outil est retenue, puis relancée une fois ;
 * une réservation identique déjà confirmée rend son résultat sans rappeler l'outil. La case écrit
 * ``verite_des_actions: false`` dans les données de l'étape quand on l'éteint (vide = allumée ; lu par
 * ``pipecat_engine.py`` et ``verite_des_actions.py``). La fenêtre d'une étape n'est jamais traduite (T3), mais ce
 * composant est le nôtre : ses textes sont dans les deux langues.
 */
import { Switch } from "@/components/ui/switch";

import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte } from "../langue/langue";

export const MARQUEUR_VERITE_DES_ACTIONS = "verite_des_actions";

/** The function name the model sees for a tool (same rule as ``custom_tool_function_name`` on the server). */
export const nomDeFonction = (nom: string): string =>
    nom
        .toLowerCase()
        .replace(/[^a-z0-9_]/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_+|_+$/g, "");

/**
 * Lot 11 (F-2): does the step write? It hands the work to the background, or it carries a tool that writes a record
 * field (booking) or undoes it (cancelling). Hand-overs, transfers and end tools do not count.
 */
export const etapeQuiEcrit = (
    toolUuids: string[],
    tools: Array<{ tool_uuid: string; name: string }>,
    outilsQuiEcrivent: string[],
    confieAuFond: boolean,
): boolean =>
    confieAuFond ||
    toolUuids.some((uuid) => {
        const outil = tools.find((t) => t.tool_uuid === uuid);
        return outil !== undefined && outilsQuiEcrivent.includes(nomDeFonction(outil.name));
    });

/**
 * fiabilite-de-la-conversation (decision of 26/10): does the agent act anywhere? One of its steps carries a tool, or
 * hands work to the background while the background work is on. The start step then shows the box too, even without
 * a tool of its own: it is where the agent first answers, and may claim an action it has not done.
 */
export const agentQuiAgit = (nodes: Array<{ data?: unknown }>, travailActif: boolean): boolean =>
    nodes.some((n) => {
        const d = (n.data ?? {}) as { tool_uuids?: unknown; travail_de_fond?: unknown };
        return (Array.isArray(d.tool_uuids) && d.tool_uuids.length > 0) || (travailActif && d.travail_de_fond === true);
    });

/** F-2: empty follows the step (on when it writes); a stored true or false decides. */
export const caseCochee = (valeur: unknown, ecrit: boolean): boolean =>
    valeur === true ? true : valeur === false ? false : ecrit;

/** F-2: what to store for a new state: nothing when it matches the step's default. */
export const valeurAEcrire = (coche: boolean, ecrit: boolean): boolean | undefined =>
    coche === ecrit ? undefined : coche;

const TEXTES = {
    libelle: { en: "Truth of actions", fr: "Vérité des actions" },
    aide: {
        en: "At this step, the code checks what the agent says and does: a booking with a date the search never gave is refused (search that day first), a reply that states a date, a wrong weekday or a done action with no tool result behind it is held back and the model is asked again once, and an identical booking already confirmed returns its known result without calling the tool again. A caller can always change day, correct a detail or cancel.",
        fr: "À cette étape, le code vérifie ce que l'agent dit et fait : une réservation avec une date que la recherche n'a pas donnée est refusée (on cherche d'abord ce jour), une réplique qui dit une date, un jour faux ou une action faite sans résultat d'outil derrière est retenue et le modèle est relancé une fois, et une réservation identique déjà confirmée rend son résultat sans rappeler l'outil. L'appelant peut toujours changer de jour, corriger une donnée ou annuler.",
    },
    aide2: {
        en: "A checked reply is sent once the model has finished writing it, not word by word. The words that say « done » are set per agent (Call data theme). Unchecked, the step behaves as before.",
        fr: "Une réplique contrôlée part quand le modèle a fini de l'écrire, et non mot à mot. Les mots qui disent « c'est fait » se règlent par agent (thème Données de l'appel). Décochée, l'étape se comporte comme avant.",
    },
} satisfies Record<string, Texte>;

const BORNES = {
    en: "Default: on when the step writes (it books, cancels or hands the work to the background), off otherwise",
    fr: "Par défaut : allumée quand l'étape écrit (elle réserve, annule ou confie le travail au fond), éteinte sinon",
} satisfies Texte;

export const VeriteDesActions = ({
    coche,
    onChange,
}: {
    coche: boolean;
    onChange: (coche: boolean) => void;
}) => (
    <ChampReglage
        cle={MARQUEUR_VERITE_DES_ACTIONS}
        idControle={MARQUEUR_VERITE_DES_ACTIONS}
        libelle={TEXTES.libelle}
        aides={[TEXTES.aide, TEXTES.aide2]}
        bornes={BORNES}
        disposition="ligne"
    >
        <Switch id={MARQUEUR_VERITE_DES_ACTIONS} checked={coche} onCheckedChange={onChange} />
    </ChampReglage>
);

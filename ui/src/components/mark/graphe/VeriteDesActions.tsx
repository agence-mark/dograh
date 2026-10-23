"use client";

/**
 * [.mark] Lot 5 de correctifs-apres-banc-commun (K7, V4, D-3) : la case « Vérité des actions » d'une étape.
 *
 * Allumée par défaut sur une étape qui offre un outil d'action (un outil de l'étape, ou le travail en arrière-plan).
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

const TEXTES = {
    libelle: { en: "Truth of actions", fr: "Vérité des actions" },
    aide: {
        en: "At this step, the code checks what the agent says and does: a booking with a date the search never gave is refused (search that day first), a reply that states a date or a done action with no tool result behind it is held back and the model is asked again once, and an identical booking already confirmed returns its known result without calling the tool again. A caller can always change day, correct a detail or cancel.",
        fr: "À cette étape, le code vérifie ce que l'agent dit et fait : une réservation avec une date que la recherche n'a pas donnée est refusée (on cherche d'abord ce jour), une réplique qui dit une date ou une action faite sans résultat d'outil derrière est retenue et le modèle est relancé une fois, et une réservation identique déjà confirmée rend son résultat sans rappeler l'outil. L'appelant peut toujours changer de jour, corriger une donnée ou annuler.",
    },
    aide2: {
        en: "A held-back reply is sent once the model has finished writing it, not word by word. Unchecked, the step behaves as before.",
        fr: "Une réplique contrôlée part quand le modèle a fini de l'écrire, et non mot à mot. Décochée, l'étape se comporte comme avant.",
    },
} satisfies Record<string, Texte>;

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
        disposition="ligne"
    >
        <Switch id={MARQUEUR_VERITE_DES_ACTIONS} checked={coche} onCheckedChange={onChange} />
    </ChampReglage>
);

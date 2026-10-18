"use client";

/**
 * [.mark] Chantier modules-et-cerveaux (lot 5, M3) : la case « Travail en arrière-plan » d'une étape.
 *
 * Le cerveau de fond se règle une fois pour l'agent (Briques : modèle, consigne, outils, délai) ; il ne
 * travaille qu'aux étapes cochées ici : l'outil qui lui confie une tâche n'est offert qu'à elles. Un travail
 * déjà lancé revient quelle que soit l'étape d'arrivée. La case écrit ``travail_de_fond`` dans les données
 * de l'étape (lu par ``pipecat_engine.py``). Visible seulement quand le travail en arrière-plan est allumé.
 * La fenêtre d'une étape n'est jamais traduite (T3), mais ce composant est le nôtre : ses textes sont dans
 * les deux langues.
 */
import { Switch } from "@/components/ui/switch";

import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte } from "../langue/langue";

export const MARQUEUR_TRAVAIL_DE_FOND = "travail_de_fond";

const TEXTES = {
    libelle: { en: "Background work", fr: "Travail en arrière-plan" },
    aide: {
        en: "At this step, the conversation model can hand a task to the background model (set in Bricks: model, instructions, tools, delay). Unchecked, the step does not offer it. A task already started still comes back, whatever the step.",
        fr: "À cette étape, le modèle de conversation peut confier une tâche au modèle de fond (réglé dans Briques : modèle, consigne, outils, délai). Décochée, l'étape ne le propose pas. Une tâche déjà lancée revient quand même, quelle que soit l'étape.",
    },
} satisfies Record<string, Texte>;

export const TravailDeFond = ({
    coche,
    onChange,
}: {
    coche: boolean;
    onChange: (coche: boolean) => void;
}) => (
    <ChampReglage
        cle={MARQUEUR_TRAVAIL_DE_FOND}
        idControle={MARQUEUR_TRAVAIL_DE_FOND}
        libelle={TEXTES.libelle}
        aides={[TEXTES.aide]}
        disposition="ligne"
    >
        <Switch id={MARQUEUR_TRAVAIL_DE_FOND} checked={coche} onCheckedChange={onChange} />
    </ChampReglage>
);

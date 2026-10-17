"use client";

/**
 * [.mark] Lot 2 d'orchestrateur-trois-cerveaux (D1) : la case « Étape de retour » d'une étape de l'accueil.
 *
 * Jumeau de ``RetourAuPrincipal`` (qui est du côté du collègue) : quand un collègue rend la main, le CODE
 * ramène l'appel sur l'étape marquée ici, au lieu de l'étape de départ, et lui donne une note écrite
 * depuis la fiche (le collègue, le motif, ce qui a été fait, ce qui reste, ce qui est connu). La case écrit
 * le marqueur ``etape_de_retour`` dans les données de l'étape (lu par ``services/groupe/passations.py``).
 *
 * N'existe que dans la fenêtre d'une étape de l'agent PRINCIPAL d'un groupe (un agent seul ou un
 * spécialisé ne la voit pas). Aucune porte n'y mène : le code la choisit. Tant que son prompt est
 * « À rédiger avec Evan. », elle n'est pas choisie et le retour se fait comme avant, sur l'étape de départ.
 * La fenêtre d'une étape n'est jamais traduite (T3), mais ce composant est le nôtre : ses textes sont dans
 * les deux langues.
 */
import { Switch } from "@/components/ui/switch";

import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte } from "../langue/langue";

export const MARQUEUR_ETAPE_DE_RETOUR = "etape_de_retour";

const TEXTES = {
    libelle: { en: "Return step", fr: "Étape de retour" },
    aide: {
        en: "When a specialised agent hands the call back, the call comes here instead of the start step. No exit leads to it: the code chooses it.",
        fr: "Quand un agent spécialisé rend la main, l'appel arrive ici et non sur l'étape de départ. Aucune sortie n'y mène : c'est le code qui la choisit.",
    },
    aide2: {
        en: "The code adds a note to the prompt of this step, written from the record: the colleague, why the call left, what was done, what is pending, what is already known. Write the step as the one that picks up: route the next request, hand it over, or close. Until the prompt is written, the call comes back to the start step as before.",
        fr: "Le code ajoute au prompt de cette étape une note écrite depuis la fiche : le collègue, le motif de départ, ce qui a été fait, ce qui reste, ce qui est déjà connu. Écrire cette étape comme celle qui reprend : orienter la demande suivante, la passer, ou conclure. Tant que le prompt n'est pas rédigé, l'appel revient sur l'étape de départ, comme avant.",
    },
} satisfies Record<string, Texte>;

export const EtapeDeRetour = ({
    coche,
    onChange,
}: {
    coche: boolean;
    onChange: (coche: boolean) => void;
}) => (
    <ChampReglage
        cle={MARQUEUR_ETAPE_DE_RETOUR}
        idControle={MARQUEUR_ETAPE_DE_RETOUR}
        libelle={TEXTES.libelle}
        aides={[TEXTES.aide, TEXTES.aide2]}
        disposition="ligne"
    >
        <Switch id={MARQUEUR_ETAPE_DE_RETOUR} checked={coche} onCheckedChange={onChange} />
    </ChampReglage>
);

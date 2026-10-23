"use client";

/**
 * [.mark] Lot 6 de correctifs-apres-banc-commun (K8, D-4) : le menu « Déclenchement de l'action » d'une étape.
 *
 * Quatre façons de faire partir l'outil d'action de l'étape (le travail en arrière-plan, ou l'unique action de
 * l'étape) ; le bon choix dépend du modèle. Libre est le comportement d'avant et reste le défaut. Le menu écrit
 * ``declenchement_de_l_action`` dans les données de l'étape (vide = libre) et, en « Automatique », la demande type
 * ``demande_type`` (lue par ``declenchement_de_l_action.py``). Visible sur une étape qui offre une action (même
 * condition que « Vérité des actions »). « Automatique » lance le travail en arrière-plan : il n'est proposé que
 * sur une étape qui le porte. La fenêtre d'une étape n'est jamais traduite (T3), mais ce composant est le nôtre :
 * ses textes sont dans les deux langues. ⛔ Aucun mot de métier.
 */
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte, useLangue } from "../langue/langue";

export const MARQUEUR_DECLENCHEMENT = "declenchement_de_l_action";
export const MARQUEUR_DEMANDE_TYPE = "demande_type";

export type PositionDeclenchement = "libre" | "relance" | "obligatoire" | "automatique";

export const POSITIONS: PositionDeclenchement[] = ["libre", "relance", "obligatoire", "automatique"];

/** Ce que le menu écrit : « libre » (le défaut) n'écrit rien. */
export const positionEcrite = (position: PositionDeclenchement): PositionDeclenchement | undefined =>
    position === "libre" ? undefined : position;

/** Ce que l'étape porte : une valeur inconnue vaut « libre ». */
export const positionLue = (valeur: unknown): PositionDeclenchement =>
    POSITIONS.includes(valeur as PositionDeclenchement) ? (valeur as PositionDeclenchement) : "libre";

const TEXTES = {
    libelle: { en: "Action trigger", fr: "Déclenchement de l'action" },
    aide: {
        en: "How this step's action starts. The right choice depends on the model: some announce the action without calling it. Free is the behaviour before this setting. In every other position, nothing starts while a task is running or once the action was done for the same request, a corrected detail reopens it, and the caller can always change day, correct or cancel.",
        fr: "Comment l'action de cette étape part. Le bon choix dépend du modèle : certains annoncent l'action sans l'appeler. Libre est le comportement d'avant ce réglage. Dans toutes les autres positions, rien ne part pendant un travail en cours ni une fois l'action faite pour la même demande, une donnée corrigée rouvre la garde, et l'appelant peut toujours changer de jour, corriger ou annuler.",
    },
    sansChamp: {
        en: "This step lists no field (Step field labels): Retry and Forced do nothing here. Only Automatic acts, once, when the step starts.",
        fr: "Cette étape ne liste aucun champ (Step field labels) : Relance et Obligatoire ne font rien ici. Seul Automatique agit, une fois, à l'entrée de l'étape.",
    },
    libre: { en: "Free (default)", fr: "Libre (par défaut)" },
    relance: { en: "Retry (recommended)", fr: "Relance (recommandée)" },
    obligatoire: { en: "Forced", fr: "Obligatoire" },
    automatique: { en: "Automatic", fr: "Automatique" },
    aideLibre: {
        en: "The model decides when to call the action, as before.",
        fr: "Le modèle décide quand appeler l'action, comme avant.",
    },
    aideRelance: {
        en: "When every field of the step is known, nothing is running and the reply has no question and no call, the reply is held back and the model is asked once more with the call forced. The reply then leaves once the model has finished writing it, not word by word. For most models.",
        fr: "Quand tous les champs de l'étape sont connus, qu'aucun travail n'est en cours et que la réplique n'a ni question ni appel, la réplique est retenue et le modèle est relancé une fois avec l'appel obligatoire. La réplique part alors quand le modèle a fini de l'écrire, et non mot à mot. Pour la plupart des modèles.",
    },
    aideObligatoire: {
        en: "Same conditions, but the turn is sent straight away with the call forced (for that turn only). For a model that often misses its calls. While a field is still missing and a note is being written, the turn waits for it, 1.5 seconds at most.",
        fr: "Mêmes conditions, mais le tour part directement avec l'appel obligatoire (pour ce tour seulement). Pour un modèle qui rate souvent ses appels. Tant qu'un champ manque et qu'une note s'écrit, le tour l'attend, 1,5 seconde au plus.",
    },
    aideAutomatique: {
        en: "As soon as the step's fields are known (or when the step starts, if it lists none), the code starts the background work itself with the request template below, then the model announces the result. The conversation can always resume afterwards.",
        fr: "Dès que les champs de l'étape sont connus (ou à l'entrée de l'étape si elle n'en liste aucun), le code lance lui-même le travail en arrière-plan avec la demande type ci-dessous, puis le modèle annonce le résultat. La conversation peut toujours reprendre ensuite.",
    },
    demandeLibelle: { en: "Request template", fr: "Demande type" },
    demandeAide: {
        en: "The request handed to the background work. Write {{field}} where the value of a record field goes; the record's values are added after it. Empty: a generic request.",
        fr: "La demande remise au travail en arrière-plan. Écrivez {{champ}} là où va la valeur d'un champ de la fiche ; les valeurs de la fiche sont ajoutées derrière. Vide : une demande générique.",
    },
} satisfies Record<string, Texte>;

export const DeclenchementDeLAction = ({
    position,
    demandeType,
    automatiquePossible,
    champsDeclares,
    onChange,
    onDemandeTypeChange,
}: {
    position: PositionDeclenchement;
    demandeType: string;
    /** L'étape porte le travail en arrière-plan : seul cas où le code peut lancer l'action lui-même. */
    automatiquePossible: boolean;
    /** L'étape liste des champs (Step field labels). */
    champsDeclares: boolean;
    onChange: (position: PositionDeclenchement) => void;
    onDemandeTypeChange: (texte: string) => void;
}) => {
    const { t } = useLangue();
    const proposees = POSITIONS.filter((p) => p !== "automatique" || automatiquePossible || position === "automatique");
    const aides: Record<PositionDeclenchement, Texte> = {
        libre: TEXTES.aideLibre,
        relance: TEXTES.aideRelance,
        obligatoire: TEXTES.aideObligatoire,
        automatique: TEXTES.aideAutomatique,
    };
    return (
        <>
            <ChampReglage
                cle={MARQUEUR_DECLENCHEMENT}
                idControle={MARQUEUR_DECLENCHEMENT}
                libelle={TEXTES.libelle}
                aides={[TEXTES.aide, aides[position]]}
                note={position !== "libre" && position !== "automatique" && !champsDeclares ? TEXTES.sansChamp : null}
            >
                <Select value={position} onValueChange={(v: string) => onChange(positionLue(v))}>
                    <SelectTrigger id={MARQUEUR_DECLENCHEMENT} className="w-64" aria-label={t(TEXTES.libelle)}>
                        <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                        {proposees.map((p) => (
                            <SelectItem key={p} value={p}>
                                {t(TEXTES[p])}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </ChampReglage>
            {position === "automatique" && (
                <ChampReglage
                    cle={MARQUEUR_DEMANDE_TYPE}
                    idControle={MARQUEUR_DEMANDE_TYPE}
                    libelle={TEXTES.demandeLibelle}
                    aides={[TEXTES.demandeAide]}
                >
                    <Textarea
                        id={MARQUEUR_DEMANDE_TYPE}
                        rows={3}
                        maxLength={4000}
                        value={demandeType}
                        onChange={(e) => onDemandeTypeChange(e.target.value)}
                    />
                </ChampReglage>
            )}
        </>
    );
};

import { BaseEdge, type Edge, EdgeLabelRenderer, type EdgeProps, getBezierPath, useReactFlow } from '@xyflow/react';
import { AlertCircle, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { useWorkflow, useWorkflowOptional } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import { useWorkflowStore } from "@/app/workflow/[workflowId]/stores/workflowStore";
import { useLangue } from "@/components/mark/langue/langue";
import { STYLE_TRANSITION, typeDeTransition } from "@/components/mark/graphe/type-de-transition";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { EdgeRecordCondition, FlowEdge, FlowEdgeData, FlowNode } from '../types';
type CustomEdge = Edge<{ value: number }, 'custom'>;


type RecordConditionMode = 'none' | 'complete' | 'field';

const recordModeOf = (condition?: EdgeRecordCondition): RecordConditionMode =>
    condition?.etape_complete ? 'complete' : condition?.champ ? 'field' : 'none';

interface EdgeDetailsDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    data?: FlowEdgeData;
    onSave: (value: FlowEdgeData) => void;
    onDelete: () => void;
}

// [.mark] K2 : la fenêtre d'une liaison, en français et à la forme des fenêtres à champs de la maquette (« Condition de passage »).
const FICHE = { none: 'Aucune', complete: 'Étape complète', field: 'Un champ a une valeur' } as const;
const PHRASE = { none: 'Aucune', text: 'Texte', audio: 'Enregistrement' } as const;

const EdgeDetailsDialog = ({ open, onOpenChange, data, onSave, onDelete }: EdgeDetailsDialogProps) => {
    const { t } = useLangue();
    const readOnly = useWorkflowOptional()?.readOnly ?? false;
    const { recordings } = useWorkflow();
    const enregistrements = recordings ?? [];
    const phraseDepart = data?.transition_speech_type === 'audio' && data.transition_speech_recording_id ? 'audio' : data?.transition_speech ? 'text' : 'none';
    const libelleEnregistrement = (r: { recording_id: string; transcript?: string | null }) => r.transcript || r.recording_id;
    const choixEnregistrement = enregistrements.map(libelleEnregistrement);
    const enregistrementDepart = enregistrements.find((r) => r.recording_id === data?.transition_speech_recording_id);

    return (
        <FenetreChamps centree={false}
            ouverte={open}
            fermer={() => onOpenChange(false)}
            titre={t({ en: "Transition condition", fr: "Condition de passage" })}
            info={t({ en: "What decides the move from one step to the next: the label, the condition the model reads, the condition on the record and the sentence said during the transition.", fr: "Ce qui décide du passage d'une étape à l'autre : le libellé, la condition que lit le modèle, la condition sur la fiche et la phrase dite pendant la transition." })}
            lecture={readOnly}
            valider={readOnly ? t({ en: 'Close', fr: 'Fermer' }) : t({ en: 'Save', fr: 'Enregistrer' })}
            pied={
                readOnly ? undefined : (
                    <Button
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={() => {
                            onDelete();
                            onOpenChange(false);
                        }}
                    >
                        <Trash2 className="size-4" /> {t({ en: 'Delete the link', fr: 'Supprimer la liaison' })}
                    </Button>
                )
            }
            corps={
                data?.invalid && data.validationMessage ? (
                    <div className="flex items-center gap-2 text-sm text-destructive">
                        <AlertCircle className="size-4" />
                        <span>{data.validationMessage}</span>
                    </div>
                ) : undefined
            }
            sections={[
                {
                    champs: [
                        { id: 'label', t: 'texte', l: t({ en: 'Label', fr: 'Libellé' }), v: data?.label ?? '' },
                        {
                            id: 'condition',
                            t: 'zone',
                            l: t({ en: 'Condition (for the model)', fr: 'Condition (pour le modèle)' }),
                            v: data?.condition ?? '',
                            info: "Décrit quand cette porte doit s'ouvrir. Le modèle la lit pour choisir la sortie.",
                        },
                        {
                            id: 'fiche',
                            t: 'choix',
                            l: t({ en: 'Condition on the record', fr: 'Condition sur la fiche' }),
                            o: Object.values(FICHE),
                            v: FICHE[recordModeOf(data?.condition_sur_la_fiche)],
                            info: "Le code n'ouvre la porte que si la condition est vraie. Les sorties se lisent dans l'ordre du canevas, la première vraie l'emporte.",
                        },
                        { id: 'champ', t: 'texte', l: t({ en: 'Field', fr: 'Champ' }), v: data?.condition_sur_la_fiche?.champ ?? '', si: ['fiche', [FICHE.field]] },
                        {
                            id: 'vaut',
                            t: 'texte',
                            l: t({ en: 'Value', fr: 'Valeur' }),
                            v: data?.condition_sur_la_fiche?.vaut ?? '',
                            si: ['fiche', [FICHE.field]],
                            info: "Vide : n'importe quelle valeur. « refusé » pour un refus.",
                        },
                        { id: 'phrase', t: 'choix', l: t({ en: 'Transition sentence', fr: 'Phrase de transition' }), o: Object.values(PHRASE), v: PHRASE[phraseDepart] },
                        {
                            id: 'texte',
                            t: 'zone',
                            l: t({ en: 'Sentence text', fr: 'Texte de la phrase' }),
                            v: data?.transition_speech ?? '',
                            si: ['phrase', [PHRASE.text]],
                            info: "Dite juste avant de passer à l'étape suivante. Elle n'entre pas dans le contexte de la conversation : une phrase de remplissage qui réduit l'attente.",
                        },
                        ...(choixEnregistrement.length > 0
                            ? [
                                  {
                                      id: 'enregistrement',
                                      t: 'choix' as const,
                                      l: t({ en: 'Recording', fr: 'Enregistrement' }),
                                      o: choixEnregistrement,
                                      v: enregistrementDepart ? libelleEnregistrement(enregistrementDepart) : choixEnregistrement[0],
                                      si: ['phrase', [PHRASE.audio]] as [string, string[]],
                                  },
                              ]
                            : []),
                    ],
                },
            ]}
            onValider={(v) => {
                const fiche = v.fiche === FICHE.complete ? 'complete' : v.fiche === FICHE.field ? 'field' : 'none';
                const champ = String(v.champ ?? '').trim();
                const recordCondition: EdgeRecordCondition | undefined =
                    fiche === 'complete'
                        ? { etape_complete: true }
                        : fiche === 'field' && champ
                          ? { champ, vaut: String(v.vaut ?? '').trim() || undefined }
                          : undefined;
                const type = v.phrase === PHRASE.audio ? 'audio' : 'text';
                const enregistrement = enregistrements.find((r) => libelleEnregistrement(r) === v.enregistrement)?.recording_id;
                onSave({
                    condition: String(v.condition ?? ''),
                    label: String(v.label ?? ''),
                    condition_sur_la_fiche: recordCondition,
                    transition_speech: v.phrase === PHRASE.text ? String(v.texte ?? '') || undefined : undefined,
                    transition_speech_type: type,
                    transition_speech_recording_id: v.phrase === PHRASE.audio ? enregistrement : undefined,
                });
            }}
        />
    );
};

interface CustomEdgeProps extends EdgeProps {
    data: FlowEdgeData;
}

export default function CustomEdge(props: CustomEdgeProps) {
    const { t } = useLangue();
    const { id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, style, selected, markerEnd } = props;

    const { getEdges, setNodes } = useReactFlow<FlowNode, FlowEdge>();
    const { saveWorkflow } = useWorkflow();
    const updateEdge = useWorkflowStore((state) => state.updateEdge);
    const deleteEdge = useWorkflowStore((state) => state.deleteEdge);
    const [open, setOpen] = useState(false);
    const [isHovered, setIsHovered] = useState(false);

    const parallel = getEdges().filter(
        (e) =>
            (e.source === source && e.target === target) ||
            (e.source === target && e.target === source)
    );

    // 2) if there are two, sort by id and pick an index
    let offsetX = 0;
    let offsetY = 0;
    if (parallel.length > 1) {
        const sorted = parallel.slice().sort((a, b) => a.id.localeCompare(b.id));
        const idx = sorted.findIndex((e) => e.id === id);

        // first edge (idx 0) moves right & down;
        // second edge (idx 1) moves left & up
        if (idx === 0) {
            offsetX = 100;
            offsetY = 0;
        } else {
            offsetX = 0;
            offsetY = -50;
        }
    }

    // Check if this is a self-loop (source and target are the same node)
    const isSelfLoop = source === target;

    // 3) draw the edge path + get label coords
    // Use custom arc path for self-loops, smoothstep for regular edges
    let edgePath: string;
    let labelX: number;
    let labelY: number;

    if (isSelfLoop) {
        // Create a loop arc that goes out and around the node
        const loopRadius = 50;
        const loopOffsetX = 80;
        // Arc path: start from source, curve out and back to target
        edgePath = `M ${sourceX} ${sourceY}
                    C ${sourceX + loopOffsetX} ${sourceY - loopRadius},
                      ${targetX + loopOffsetX} ${targetY + loopRadius},
                      ${targetX} ${targetY}`;
        labelX = sourceX + loopOffsetX;
        labelY = sourceY;
    } else {
        // [.mark] E36 : liaisons courbes (colonne centrée), la condition au milieu ; seul l'habillage change.
        const [path, lx, ly] = getBezierPath({
            sourceX,
            sourceY,
            sourcePosition,
            targetX,
            targetY,
            targetPosition,
            curvature: 0.35,
        });
        edgePath = path;
        labelX = lx;
        labelY = ly;
    }

    // Update connected nodes when edge is selected or hovered
    useEffect(() => {
        setNodes((nodes) => {
            return nodes.map((node) => {
                if (node.id === source || node.id === target) {
                    // Update both properties based on edge state
                    const shouldSelectThroughEdge = selected || false;
                    const shouldHoverThroughEdge = isHovered || false;

                    // Only update if state actually changed
                    if (
                        node.data.selected_through_edge !== shouldSelectThroughEdge ||
                        node.data.hovered_through_edge !== shouldHoverThroughEdge
                    ) {
                        return {
                            ...node,
                            data: {
                                ...node.data,
                                selected_through_edge: shouldSelectThroughEdge,
                                hovered_through_edge: shouldHoverThroughEdge
                            }
                        };
                    }
                }
                return node;
            });
        });
    }, [selected, isHovered, source, target, setNodes]);

    const handleSaveEdgeData = useCallback(async (updatedData: FlowEdgeData) => {
        // Use the workflow store's updateEdge method to properly track history
        updateEdge(id, { data: updatedData });
        await saveWorkflow();
    }, [id, updateEdge, saveWorkflow]);

    // [.mark] Partie 3, sous-lot 20 : une couleur par type de transition (le modèle décide, étape de la fiche complète, champ de la fiche).
    const typeTransition = typeDeTransition(data);
    const style_ = STYLE_TRANSITION[typeTransition];

    const handleDeleteEdge = useCallback(() => {
        deleteEdge(id);
    }, [id, deleteEdge]);

    return (
        <>
            <g onMouseEnter={() => setIsHovered(true)} onMouseLeave={() => setIsHovered(false)} onDoubleClick={() => setOpen(true)}>
                <BaseEdge
                    id={id}
                    path={edgePath}
                    markerEnd={markerEnd}
                    style={{
                        ...style,
                        stroke: data?.invalid ? 'var(--destructive)' : selected || isHovered ? 'var(--liaison-survol)' : style_.trait,
                        strokeWidth: 1.5,
                        transition: 'stroke 0.2s ease',
                    }}
                    interactionWidth={20}
                />
            </g>
            {/* [.mark] K2 : la condition en pastille sobre de la maquette ; un clic l'ouvre. */}
            <EdgeLabelRenderer>
                <div
                    style={{
                        position: 'absolute',
                        pointerEvents: 'all',
                        transformOrigin: 'center',
                        transform: `translate(-50%, -50%) translate(${labelX + offsetX}px, ${labelY + offsetY}px)`,
                        zIndex: 1000,
                    }}
                    className="nodrag nopan"
                    onMouseEnter={() => setIsHovered(true)}
                    onMouseLeave={() => setIsHovered(false)}
                >
                    <button
                        type="button"
                        onClick={() => setOpen(true)}
                        data-type-transition={typeTransition}
                        title={t(style_.nom)}
                        className={cn(
                            'max-w-[220px] cursor-pointer truncate rounded-md border px-2 py-0.5 text-[11px] hover:font-semibold hover:text-foreground',
                            data?.invalid ? 'border-destructive bg-background text-destructive' : style_.pastille,
                        )}
                    >
                        {data?.label || data?.condition || t({ en: 'No condition', fr: 'Sans condition' })}
                    </button>
                </div>
            </EdgeLabelRenderer>
            <EdgeDetailsDialog open={open} onOpenChange={setOpen} data={data} onSave={handleSaveEdgeData} onDelete={handleDeleteEdge} />
        </>
    );
}

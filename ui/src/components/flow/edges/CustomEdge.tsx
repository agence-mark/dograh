import { BaseEdge, type Edge, EdgeLabelRenderer, type EdgeProps, getBezierPath, useReactFlow } from '@xyflow/react';
import { Braces, Sparkles } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import { useWorkflow, useWorkflowOptional } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import { useWorkflowStore } from "@/app/workflow/[workflowId]/stores/workflowStore";
import { quiDecide, type QuiDecide } from "@/components/mark/graphe/conditions-de-porte";
import { FenetreTransition } from "@/components/mark/graphe/FenetreTransition";
import { STYLE_TRANSITION, typeDeTransition } from "@/components/mark/graphe/type-de-transition";
import { useLangue } from "@/components/mark/langue/langue";
import { cn } from "@/lib/utils";

import { FlowEdge, FlowEdgeData, FlowNode } from '../types';
type CustomEdge = Edge<{ value: number }, 'custom'>;

interface CustomEdgeProps extends EdgeProps {
    data: FlowEdgeData;
}

export default function CustomEdge(props: CustomEdgeProps) {
    const { t } = useLangue();
    const { id, source, target, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, style, selected, markerEnd } = props;

    const { getEdges, setNodes } = useReactFlow<FlowNode, FlowEdge>();
    const { saveWorkflow, recordings } = useWorkflow();
    const readOnly = useWorkflowOptional()?.readOnly ?? false;
    const updateEdge = useWorkflowStore((state) => state.updateEdge);
    const updateNode = useWorkflowStore((state) => state.updateNode);
    const deleteEdge = useWorkflowStore((state) => state.deleteEdge);
    // [.mark] Sous-lot 21 : l'étape d'où part la liaison (qui y décide), lue dans le magasin du graphe.
    const noeudSource = useWorkflowStore((state) => state.nodes.find((n) => n.id === source));
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

    const handleSaveEdgeData = useCallback(async (updatedData: FlowEdgeData, quiPose?: QuiDecide) => {
        // [.mark] Sous-lot 21 : la correction « faire décider la fiche » se pose sur l'étape source, avec la liaison.
        if (quiPose && noeudSource) {
            updateNode(noeudSource.id, { data: { ...noeudSource.data, qui_decide_du_passage: quiPose } });
        }
        // Use the workflow store's updateEdge method to properly track history
        updateEdge(id, { data: updatedData });
        await saveWorkflow();
    }, [id, updateEdge, updateNode, noeudSource, saveWorkflow]);

    // [.mark] Partie 3, sous-lot 20 : une couleur par type de transition ; sous-lot 21 : règles, toujours, sinon, et l'indicateur
    // « le code vérifie » ou « l'IA juge ». Sur une étape où le modèle décide, une condition du code est sans effet : l'icône le dit.
    const typeTransition = typeDeTransition(data);
    const style_ = STYLE_TRANSITION[typeTransition];
    const qui = quiDecide(noeudSource?.data?.qui_decide_du_passage);
    const inerte = style_.decide !== 'modele' && qui === 'agent';
    const decide = inerte ? 'modele' : style_.decide;
    const Icone = decide === 'code' ? Braces : decide === 'modele' ? Sparkles : null;
    const titre = inerte ? `${t(style_.nom)} · ${t({ en: 'no effect: the model decides on this step', fr: "sans effet : le modèle décide sur cette étape" })}` : t(style_.nom);
    const autreSinon = getEdges().some((e) => e.source === source && e.id !== id && !!e.data?.condition_sur_la_fiche?.sinon);

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
                        strokeDasharray: style_.pointille ? '4 4' : undefined,
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
                        data-decide={decide}
                        {...(inerte ? { 'data-sans-effet': '' } : {})}
                        title={titre}
                        aria-label={`${data?.label || data?.condition || t({ en: 'No condition', fr: 'Sans condition' })} : ${titre}`}
                        className={cn(
                            'inline-flex max-w-[220px] cursor-pointer items-center gap-1 truncate rounded-md border px-2 py-0.5 text-[11px] hover:font-semibold hover:text-foreground',
                            data?.invalid ? 'border-destructive bg-background text-destructive' : style_.pastille,
                        )}
                    >
                        {Icone && <Icone className="size-3 shrink-0" aria-hidden />}
                        <span className="truncate">{data?.label || data?.condition || t({ en: 'No condition', fr: 'Sans condition' })}</span>
                    </button>
                </div>
            </EdgeLabelRenderer>
            <FenetreTransition
                ouverte={open}
                fermer={() => setOpen(false)}
                data={data}
                etape={{ nom: String(noeudSource?.data?.name ?? ''), qui }}
                autreSinon={autreSinon}
                enregistrements={recordings ?? []}
                lecture={readOnly}
                onSave={handleSaveEdgeData}
                onDelete={handleDeleteEdge}
            />
        </>
    );
}

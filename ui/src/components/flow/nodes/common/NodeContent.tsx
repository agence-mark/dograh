import { Position } from "@xyflow/react";
import { ReactNode } from "react";

import { BaseHandle } from "@/components/flow/nodes/BaseHandle";
import { BaseNode } from "@/components/flow/nodes/BaseNode";

interface NodeContentProps {
    selected: boolean;
    invalid?: boolean;
    selected_through_edge?: boolean;
    hovered_through_edge?: boolean;
    runtimeActive?: boolean;
    title: string;
    icon: ReactNode;
    /** Le type de l'étape, en petit au-dessus du titre (« Début », « Étape », « Fin »…). */
    badgeLabel?: string;
    hasSourceHandle?: boolean;
    hasTargetHandle?: boolean;
    children?: ReactNode;
    className?: string;
    onDoubleClick?: () => void;
}

/**
 * [.mark] K2 : la carte d'un nœud, reprise de la maquette (`canevas.tsx`) : le type en petit avec son icône, le titre, deux
 * lignes de texte, un petit rond en haut et en bas pour les liaisons. Le contenu (le texte de l'étape) vient de l'appelant.
 */
export const NodeContent = ({
    selected,
    invalid,
    selected_through_edge,
    hovered_through_edge,
    runtimeActive,
    title,
    icon,
    badgeLabel,
    hasSourceHandle = false,
    hasTargetHandle = false,
    children,
    className = "",
    onDoubleClick,
}: NodeContentProps) => (
    <BaseNode
        selected={selected}
        invalid={invalid}
        selected_through_edge={selected_through_edge}
        hovered_through_edge={hovered_through_edge}
        runtimeActive={runtimeActive}
        className={className}
        onDoubleClick={onDoubleClick}
    >
        {hasTargetHandle && <BaseHandle type="target" position={Position.Top} />}
        <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            <span className="[&>*]:size-3">{icon}</span>
            {badgeLabel}
        </p>
        <p className="mt-0.5 truncate text-sm font-medium">{title}</p>
        {children}
        {hasSourceHandle && <BaseHandle type="source" position={Position.Bottom} />}
    </BaseNode>
);

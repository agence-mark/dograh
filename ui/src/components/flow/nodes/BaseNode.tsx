import { forwardRef, HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const BaseNode = forwardRef<
    HTMLDivElement,
    HTMLAttributes<HTMLDivElement> & {
        selected?: boolean;
        invalid?: boolean;
        selected_through_edge?: boolean;
        hovered_through_edge?: boolean;
        runtimeActive?: boolean;
    }
>(({ children, className, selected, invalid, selected_through_edge, hovered_through_edge, runtimeActive, ...props }, ref) => (
    <div
        ref={ref}
        className={cn(
            // Base styling - larger with max width, uses semantic colors
            "relative rounded-lg border bg-card text-card-foreground min-w-[320px] max-w-[400px] min-h-[120px]",
            // Border styling
            "border-border",
            className,
            // Selected state - prominent halo effect
            selected ? "border-foreground" : "",
            // Invalid state
            invalid ? "border-destructive" : "",
            // Hovered through edge takes precedence over selected through edge
            hovered_through_edge ? "border-foreground/60" : "",
            !hovered_through_edge && selected_through_edge ? "border-foreground/40" : "",
            runtimeActive ? "ring-2 ring-ring" : "",
            !selected_through_edge && !hovered_through_edge && "hover:border-(--border-strong)",
        )}
        tabIndex={0}
        {...props}
    >
        {children}
    </div>
));

BaseNode.displayName = "BaseNode";

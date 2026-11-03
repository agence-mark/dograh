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
            "relative w-[250px] cursor-pointer rounded-xl border bg-card px-3.5 py-3 text-card-foreground shadow-[0_1px_2px_rgba(15,15,16,0.05)]",
            // Border styling
            "border-black/10",
            className,
            // Selected state - prominent halo effect
            selected ? "border-(--acc) shadow-[0_0_0_3px_var(--acc-soft)]" : "",
            // Invalid state
            invalid ? "border-destructive" : "",
            // Hovered through edge takes precedence over selected through edge
            hovered_through_edge ? "border-(--acc)/70" : "",
            !hovered_through_edge && selected_through_edge ? "border-(--acc)/45" : "",
            runtimeActive ? "ring-2 ring-foreground/60" : "",
            !selected_through_edge && !hovered_through_edge && "hover:border-black/25",
        )}
        tabIndex={0}
        {...props}
    >
        {children}
    </div>
));

BaseNode.displayName = "BaseNode";

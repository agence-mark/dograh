import { Handle, HandleProps } from "@xyflow/react";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";

export type BaseHandleProps = HandleProps;

export const BaseHandle = forwardRef<HTMLDivElement, BaseHandleProps>(
    ({ className, children, type, ...props }, ref) => {
        return (
            <Handle
                ref={ref}
                type={type}
                {...props}
                className={cn("!size-2 !rounded-full !border !border-solid !border-border !bg-background transition-all hover:!border-primary", className)}
                style={{ ...props.style }}
            >
                {children}
            </Handle>
        );
    },
);

BaseHandle.displayName = "BaseHandle";

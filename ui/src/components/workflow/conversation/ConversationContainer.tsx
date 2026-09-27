"use client";

import { MessageSquare, Mic, MicOff } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import type { ConversationStatus } from "./types";

interface ConversationContainerProps {
    title: string;
    status: ConversationStatus;
    children: ReactNode;
    messageCount?: number;
}

const STATUS_CONFIG = {
    ready: {
        icon: MicOff,
        label: "Ready",
        className: "border border-border bg-background text-foreground before:bg-(--signal-idle) before:size-1.5 before:shrink-0 before:rounded-full before:content-['']",
    },
    live: {
        icon: Mic,
        label: "Live",
        className: "border border-border bg-background text-foreground before:bg-foreground before:size-1.5 before:shrink-0 before:rounded-full before:content-['']",
    },
    ended: {
        icon: MicOff,
        label: "Ended",
        className: "border border-border bg-background text-foreground before:bg-(--signal-idle) before:size-1.5 before:shrink-0 before:rounded-full before:content-['']",
    },
} satisfies Record<ConversationStatus, { icon: typeof Mic; label: string; className: string }>;

export function ConversationContainer({
    title,
    status,
    children,
    messageCount,
}: ConversationContainerProps) {
    const statusConfig = STATUS_CONFIG[status];
    const StatusIcon = statusConfig.icon;

    return (
        <div className="flex h-full min-h-0 w-full flex-col bg-background">
            <div className="shrink-0 border-b border-border px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                        <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="truncate whitespace-nowrap text-sm font-medium">{title}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                        {messageCount !== undefined && messageCount > 0 ? (
                            <span className="text-xs text-muted-foreground">{messageCount} messages</span>
                        ) : null}
                        <div
                            className={cn(
                                "flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs",
                                statusConfig.className,
                            )}
                        >
                            <StatusIcon className="h-3 w-3" />
                            <span>{statusConfig.label}</span>
                        </div>
                    </div>
                </div>
            </div>
            {children}
        </div>
    );
}

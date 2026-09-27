"use client";

import { AlertTriangle, ExternalLink, MicOff } from "lucide-react";

import { cn } from "@/lib/utils";

interface NoticeCardProps {
    tone: "warning" | "error";
    title: string;
    text: string;
    linkHref?: string;
    linkLabel?: string;
}

export function NoticeCard({
    tone,
    title,
    text,
    linkHref,
    linkLabel,
}: NoticeCardProps) {
    const isWarning = tone === "warning";
    const Icon = isWarning ? MicOff : AlertTriangle;

    return (
        <div
            className={cn(
                "flex items-start gap-2 rounded-lg px-3 py-2",
                isWarning
                    ? "bg-muted"
                    : "bg-muted",
            )}
        >
            <Icon
                className={cn(
                    "mt-0.5 h-4 w-4 shrink-0",
                    isWarning ? "text-(--signal-warn)" : "text-destructive",
                )}
            />
            <div className="min-w-0 flex-1">
                <div
                    className={cn(
                        "text-xs font-medium",
                        isWarning ? "text-foreground" : "text-destructive",
                    )}
                >
                    {title}
                </div>
                <div
                    className={cn(
                        "mt-0.5 break-words text-sm",
                        isWarning ? "text-muted-foreground" : "text-muted-foreground",
                    )}
                >
                    {text}
                </div>
                {linkHref && linkLabel ? (
                    <a
                        href={linkHref}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={cn(
                            "mt-1 inline-flex items-center gap-1 text-xs hover:underline",
                            isWarning ? "text-foreground" : "text-foreground",
                        )}
                    >
                        {linkLabel} <ExternalLink className="h-3 w-3" />
                    </a>
                ) : null}
            </div>
        </div>
    );
}

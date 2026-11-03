"use client";

import { AlertCircle, MessageSquareText } from "lucide-react";
import type { ReactNode } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function DisabledNotice({ reason }: { reason: string }) {
    return (
        <div className="rounded-lg bg-muted px-3 py-2.5 text-sm text-foreground">
            <div className="flex items-start gap-3">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="space-y-0.5">
                    <p className="font-medium">Testing is paused</p>
                    <p className="text-foreground">{reason}</p>
                </div>
            </div>
        </div>
    );
}

export function EmptyState({
    icon,
    title,
    description,
    action,
}: {
    icon: ReactNode;
    title: string;
    description?: string;
    action?: ReactNode;
}) {
    // [.mark] K2 : l'état au repos de la maquette (`panneau-essai.tsx`) : l'icône, une ligne, le bouton, au centre.
    return (
        <div className="space-y-3 py-10 text-center">
            <div className="mx-auto flex size-8 items-center justify-center text-muted-foreground [&>*]:size-8">{icon}</div>
            <p className="text-sm">{title}</p>
            {description ? <p className="text-sm leading-6 text-muted-foreground">{description}</p> : null}
            {action ? <div>{action}</div> : null}
        </div>
    );
}

export function ChatModeToggle({
    value,
    onChange,
}: {
    value: "manual" | "simulated";
    onChange: (next: "manual" | "simulated") => void;
}) {
    const { t } = useLangue();
    const options: Array<{ id: "manual" | "simulated"; label: string }> = [
        { id: "manual", label: t({ en: "Manual", fr: "Manuel" }) },
        { id: "simulated", label: t({ en: "Simulated", fr: "Simulé" }) },
    ];

    return (
        <div className="inline-flex rounded-md border p-0.5 text-xs">
            {options.map((option) => {
                const active = option.id === value;
                return (
                    <button
                        key={option.id}
                        type="button"
                        onClick={() => onChange(option.id)}
                        className={cn(
                            "cursor-pointer rounded px-2 py-0.5",
                            active ? "bg-foreground text-background" : "text-muted-foreground hover:font-medium hover:text-foreground",
                        )}
                    >
                        {option.label}
                    </button>
                );
            })}
        </div>
    );
}

export function TypingIndicator() {
    return (
        <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-muted px-3.5 py-3">
                <div className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.3s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
                </div>
            </div>
        </div>
    );
}

export function ManualChatEmptyState({
    disabled,
    ready,
    onStart,
}: {
    disabled: boolean;
    ready: boolean;
    onStart: () => void;
}) {
    return (
        <EmptyState
            icon={<MessageSquareText className="h-7 w-7" />}
            title="Chat with this agent"
            description="Test the agent over a text conversation. Send messages and see how it responds, with tool calls, transitions, and rewind support."
            action={
                <Button onClick={onStart} disabled={disabled || !ready}>
                    <MessageSquareText className="h-4 w-4" />
                    Start Test
                </Button>
            }
        />
    );
}

"use client";

import { formatDistanceToNow } from "date-fns";
import { FileDiff, FileText, LoaderCircle, X } from "lucide-react";
import { useEffect } from "react";

import type { WorkflowVersionResponse } from "@/client/types.gen";
import { Button } from "@/components/ui/button";

interface VersionHistoryPanelProps {
    isOpen: boolean;
    onClose: () => void;
    versions: WorkflowVersionResponse[];
    loading: boolean;
    activeVersionId: number | null;
    onSelectVersion: (version: WorkflowVersionResponse) => void;
    onCompareVersion: (version: WorkflowVersionResponse) => void;
    comparingVersionId: number | null;
    hasMore: boolean;
    loadingMore: boolean;
    onLoadMore: () => void;
}

const statusLabel: Record<string, string> = {
    draft: "Draft",
    published: "Published",
    archived: "Archived",
};

const statusColor: Record<string, string> = {
    draft: "border-border bg-background text-foreground before:bg-(--signal-warn) before:mr-1.5 before:inline-block before:size-1.5 before:rounded-full before:align-middle before:content-['']",
    published: "border-border bg-background text-foreground before:bg-(--signal-ok) before:mr-1.5 before:inline-block before:size-1.5 before:rounded-full before:align-middle before:content-['']",
    archived: "border-border bg-background text-muted-foreground before:bg-(--signal-idle) before:mr-1.5 before:inline-block before:size-1.5 before:rounded-full before:align-middle before:content-['']",
};

export const VersionHistoryPanel = ({
    isOpen,
    onClose,
    versions,
    loading,
    activeVersionId,
    onSelectVersion,
    onCompareVersion,
    comparingVersionId,
    hasMore,
    loadingMore,
    onLoadMore,
}: VersionHistoryPanelProps) => {
    useEffect(() => {
        const handleKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape" && isOpen) {
                onClose();
            }
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [isOpen, onClose]);

    return (
        <div
            className={`fixed z-51 right-0 top-0 h-full w-80 bg-card border-l border-border shadow-lg transform transition-transform duration-300 ease-in-out ${
                isOpen ? "translate-x-0" : "translate-x-full"
            }`}
        >
            <div className="p-4 h-full overflow-y-auto">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-lg font-semibold text-foreground">
                        Version History
                    </h2>
                    <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Close version history"
                        onClick={onClose}
                        className="text-muted-foreground hover:text-foreground hover:bg-accent"
                    >
                        <X className="w-5 h-5" />
                    </Button>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <LoaderCircle className="w-6 h-6 text-muted-foreground animate-spin" />
                    </div>
                ) : versions.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">
                        No versions found.
                    </p>
                ) : (
                    <div className="space-y-2">
                        {versions.map((version, index) => {
                            const isActive = version.id === activeVersionId;
                            const date = version.published_at || version.created_at;
                            const previousVersion = versions[index + 1];
                            const canCompare = Boolean(previousVersion) || hasMore;
                            const compareLabel = previousVersion
                                ? `Compare v${version.version_number} with v${previousVersion.version_number}`
                                : `Compare v${version.version_number} with its previous version`;
                            return (
                                <div
                                    key={version.id}
                                    className={`flex w-full overflow-hidden rounded-lg border transition-colors ${
                                        isActive
                                            ? "border-border bg-muted"
                                            : "border-border bg-muted"
                                    }`}
                                >
                                    <button
                                        type="button"
                                        onClick={() => onSelectVersion(version)}
                                        className="min-w-0 flex-1 cursor-pointer p-3 text-left transition-colors hover:bg-accent"
                                    >
                                        <div className="mb-1.5 flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <FileText className="h-4 w-4 text-muted-foreground" />
                                                <span className="text-sm font-medium text-foreground">
                                                    v{version.version_number}
                                                </span>
                                            </div>
                                            {version.status !== "archived" && (
                                                <span
                                                    className={`rounded-full border px-2 py-0.5 text-xs ${
                                                        statusColor[version.status] ?? ""
                                                    }`}
                                                >
                                                    {statusLabel[version.status] ?? version.status}
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-xs text-muted-foreground">
                                            {formatDistanceToNow(new Date(date), {
                                                addSuffix: true,
                                            })}
                                        </p>
                                    </button>

                                    {canCompare && (
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="icon"
                                            aria-label={compareLabel}
                                            disabled={comparingVersionId !== null}
                                            onClick={() => onCompareVersion(version)}
                                            className="mr-2 h-7 w-7 shrink-0 self-center rounded-md border border-border text-muted-foreground hover:bg-accent hover:text-foreground"
                                        >
                                            {comparingVersionId === version.id ? (
                                                <LoaderCircle className="h-4 w-4 animate-spin" />
                                            ) : (
                                                <FileDiff className="h-4 w-4" />
                                            )}
                                        </Button>
                                    )}
                                </div>
                            );
                        })}
                        {hasMore && (
                            <Button
                                variant="ghost"
                                onClick={onLoadMore}
                                disabled={loadingMore}
                                className="w-full text-sm text-muted-foreground hover:text-foreground hover:bg-accent"
                            >
                                {loadingMore ? (
                                    <LoaderCircle className="w-4 h-4 animate-spin" />
                                ) : (
                                    "Load more"
                                )}
                            </Button>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
};

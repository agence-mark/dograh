"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";
import { usePathname } from "next/navigation";
import React, { ReactNode } from "react";

import { ShellStudio } from "@/components/mark/studio/shell-studio";
import { Button } from "@/components/ui/button";
import { useAppConfig } from "@/context/AppConfigContext";

function BackendStatusBanner() {
  const { config, loading, refresh } = useAppConfig();

  if (!config || config.backendStatus === "reachable") {
    return null;
  }

  const backendUrl = config.backendUrl && config.backendUrl !== "unknown"
    ? config.backendUrl
    : "the configured backend";
  const message = config.backendMessage || `Backend is not reachable at ${backendUrl}.`;

  return (
    <div
      role="alert"
      className="border-b bg-muted px-4 py-3 text-foreground"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-semibold">Backend connection failed</p>
            <p className="break-words text-sm">{message}</p>
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => void refresh()}
          disabled={loading}
          className="h-8 shrink-0 border-border"
        >
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      </div>
    </div>
  );
}

interface AppLayoutProps {
  children: ReactNode;
}

const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  const pathname = usePathname();

  // The frame is hidden for root (/), /handler routes (Stack Auth routes) and /auth routes, plus the sign-in and invitation pages of the .mark team (U2 ter).
  const shouldShowSidebar =
    pathname !== "/" &&
    !pathname.startsWith("/handler") &&
    !pathname.startsWith("/auth") &&
    !["/connexion", "/invitation"].includes(pathname);

  // [.mark] K2: a page of an agent (the flow and its tabs) folds the menu (E5) and fills the frame's top bar itself.
  const isWorkflowEditor = /^\/(workflow|agents)\/\d+(\/(settings|tests|runs|versions|site))?$/.test(pathname);

  // [.mark] U1: the frame of the studio replaces Dograh's sidebar and header.
  if (shouldShowSidebar) {
    return (
        <ShellStudio replie={isWorkflowEditor}>
          <BackendStatusBanner />
          {children}
        </ShellStudio>
    );
  }

  return (
    <div className="app-surface w-full flex-1">
      <BackendStatusBanner />
      {children}
    </div>
  );
};

export default AppLayout;

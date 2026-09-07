"use client";

// [.mark] The OSS counterpart of SidebarTeamSwitcher.
//
// Under Stack Auth the identity provider owns teams and ships its own
// switcher. Under local (OSS) auth nothing did, so an installation could only
// ever hold the single organization its signup created — one customer per
// account, per email address. This is the missing control; the routes behind
// it are in api/services/organization_membership.py.
import { Building2, Check, Loader2, Plus } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import SpinLoader from "@/components/SpinLoader";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth";
import { reloadApp } from "@/lib/browserReload";
import logger from "@/lib/logger";
import {
  createOrganization,
  listOrganizations,
  type Organization,
  selectOrganization,
} from "@/lib/organizationMembership";

export function SidebarOrganizationSwitcher() {
  const { provider, user, loading } = useAuth();

  // The auth interceptor that attaches the bearer token is only registered
  // once auth has finished loading, so mounting the content any earlier would
  // send an unauthenticated request that fails silently (ui/AGENTS.md).
  if (provider !== "local" || loading || !user) {
    return null;
  }

  return <SidebarOrganizationSwitcherContent />;
}

function SidebarOrganizationSwitcherContent() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const hasFetched = useRef(false);
  const [isSwitching, setIsSwitching] = useState(false);
  const [isCreateOpen, setIsCreateOpen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setOrganizations(await listOrganizations());
    } catch (error) {
      // Silent on purpose: an installation running unpatched code answers 404
      // here, and the sidebar must not turn that into a toast on every load.
      logger.error("Failed to list organizations", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (hasFetched.current) return;
    hasFetched.current = true;
    void refresh();
  }, [refresh]);

  const handleSwitch = async (organization: Organization) => {
    if (organization.is_selected) {
      return;
    }
    setIsSwitching(true);
    try {
      await selectOrganization(organization.id);
      // Everything on screen is organization-scoped, so a full reload is the
      // only way to be sure nothing from the previous one survives in a cache.
      reloadApp();
    } catch (error) {
      logger.error("Failed to switch organization", error);
      toast.error("Could not switch organization. Please try again.");
      setIsSwitching(false);
    }
  };

  const selected = organizations.find((organization) => organization.is_selected);

  if (isLoading || organizations.length === 0) {
    return null;
  }

  return (
    <div className="relative">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            className="w-full justify-start gap-2 font-normal"
          >
            <Building2 className="h-4 w-4 shrink-0" />
            <span className="truncate">
              {selected?.provider_id ?? "Select an organization"}
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-[var(--radix-dropdown-menu-trigger-width)]">
          {organizations.map((organization) => (
            <DropdownMenuItem
              key={organization.id}
              onSelect={() => {
                void handleSwitch(organization);
              }}
              className="gap-2"
            >
              <Check
                className={
                  organization.is_selected
                    ? "h-4 w-4 shrink-0"
                    : "h-4 w-4 shrink-0 opacity-0"
                }
              />
              <span className="truncate">{organization.provider_id}</span>
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={() => setIsCreateOpen(true)}
            className="gap-2"
          >
            <Plus className="h-4 w-4 shrink-0" />
            New organization
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <CreateOrganizationDialog
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        onCreated={refresh}
      />

      {isSwitching && (
        <div
          className="fixed inset-0 z-[100] flex min-h-screen items-center justify-center bg-background/90 backdrop-blur-sm"
          role="status"
          aria-live="polite"
        >
          <SpinLoader label="Switching organization..." />
        </div>
      )}
    </div>
  );
}

function CreateOrganizationDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: () => Promise<void>;
}) {
  const [identifier, setIdentifier] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const handleCreate = async () => {
    const trimmed = identifier.trim();
    if (!trimmed) {
      return;
    }
    setIsSaving(true);
    try {
      await createOrganization(trimmed, { select: true });
      // Selected on creation, so the app must reload into it rather than stay
      // showing the previous organization's data under a new name.
      reloadApp();
    } catch (error) {
      logger.error("Failed to create organization", error);
      toast.error(
        error instanceof Error ? error.message : "Could not create the organization",
      );
      setIsSaving(false);
      await onCreated();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New organization</DialogTitle>
          <DialogDescription>
            An organization holds its own agents, phone numbers, telephony
            configuration and provider keys. Nothing is shared with the others.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="organization-identifier">Identifier</Label>
          <Input
            id="organization-identifier"
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            placeholder="acme-plumbing"
            autoComplete="off"
          />
          <p className="text-xs text-muted-foreground">
            Used as the organization&apos;s name across the app. It must be
            unique and cannot be changed afterwards.
          </p>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <Button onClick={() => void handleCreate()} disabled={isSaving || !identifier.trim()}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * [.mark] Non-regression test for the OSS organization switcher.
 *
 * The question this file answers:
 *
 *   Can someone see the organizations they hold, move between them, and add
 *   one — without the control appearing where it would be a lie?
 *
 * The last clause carries the weight. Under Stack Auth the identity provider
 * owns teams and re-derives the current one from the token on every request,
 * so an OSS switcher rendered there would accept a click and be undone by the
 * next page load. Rendering nothing is the correct behaviour, and it is the
 * kind of thing a refactor removes without any screen looking broken.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React, { type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthContext,
  type AuthContextType,
} from "@/lib/auth/providers/AuthProvider";

import { SidebarOrganizationSwitcher } from "../SidebarOrganizationSwitcher";

const mocks = vi.hoisted(() => ({
  listOrganizations: vi.fn(),
  createOrganization: vi.fn(),
  selectOrganization: vi.fn(),
  reloadApp: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@/lib/organizationMembership", () => ({
  listOrganizations: mocks.listOrganizations,
  createOrganization: mocks.createOrganization,
  selectOrganization: mocks.selectOrganization,
}));

vi.mock("@/lib/browserReload", () => ({ reloadApp: mocks.reloadApp }));

vi.mock("sonner", () => ({ toast: { error: mocks.toastError } }));

vi.mock("@/lib/logger", () => ({
  default: { error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() },
}));

// Radix dropdowns and dialogs need layout APIs jsdom does not provide, and the
// point here is the behaviour, not Radix's rendering.
vi.mock("@/components/ui/dropdown-menu", () => ({
  DropdownMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  DropdownMenuContent: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  DropdownMenuItem: ({
    children,
    onSelect,
  }: {
    children: ReactNode;
    onSelect?: () => void;
  }) => (
    <button type="button" onClick={onSelect}>
      {children}
    </button>
  ),
  DropdownMenuSeparator: () => <hr />,
}));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children: ReactNode }) =>
    open ? <div role="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

const NUANCES = { id: 1, provider_id: "client-nuances-de-feu", is_selected: true };
const VERANDA = { id: 2, provider_id: "client-vie-veranda", is_selected: false };

function renderSwitcher(
  provider: "local" | "stack",
  { loading = false, user = { id: "7", provider: "local" } } = {},
) {
  const value = {
    provider,
    isAuthenticated: !!user,
    user,
    loading,
    getAccessToken: async () => "token",
    redirectToLogin: () => {},
    logout: async () => {},
  } as unknown as AuthContextType;

  return render(
    <AuthContext.Provider value={value}>
      <SidebarOrganizationSwitcher />
    </AuthContext.Provider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listOrganizations.mockResolvedValue([NUANCES, VERANDA]);
});

describe("SidebarOrganizationSwitcher", () => {
  it("shows the current organization and the others alongside it", async () => {
    renderSwitcher("local");

    await waitFor(() =>
      expect(screen.getAllByText("client-nuances-de-feu").length).toBeGreaterThan(0),
    );
    expect(screen.getByText("client-vie-veranda")).toBeTruthy();
  });

  it("switches, then reloads so nothing of the previous organization survives", async () => {
    mocks.selectOrganization.mockResolvedValue({ ...VERANDA, is_selected: true });
    renderSwitcher("local");

    await waitFor(() => screen.getByText("client-vie-veranda"));
    fireEvent.click(screen.getByText("client-vie-veranda"));

    await waitFor(() => expect(mocks.selectOrganization).toHaveBeenCalledWith(2));
    expect(mocks.reloadApp).toHaveBeenCalled();
  });

  it("does not call the backend when picking the organization already current", async () => {
    renderSwitcher("local");

    await waitFor(() => screen.getAllByText("client-nuances-de-feu"));
    fireEvent.click(screen.getAllByText("client-nuances-de-feu")[1]);

    await waitFor(() => expect(mocks.selectOrganization).not.toHaveBeenCalled());
  });

  it("creates an organization and moves into it", async () => {
    mocks.createOrganization.mockResolvedValue({
      id: 3,
      provider_id: "client-sinea",
      is_selected: true,
    });
    renderSwitcher("local");

    await waitFor(() => screen.getByText("New organization"));
    fireEvent.click(screen.getByText("New organization"));

    fireEvent.change(screen.getByLabelText("Identifier"), {
      target: { value: "client-sinea" },
    });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() =>
      expect(mocks.createOrganization).toHaveBeenCalledWith("client-sinea", {
        select: true,
      }),
    );
    expect(mocks.reloadApp).toHaveBeenCalled();
  });

  it("surfaces a taken identifier instead of failing silently", async () => {
    mocks.createOrganization.mockRejectedValue(
      new Error("An organization with this identifier already exists"),
    );
    renderSwitcher("local");

    await waitFor(() => screen.getByText("New organization"));
    fireEvent.click(screen.getByText("New organization"));
    fireEvent.change(screen.getByLabelText("Identifier"), {
      target: { value: "client-de-pierre" },
    });
    fireEvent.click(screen.getByText("Create"));

    await waitFor(() =>
      expect(mocks.toastError).toHaveBeenCalledWith(
        "An organization with this identifier already exists",
      ),
    );
    expect(mocks.reloadApp).not.toHaveBeenCalled();
  });

  it("asks for nothing while auth is still loading", async () => {
    // The interceptor that attaches the bearer token is registered only once
    // auth has loaded. Fetching earlier sends an unauthenticated request that
    // fails silently, so the switcher would just never appear (ui/AGENTS.md).
    const { container } = renderSwitcher("local", { loading: true });

    await waitFor(() => expect(mocks.listOrganizations).not.toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing under Stack Auth, which owns teams itself", async () => {
    const { container } = renderSwitcher("stack");

    await waitFor(() => expect(mocks.listOrganizations).not.toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when the backend has no membership routes", async () => {
    // An installation running unpatched code answers 404 here. The sidebar
    // must stay silent rather than show a broken control on every page.
    mocks.listOrganizations.mockRejectedValue(new Error("Not found"));
    const { container } = renderSwitcher("local");

    await waitFor(() => expect(mocks.listOrganizations).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });
});

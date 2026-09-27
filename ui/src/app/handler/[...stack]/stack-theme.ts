// Dark token overrides for the embedded Stack Auth form so it blends into the
// auth card surface (zinc-900 background, zinc-100 foreground, the warm CTA
// accent on the primary button, zinc-800 borders/inputs). Stack's theme parser
// does not accept OKLCH strings, so keep these values in hex.

import type { StackTheme } from "@stackframe/stack";
import type { ComponentProps } from "react";

type ThemeConfig = NonNullable<ComponentProps<typeof StackTheme>["theme"]>;

export const stackAuthDarkTheme: ThemeConfig = {
  dark: {
    background: "#141414",
    foreground: "#f5f5f5",
    card: "#141414",
    cardForeground: "#f5f5f5",
    popover: "#141414",
    popoverForeground: "#f5f5f5",
    primary: "#f5f5f5",
    primaryForeground: "#0e0e0e",
    secondary: "#1f1f1f",
    secondaryForeground: "#f5f5f5",
    muted: "#1f1f1f",
    mutedForeground: "#9a9a9a",
    accent: "#1a1a1a",
    accentForeground: "#f5f5f5",
    destructive: "#f16a6e",
    destructiveForeground: "#f5f5f5",
    border: "#242424",
    input: "#2c2c2c",
    ring: "#5c5c5c",
  },
  radius: "0.625rem",
};

"use client";

import { ExternalLink } from "lucide-react";

import { SectionAnnonceOuverture } from "@/components/mark/SectionAnnonceOuverture";
import { SectionLexiqueMetier } from "@/components/mark/SectionLexiqueMetier";
import { MCPSection } from "@/components/MCPSection";
import { OrganizationPreferencesSection } from "@/components/OrganizationPreferencesSection";
import { TelemetrySection } from "@/components/TelemetrySection";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="flex justify-center py-12 px-4">
      <div className="w-full max-w-2xl space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Platform Settings</h1>
          <p className="text-muted-foreground">
            Manage your platform configuration and integrations.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Preferences</CardTitle>
            <CardDescription>
              Set organization-wide defaults such as the test phone number and
              timezone.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <OrganizationPreferencesSection />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Trade vocabulary</CardTitle>
            <CardDescription>
              The names and words of this business: recognised before the model
              reads them, listened for by the transcription, and pronounced the
              way you write them.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SectionLexiqueMetier />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Closed-business announcement</CardTitle>
            <CardDescription>
              What every agent of this organization says when it picks up while
              the business is closed or on a break, and the state you can force
              by hand until a date.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SectionAnnonceOuverture />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>MCP Server</CardTitle>
            <CardDescription>
              Let AI agents access your Dograh workspace and documentation via
              the Model Context Protocol.{" "}
              <a
                href="https://docs.dograh.com/integrations/mcp"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 underline"
              >
                Learn more <ExternalLink className="h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <MCPSection />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Telemetry</CardTitle>
            <CardDescription>
              Configure Langfuse tracing for your voice agent calls.{" "}
              <a
                href="https://docs.dograh.com/configurations/tracing"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 underline"
              >
                Learn more <ExternalLink className="h-3 w-3" />
              </a>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TelemetrySection />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

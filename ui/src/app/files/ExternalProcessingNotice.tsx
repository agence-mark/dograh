'use client';

import { Info } from 'lucide-react';

import { useAppConfig } from '@/context/AppConfigContext';

export default function ExternalProcessingNotice() {
  const { config } = useAppConfig();
  if (config?.deploymentMode !== 'oss') return null;

  return (
    <div className="flex gap-3 rounded-lg bg-muted p-3">
      <Info className="h-4 w-4 flex-shrink-0 text-(--signal-warn) mt-0.5" />
      <div className="text-xs text-foreground">
        <p className="font-medium">Processed by an external service</p>
        <p className="mt-1">
          Documents are sent to Dograh&apos;s managed Model Proxy Service for parsing and
          chunking when they are uploaded or edited. Dograh Model Proxy Service does not
          store or read your documents - the extracted text and embeddings are returned
          and stored locally in your self-hosted database.
        </p>
      </div>
    </div>
  );
}

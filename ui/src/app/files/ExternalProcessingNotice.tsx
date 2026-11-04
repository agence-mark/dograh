'use client';

import { Info } from 'lucide-react';

import { useLangue } from '@/components/mark/langue/langue';
import { Info as Explication } from '@/components/mark/studio/marques';
import { useAppConfig } from '@/context/AppConfigContext';

// [.mark] V2b: in a window an explanation is never a visible note (and never orange): `enInfo` puts the same
// notice in the « ! » next to the window title.
export default function ExternalProcessingNotice({ enInfo = false }: { enInfo?: boolean }) {
  const { config } = useAppConfig();
  const { t } = useLangue();
  if (config?.deploymentMode !== 'oss') return null;

  if (enInfo) {
    return (
      <Explication>
        {t({
          en: "Processed by an external service. Documents are sent to Dograh's managed Model Proxy Service for parsing and chunking when they are uploaded or edited. That service does not store or read your documents: the extracted text and embeddings are returned and stored in your own database.",
          fr: "Traité par un service externe. Les documents sont envoyés au service Model Proxy géré par Dograh pour être lus et découpés quand ils sont ajoutés ou modifiés. Ce service ne conserve ni ne lit vos documents : le texte extrait et les embeddings sont renvoyés et stockés dans votre propre base de données.",
        })}
      </Explication>
    );
  }

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

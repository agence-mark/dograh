import { PageDesAgents } from './page-des-agents';

export const dynamic = 'force-dynamic';

// [.mark] V1 : la liste des agents vit dans `page-des-agents.tsx` (une page ne peut exporter que sa page) ; ici, l'adresse neutre.
export default function WorkflowPage(props: { searchParams?: Promise<{ dossier?: string }>; params?: Promise<{ org?: string }> }) {
    return PageDesAgents(props);
}

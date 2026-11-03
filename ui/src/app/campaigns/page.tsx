"use client";

import { Megaphone, Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { getCampaignsApiV1CampaignGet } from '@/client/sdk.gen';
import type { CampaignsResponse } from '@/client/types.gen';
import { useLangue } from '@/components/mark/langue/langue';
import { EtatVide } from '@/components/mark/studio/etat-vide';
import { PointEtat } from '@/components/mark/studio/marques';
import { Paginee } from '@/components/mark/studio/pagination';
import { PageStudio } from '@/components/mark/studio/shell-studio';
import { Cellule, Ligne, Tableau } from '@/components/mark/studio/tableau';
import { TitrePage } from '@/components/mark/studio/titre-page';
import { Button } from '@/components/ui/button';
import { useOrganizationTimezone } from '@/hooks/useOrganizationTimezone';
import { useAuth } from '@/lib/auth';
import { formatDate } from '@/lib/dateTime';

import { etatCampagne } from './etat-campagne';

/**
 * [.mark] K8 : Campagnes à la forme de la maquette (`EcranCampagnes`) : un titre, « Nouvelle campagne », puis un tableau
 * nu (Campagne, Agent, État, Appels passés, Créée) dont un clic sur la ligne ouvre la campagne. Mêmes routes qu'avant.
 */
export default function CampaignsPage() {
    const { user, loading: authLoading } = useAuth();
    const organizationTimezone = useOrganizationTimezone();
    const router = useRouter();
    const { t } = useLangue();

    const [campaignsData, setCampaignsData] = useState<CampaignsResponse | null>(null);
    const [illisible, setIllisible] = useState(false);

    // Une seule lecture, quand l'authentification est prête (`pret` est un booléen : l'objet utilisateur peut changer
    // d'identité sans que rien n'ait changé).
    const pret = !authLoading && Boolean(user);
    const lire = useCallback(async () => {
        setIllisible(false);
        try {
            const reponse = await getCampaignsApiV1CampaignGet();
            if (reponse.error || !reponse.data) setIllisible(true);
            else setCampaignsData(reponse.data);
        } catch {
            setIllisible(true);
        }
    }, []);
    useEffect(() => {
        if (pret) void lire();
    }, [pret, lire]);
    useEffect(() => {
        router.prefetch('/campaigns/new');
    }, [router]);

    const campagnes = campaignsData?.campaigns ?? [];

    return (
        <PageStudio>
            <TitrePage
                titre={t({ en: 'Campaigns', fr: 'Campagnes' })}
                info={t({ en: 'Outbound calls in series, from a file.', fr: 'Appels sortants en série, depuis un fichier.' })}
                action={
                    <Button onClick={() => router.push('/campaigns/new')}>
                        <Plus className="size-4" />
                        {t({ en: 'New campaign', fr: 'Nouvelle campagne' })}
                    </Button>
                }
            />
            {illisible ? (
                <EtatVide cas="erreur" reessayer={() => void lire()} />
            ) : campaignsData === null ? (
                <EtatVide cas="chargement" />
            ) : campagnes.length === 0 ? (
                <EtatVide cas="premier" icone={Megaphone} titre={t({ en: 'No campaign yet', fr: "Aucune campagne pour l'instant" })} />
            ) : (
                <Paginee liste={campagnes}>
                    {(page) => (
                        <Tableau
                            colonnes={[
                                { titre: t({ en: 'Campaign', fr: 'Campagne' }) },
                                { titre: t({ en: 'Agent', fr: 'Agent' }) },
                                { titre: t({ en: 'State', fr: 'État' }) },
                                { titre: t({ en: 'Calls made', fr: 'Appels passés' }), droite: true },
                                { titre: t({ en: 'Created', fr: 'Créée' }), droite: true },
                            ]}
                        >
                            {page.map((campaign) => {
                                const etat = etatCampagne(campaign.state);
                                const variantes = campaign.traffic_split?.variants.length ?? 1;
                                return (
                                    <Ligne key={campaign.id} href={`/campaigns/${campaign.id}`}>
                                        <Cellule principale>{campaign.name}</Cellule>
                                        <Cellule>
                                            {campaign.workflow_name}
                                            {variantes > 1 && <span> +{variantes - 1}</span>}
                                        </Cellule>
                                        <Cellule>
                                            <PointEtat etat={etat.point}>{t(etat.libelle)}</PointEtat>
                                        </Cellule>
                                        <Cellule droite>
                                            {campaign.executed_count} / {campaign.total_queued_count}
                                        </Cellule>
                                        <Cellule droite>{formatDate(campaign.created_at, organizationTimezone)}</Cellule>
                                    </Ligne>
                                );
                            })}
                        </Tableau>
                    )}
                </Paginee>
            )}
        </PageStudio>
    );
}

"use client";

import { RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { getCampaignTrafficStatsApiV1CampaignCampaignIdTrafficStatsGet } from '@/client/sdk.gen';
import type { CampaignResponse, CampaignTrafficStatsResponse } from '@/client/types.gen';
import { useLangue } from '@/components/mark/langue/langue';
import { phraseEchec } from '@/components/mark/notifications/echec-affiche';
import { ECHECS } from '@/components/mark/notifications/phrases-echec';
import { EtatVide } from '@/components/mark/studio/etat-vide';
import { Info } from '@/components/mark/studio/marques';
import { Cellule, Ligne, Tableau, TitreTableau } from '@/components/mark/studio/tableau';
import { Button } from '@/components/ui/button';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';

/**
 * [.mark] K8 : la répartition du trafic d'une campagne, en tableau nu (jamais dans un cadre). Mêmes routes, mêmes
 * colonnes ; l'explication passe par le « ! ».
 */
export default function CampaignTrafficStats({ campaign }: { campaign: CampaignResponse }) {
    const { user, loading } = useAuth();
    const { t } = useLangue();
    const [stats, setStats] = useState<CampaignTrafficStatsResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [refresh, setRefresh] = useState(0);
    const revision = campaign.traffic_split?.revision;
    // Un booléen et non l'objet utilisateur : celui-ci peut changer d'identité sans que rien n'ait changé.
    const pret = !loading && Boolean(user);
    useEffect(() => {
        if (!pret) return;
        let cancelled = false;
        let timer: ReturnType<typeof setTimeout> | undefined;
        const fetchStats = async () => {
            try {
                const response = await getCampaignTrafficStatsApiV1CampaignCampaignIdTrafficStatsGet({ path: { campaign_id: campaign.id } });
                if (cancelled) return;
                if (response.error) throw new Error(detailFromError(response.error, 'Failed to load traffic statistics'));
                setStats(response.data ?? null);
                setError(null);
            } catch (e) {
                if (!cancelled) setError(phraseEchec(e, ECHECS.campagneTrafic));
            } finally {
                if (!cancelled && ['running', 'syncing'].includes(campaign.state)) timer = setTimeout(fetchStats, 10000);
            }
        };
        fetchStats();
        return () => { cancelled = true; clearTimeout(timer); };
    }, [campaign.id, campaign.state, revision, pret, refresh]);

    return (
        <section>
            <TitreTableau
                titre={t({ en: 'Traffic split', fr: 'Répartition du trafic' })}
                info={
                    <Info>
                        {t({
                            en: 'Target is the current split. Actual share includes all call attempts and retries, including earlier splits. Small campaigns may differ from the target.',
                            fr: "La cible est la répartition actuelle. La part réelle compte toutes les tentatives et les relances, répartitions précédentes comprises. Une petite campagne peut s'éloigner de la cible.",
                        })}
                    </Info>
                }
                action={
                    <Button type="button" variant="outline" size="sm" onClick={() => setRefresh((r) => r + 1)}>
                        <RefreshCw className="size-3.5" />
                        {t({ en: 'Refresh', fr: 'Actualiser' })}
                    </Button>
                }
            />
            {!stats ? (
                error ? <EtatVide cas="erreur" compact reessayer={() => setRefresh((r) => r + 1)} /> : <EtatVide cas="chargement" />
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: 'Agent / version', fr: 'Agent / version' }) },
                        { titre: t({ en: 'Target', fr: 'Cible' }), droite: true },
                        { titre: t({ en: 'Actual', fr: 'Réel' }), droite: true },
                        { titre: t({ en: 'Completed attempts', fr: 'Tentatives abouties' }), droite: true },
                        { titre: t({ en: 'Outcomes', fr: 'Issues' }) },
                    ]}
                >
                    {stats.variants.map((variant) => (
                        <Ligne key={variant.id}>
                            <Cellule
                                principale
                                sous={
                                    <>
                                        {variant.workflow_definition_id == null
                                            ? t({ en: 'Latest published', fr: 'Dernière publiée' })
                                            : `${t({ en: 'Version', fr: 'Version' })} ${variant.version_number ?? variant.workflow_definition_id}`}
                                        {variant.workflow_definition_id == null && (variant.definitions?.length ?? 0) > 0 && (
                                            <span className="block">
                                                {(variant.definitions ?? []).map((d, index) => (
                                                    <span key={d.definition_id ?? 'unversioned'}>
                                                        {index > 0 && ' · '}
                                                        {d.version_number != null ? (
                                                            <Link className="cursor-pointer hover:font-semibold" href={`/workflow/${variant.workflow_id}?version=${d.version_number}`}>
                                                                v{d.version_number}
                                                            </Link>
                                                        ) : (
                                                            t({ en: 'Unversioned', fr: 'Sans version' })
                                                        )}
                                                        : {d.attempts}
                                                    </span>
                                                ))}
                                            </span>
                                        )}
                                    </>
                                }
                            >
                                <Link
                                    className="cursor-pointer hover:font-semibold"
                                    href={`/workflow/${variant.workflow_id}${variant.workflow_definition_id == null ? '?version=latest' : variant.version_number != null ? `?version=${variant.version_number}` : ''}`}
                                >
                                    {variant.workflow_name}
                                </Link>
                            </Cellule>
                            <Cellule droite>{variant.target_weight == null ? t({ en: 'Removed', fr: 'Retirée' }) : `${variant.target_weight}%`}</Cellule>
                            <Cellule droite>{(variant.actual_percentage ?? 0).toFixed(1)}%</Cellule>
                            <Cellule droite>
                                {variant.completed} / {variant.attempts}
                            </Cellule>
                            <Cellule>
                                {Object.entries(variant.outcomes ?? {})
                                    .map(([outcome, count]) => `${outcome.replaceAll('_', ' ')}: ${count}`)
                                    .join(' · ') || t({ en: 'No attempts yet', fr: 'Aucune tentative' })}
                            </Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}
        </section>
    );
}

"use client";

/**
 * [.mark] Builder partie 3, SA-L3d (décision 21) : l'onglet « Versions » de la fenêtre d'un outil. Les versions de la plus récente à
 * la plus ancienne ; sous chacune, qui l'utilise (agent, branche) ; « N agents restent sur la version précédente » ; « Passer à la
 * v5 » sur chaque agent resté en arrière (fenêtre de confirmation centrée). La règle est dite en bulle.
 */
import { useLangue } from "../../langue/langue";
import { Section } from "../../studio/fenetre-onglets";
import { Info } from "../../studio/marques";
import { Cellule, Ligne, Tableau } from "../../studio/tableau";
import { BoutonPasser } from "./BoutonPasser";
import { REGLE_VERSIONS_OUTIL, T } from "./textes";
import { useVersionsDUnOutil } from "./useVersionsOutils";

const date = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString() : "");

export function OngletVersions({ toolUuid, nom }: { toolUuid: string; nom: string }) {
    const { t } = useLangue();
    const { vue, echec } = useVersionsDUnOutil(toolUuid);

    if (echec) return <p className="text-sm text-destructive">{t(T.erreurLecture)}</p>;
    if (!vue) return <p className="text-sm text-muted-foreground">{t(T.chargement)}</p>;
    if (vue.versions.length === 0) return <p className="text-sm text-muted-foreground">{t(T.aucuneVersion)}</p>;

    return (
        <div data-onglet-versions>
            {vue.agents_en_retard > 0 && (
                <p className="flex items-center gap-1.5 pb-4 text-sm font-medium" data-agents-en-retard>
                    {t(T.retard(vue.agents_en_retard))}
                    <Info>{t(REGLE_VERSIONS_OUTIL)}</Info>
                </p>
            )}
            {vue.versions.map((v) => {
                const ici = vue.usage.filter((u) => u.version_outil === v.version);
                return (
                    <Section
                        key={v.version}
                        titre={`v${v.version}${v.courante ? ` · ${t(T.derniere)}` : ""}`}
                        info={v.courante ? t(REGLE_VERSIONS_OUTIL) : undefined}
                    >
                        <p className="pb-2 pt-1 text-xs text-muted-foreground">{date(v.cree_le)}</p>
                        {ici.length > 0 ? (
                            <Tableau colonnes={[{ titre: t(T.colAgent) }, { titre: t(T.colBranche) }, { titre: "", droite: true }]}>
                                {ici.map((u) => (
                                    <Ligne key={`${u.workflow_id}-${u.branche_id ?? "p"}-${u.brouillon ? "b" : "v"}`}>
                                        <Cellule principale>{u.agent}</Cellule>
                                        <Cellule>
                                            {u.branche}
                                            {u.brouillon && <span className="ml-2 text-xs text-muted-foreground">{t(T.dansLeBrouillonCourt)}</span>}
                                        </Cellule>
                                        <Cellule droite>
                                            {!v.courante && !u.brouillon && (
                                                <BoutonPasser
                                                    cible={{
                                                        toolUuid,
                                                        outil: nom,
                                                        workflowId: u.workflow_id,
                                                        agent: u.agent,
                                                        branche: u.branche,
                                                        brancheId: u.branche_id ?? null,
                                                        de: v.version,
                                                        vers: vue.courante,
                                                    }}
                                                />
                                            )}
                                        </Cellule>
                                    </Ligne>
                                ))}
                            </Tableau>
                        ) : (
                            <p className="text-sm text-muted-foreground">{t(T.aucunAgent)}</p>
                        )}
                    </Section>
                );
            })}
        </div>
    );
}

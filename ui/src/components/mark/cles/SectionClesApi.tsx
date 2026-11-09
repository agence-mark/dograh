"use client";

/**
 * [.mark] Clôture, lot D2 (É70) : les clés d'API de Dograh, au design du fork. Avant, la page d'amont « Portail
 * développeur » (grand titre, cartes, colonne de texte réduite à trois mots) était enchâssée dans le thème Développeurs.
 * Ici : un tableau sans cadre (nom, rôle, état, dernière utilisation), un clic sur une ligne ouvre la clé dans le panneau
 * de droite (rôle, suspension, trois interrupteurs MCP, archivage), « Créer une clé » est une fenêtre de deux champs au
 * panneau aussi, et la clé créée (montrée une seule fois) s'ouvre dans le panneau. Mêmes routes que la page d'amont,
 * aucune fonction en moins ; chaque écriture dit son résultat par une notification.
 */
import { KeyRound, Plus, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
    archiveApiKeyApiV1UserApiKeysApiKeyIdDelete,
    createApiKeyApiV1UserApiKeysPost,
    getApiKeysApiV1UserApiKeysGet,
    listerLesRolesApiV1EquipeMarkRolesGet,
    reactivateApiKeyApiV1UserApiKeysApiKeyIdReactivatePut,
} from "@/client/sdk.gen";
import type { ApiKeyResponse, CreateApiKeyResponse, RoleResponse } from "@/client/types.gen";
import { PanneauDroitsCle } from "@/components/mark/cles/PanneauDroitsCle";
import { regenererLaClePortail } from "@/components/mark/equipe/api-cloture";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { useOrganizationTimezone } from "@/hooks/useOrganizationTimezone";
import { useAuth } from "@/lib/auth";
import { copyTextToClipboard } from "@/lib/clipboard";
import { formatDateTime } from "@/lib/dateTime";

const T = {
    titre: { fr: "Clés d'API", en: "API keys" },
    creer: { fr: "Créer une clé", en: "Create a key" },
    archivees: { fr: "Voir les clés archivées", en: "Show archived keys" },
    masquer: { fr: "Masquer les clés archivées", en: "Hide archived keys" },
    nom: { fr: "Nom", en: "Name" },
    role: { fr: "Rôle", en: "Role" },
    etat: { fr: "État", en: "Status" },
    usage: { fr: "Dernière utilisation", en: "Last used" },
    jamais: { fr: "Jamais", en: "Never" },
    active: { fr: "Active", en: "Active" },
    suspendue: { fr: "Suspendue", en: "Suspended" },
    archivee: { fr: "Archivée", en: "Archived" },
    inactive: { fr: "Inactive", en: "Inactive" },
    sansRole: { fr: "Aucun (liste fermée du portail)", en: "None (closed portal list)" },
    vide: { fr: "Aucune clé pour l'instant", en: "No key yet" },
    nomDeLaCle: { fr: "Nom de la clé", en: "Key name" },
    roleDeLaCle: { fr: "Rôle de la clé", en: "Key role" },
    aideNom: { fr: "Un nom qui dit à quoi elle sert, par exemple « Serveur de production ».", en: "A name that says what it is for, for example “Production server”." },
    nomRequis: { fr: "Donnez un nom à la clé.", en: "Give the key a name." },
    fermer: { fr: "Fermer", en: "Close" },
    terminer: { fr: "Terminé", en: "Done" },
    regenerer: { fr: "Régénérer la clé du portail", en: "Regenerate the portal key" },
    confirmerRegeneration: { fr: "Confirmer la révocation", en: "Confirm revocation" },
    aideRegeneration: { fr: "L'ancienne clé du portail est révoquée dès la confirmation.", en: "The old portal key is revoked as soon as you confirm." },
    cleCreee: { fr: "Clé créée", en: "Key created" },
    aideCleCreee: { fr: "Copiez la clé maintenant : elle ne sera plus jamais affichée.", en: "Copy the key now: it will never be shown again." },
    copier: { fr: "Copier la clé", en: "Copy the key" },
    archiver: { fr: "Archiver la clé", en: "Archive the key" },
    reactiver: { fr: "Réactiver la clé", en: "Reactivate the key" },
    creeeLe: { fr: "Créée", en: "Created" },
} satisfies Record<string, Texte>;

type Cle = ApiKeyResponse & { suspendue?: boolean; role_nom?: string | null; role_id?: number | null };

export function SectionClesApi() {
    const { user, getAccessToken, loading } = useAuth();
    const { t, langue } = useLangue();
    const fuseau = useOrganizationTimezone();
    const [cles, setCles] = useState<Cle[] | null>(null);
    const [erreur, setErreur] = useState(false);
    const [archivees, setArchivees] = useState(false);
    const [roles, setRoles] = useState<RoleResponse[]>([]);
    const [creation, setCreation] = useState(false);
    const [creee, setCreee] = useState<CreateApiKeyResponse | null>(null);
    const [ouverteId, setOuverteId] = useState<number | null>(null);
    const [confirmerRegeneration, setConfirmerRegeneration] = useState(false);

    const entetes = useCallback(async () => ({ Authorization: `Bearer ${await getAccessToken()}` }), [getAccessToken]);

    const lire = useCallback(async () => {
        if (loading || !user) return;
        setErreur(false);
        const reponse = await getApiKeysApiV1UserApiKeysGet({ query: { include_archived: archivees }, headers: await entetes() }).catch(() => null);
        if (!reponse || reponse.error) {
            setErreur(true);
            return;
        }
        setCles((reponse.data as Cle[] | undefined) ?? []);
    }, [loading, user, archivees, entetes]);

    // Les clés et les rôles se lisent ensemble (jamais l'un après l'autre).
    useEffect(() => {
        void lire();
    }, [lire]);
    useEffect(() => {
        void listerLesRolesApiV1EquipeMarkRolesGet().then((res) => setRoles(res.data ?? []));
    }, []);

    const date = (valeur: string | null | undefined) => (valeur ? formatDateTime(valeur, fuseau, langue) : t(T.jamais));
    const ouverte = useMemo(() => cles?.find((c) => c.id === ouverteId) ?? null, [cles, ouverteId]);

    const creer = async (valeurs: Record<string, string | boolean | string[]>) => {
        const role = roles.find((r) => r.nom === valeurs.role);
        const reponse = await createApiKeyApiV1UserApiKeysPost({
            body: { name: String(valeurs.nom).trim(), ...(role ? { role_id: role.id } : {}) } as { name: string },
            headers: await entetes(),
        });
        if (reponse.error || !reponse.data) {
            notifier.echec({ fr: "Clé non créée. Réessayez.", en: "Key not created. Try again." }, { erreur: reponse.error });
            return false;
        }
        notifier.succes({ fr: "Clé créée.", en: "Key created." });
        setCreee(reponse.data);
        await lire();
    };

    const regenerer = async () => {
        if (!confirmerRegeneration) {
            setConfirmerRegeneration(true);
            return;
        }
        setConfirmerRegeneration(false);
        const res = await regenererLaClePortail();
        if (res.error || !res.data) {
            notifier.echec({ fr: "Clé du portail non régénérée. Réessayez.", en: "Portal key not regenerated. Try again." }, { erreur: res.error });
            return;
        }
        notifier.succes({ fr: "Clé du portail régénérée : l'ancienne est révoquée.", en: "Portal key regenerated: the old one is revoked." });
        setCreee(res.data as unknown as CreateApiKeyResponse);
        await lire();
    };

    const archiver = async (id: number) => {
        const reponse = await archiveApiKeyApiV1UserApiKeysApiKeyIdDelete({ path: { api_key_id: id }, headers: await entetes() });
        if (reponse.error) {
            notifier.echec({ fr: "Clé non archivée. Réessayez.", en: "Key not archived. Try again." }, { erreur: reponse.error });
            return;
        }
        // Un archivage se rattrape : « Annuler » différé (la clé redevient active), pas de confirmation à cliquer.
        notifier.reversible({ fr: "Clé archivée.", en: "Key archived." }, async () => {
            await reactivateApiKeyApiV1UserApiKeysApiKeyIdReactivatePut({ path: { api_key_id: id }, headers: await entetes() });
            await lire();
        });
        setOuverteId(null);
        await lire();
    };

    const reactiver = async (id: number) => {
        const reponse = await reactivateApiKeyApiV1UserApiKeysApiKeyIdReactivatePut({ path: { api_key_id: id }, headers: await entetes() });
        if (reponse.error) {
            notifier.echec({ fr: "Clé non réactivée. Réessayez.", en: "Key not reactivated. Try again." }, { erreur: reponse.error });
            return;
        }
        notifier.succes({ fr: "Clé réactivée.", en: "Key reactivated." });
        await lire();
    };

    const copier = async (texte: string) => {
        try {
            await copyTextToClipboard(texte);
            notifier.succes({ fr: "Clé copiée.", en: "Key copied." });
        } catch {
            notifier.echec({ fr: "Copie impossible. Sélectionnez la clé à la main.", en: "Could not copy. Select the key by hand." });
        }
    };

    const etat = (c: Cle) => (c.archived_at ? T.archivee : c.suspendue ? T.suspendue : c.is_active ? T.active : T.inactive);

    return (
        <div data-testid="section-cles-api" className="space-y-1">
            <TitreTableau
                titre={t(T.titre)}
                action={
                    <span className="flex flex-wrap items-center gap-2">
                        <Button variant="ghost" size="sm" className="cursor-pointer" onClick={() => setArchivees((v) => !v)}>
                            {archivees ? t(T.masquer) : t(T.archivees)}
                        </Button>
                        <Button
                            variant={confirmerRegeneration ? "destructive" : "outline"}
                            size="sm"
                            className="cursor-pointer"
                            title={t(T.aideRegeneration)}
                            onClick={() => void regenerer()}
                            onBlur={() => setConfirmerRegeneration(false)}
                        >
                            <RefreshCw className="size-4" />
                            {confirmerRegeneration ? t(T.confirmerRegeneration) : t(T.regenerer)}
                        </Button>
                        <Button size="sm" className="cursor-pointer" onClick={() => setCreation(true)}>
                            <Plus className="size-4" />
                            {t(T.creer)}
                        </Button>
                    </span>
                }
            />
            {erreur ? (
                <EtatVide cas="erreur" compact reessayer={() => void lire()} />
            ) : cles === null ? (
                <EtatVide cas="chargement" lignes={3} />
            ) : cles.length === 0 ? (
                <EtatVide cas="premier" compact icone={KeyRound} titre={t(T.vide)} />
            ) : (
                <Tableau colonnes={[{ titre: t(T.nom) }, { titre: t(T.role) }, { titre: t(T.etat) }, { titre: t(T.usage) }]}>
                    {cles.map((c) => (
                        <Ligne key={c.id} onClick={() => setOuverteId(c.id)}>
                            <Cellule principale sous={`${c.key_prefix}...`}>
                                {c.name}
                            </Cellule>
                            <Cellule>{c.role_nom ?? t({ fr: "Aucun", en: "None" })}</Cellule>
                            <Cellule>{t(etat(c))}</Cellule>
                            <Cellule>{date(c.last_used_at ?? null)}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}

            <FenetreChamps
                ouverte={creation}
                fermer={() => setCreation(false)}
                titre={t(T.creer)}
                valider={t(T.creer)}
                sections={[
                    {
                        champs: [
                            { id: "nom", t: "texte", l: t(T.nomDeLaCle), info: t(T.aideNom) },
                            { id: "role", t: "choix", l: t(T.roleDeLaCle), o: [t(T.sansRole), ...roles.map((r) => r.nom)] },
                        ],
                    },
                ]}
                verifier={(v) => (String(v.nom).trim() ? null : { nom: t(T.nomRequis) })}
                onValider={creer}
            />

            {creee && (
                <FenetreChamps
                    ouverte
                    fermer={() => setCreee(null)}
                    titre={t(T.cleCreee)}
                    info={t(T.aideCleCreee)}
                    sections={[]}
                    lecture
                    etroite
                    valider={t(T.terminer)}
                    corps={
                        <div className="flex items-center gap-2">
                            <code data-testid="cle-creee" className="min-w-0 flex-1 break-all text-sm">
                                {creee.api_key}
                            </code>
                            <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => void copier(creee.api_key)}>
                                {t(T.copier)}
                            </Button>
                        </div>
                    }
                />
            )}

            {ouverte && (
                <FenetreDeLaCle
                    cle={ouverte}
                    date={date}
                    fermer={() => setOuverteId(null)}
                    recharger={() => void lire()}
                    archiver={() => archiver(ouverte.id)}
                    reactiver={() => reactiver(ouverte.id)}
                />
            )}
        </div>
    );
}

function FenetreDeLaCle({
    cle,
    date,
    fermer,
    recharger,
    archiver,
    reactiver,
}: {
    cle: Cle;
    date: (v: string | null | undefined) => string;
    fermer: () => void;
    recharger: () => void;
    archiver: () => Promise<void>;
    reactiver: () => Promise<void>;
}) {
    const { t } = useLangue();
    return (
        <FenetreChamps
            ouverte
            fermer={fermer}
            titre={cle.name}
            sections={[]}
            lecture
            etroite
            valider={t(T.fermer)}
            corps={
                <section className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                        <span className="font-mono">{cle.key_prefix}...</span> · {t(T.creeeLe)} {date(cle.created_at)} · {t(T.usage)} : {date(cle.last_used_at ?? null)}
                    </p>
                    {!cle.archived_at && <PanneauDroitsCle cle={cle as never} recharger={recharger} />}
                </section>
            }
            pied={
                cle.archived_at ? (
                    <Button variant="outline" className="cursor-pointer" onClick={() => void reactiver()}>
                        {t(T.reactiver)}
                    </Button>
                ) : (
                    <Button variant="ghost" className="cursor-pointer text-(--marque-danger-texte)" onClick={() => void archiver()}>
                        {t(T.archiver)}
                    </Button>
                )
            }
        />
    );
}

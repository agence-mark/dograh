"use client";

/**
 * [.mark] Chantier cloture-code-avant-migration, lot F7 (D116, D117) : la section « Objets » du thème
 * « Établissements », à côté des fiches et des phrases. Une carte cliquable par objet (libellé précédé du lieu pour
 * un objet d'établissement, nom technique en gris, description, « utilisé par » calculé, jauge), qui ouvre sa
 * modale centrée ; « Ajouter un objet » ouvre la même, vide. Le plafond (D112) est un champ de la section, avec son
 * propre bouton : il s'écrit dans la base du client, comme les objets (exception E6 de la base du client).
 *
 * Sans base rattachée, la section dit ce que le serveur répond et ne propose rien.
 */
import { ChevronRight, Plus } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { getObjetsApiV1OrganizationsObjetsGet, putReglagesObjetsApiV1OrganizationsObjetsReglagesPut } from "@/client/sdk.gen";
import type { ObjetAgent, ObjetsAgent } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { useLangue } from "../langue/langue";
import { JaugeObjet, ModaleObjet } from "./ModaleObjet";

/** Les champs de `ReglagesObjets` montrés par la section (l'inventaire les compare au client généré). */
export const CHAMPS_REGLAGES_OBJETS = ["plafond_caracteres"] as const;

export const useObjets = () => {
    const { user, loading: authLoading } = useAuth();
    const [vue, setVue] = useState<ObjetsAgent | null>(null);
    const [refus, setRefus] = useState<string | null>(null);
    const dejaLu = useRef(false);
    const relire = useCallback(async () => {
        const reponse = await getObjetsApiV1OrganizationsObjetsGet();
        if (reponse.error) {
            setRefus(detailFromError(reponse.error, "Objects unreadable"));
            return;
        }
        setRefus(null);
        // Same rule as the fiches (`useResumeEtablissements`): an answer without a body is an empty list.
        setVue(reponse.data ?? { objets: [], plafond_caracteres: 3000 });
    }, []);
    useEffect(() => {
        if (authLoading || !user || dejaLu.current) return;
        dejaLu.current = true;
        void relire();
    }, [authLoading, user, relire]);
    return { vue, refus, relire };
};

export const SectionObjets = ({ etablissements }: { etablissements: Array<{ id: string; nom: string }> }) => {
    const { t } = useLangue();
    const { vue, refus, relire } = useObjets();
    const [ouvert, setOuvert] = useState<ObjetAgent | "neuf" | null>(null);
    const [plafond, setPlafond] = useState("");
    const [erreurPlafond, setErreurPlafond] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const enregistre = vue?.plafond_caracteres ?? 3000;
    useEffect(() => setPlafond(String(enregistre)), [enregistre]);
    const nomDu = (id?: string | null) => etablissements.find((e) => e.id === id)?.nom ?? id;

    const enregistrerPlafond = async () => {
        const n = Number(plafond);
        if (!Number.isInteger(n) || n < 100 || n > 50000) {
            setErreurPlafond(t({ en: "Between 100 and 50,000 characters.", fr: "Entre 100 et 50 000 caractères." }));
            return;
        }
        setEnCours(true);
        setErreurPlafond(null);
        try {
            const reponse = await putReglagesObjetsApiV1OrganizationsObjetsReglagesPut({ body: { plafond_caracteres: n } });
            if (reponse.error) {
                setErreurPlafond(detailFromError(reponse.error, "Ceiling refused"));
                return;
            }
            toast.success(t({ en: "Ceiling saved", fr: "Plafond enregistré" }));
            await relire();
        } finally {
            setEnCours(false);
        }
    };

    return (
        <Intertitre
            id="etablissement-objets"
            titre={{ en: "Objects", fr: "Objets" }}
            description={{
                en: "Business data the agent receives as {{technical name}}: a single value or a list. .mark creates them; the client keeps their content up to date in the portal.",
                fr: "Des données métier que l'agent reçoit en {{nom technique}} : une valeur simple ou une liste. .mark les crée ; le client en tient le contenu à jour dans le portail.",
            }}
        >
            {refus ? (
                <p className="text-sm text-muted-foreground" data-testid="objets-refus">
                    {refus}
                </p>
            ) : !vue ? (
                <p className="text-sm text-muted-foreground">{t({ en: "Loading...", fr: "Chargement..." })}</p>
            ) : (
                <>
                    <div className="space-y-2" data-testid="liste-objets">
                        {(vue.objets ?? []).map((o) => (
                            <button
                                key={o.id}
                                type="button"
                                data-objet={o.nom}
                                onClick={() => setOuvert(o)}
                                className="flex w-full items-start justify-between gap-3 rounded-lg border bg-background p-3 text-left hover:bg-muted/40"
                            >
                                <span className="min-w-0 flex-1 space-y-1">
                                    <span className="block text-sm font-medium">
                                        {o.etablissement ? `${nomDu(o.etablissement)} · ` : ""}
                                        {o.libelle} <span className="font-mono text-xs text-muted-foreground">{`{{${o.nom}}}`}</span>
                                    </span>
                                    {o.description && <span className="block text-xs text-muted-foreground">{o.description}</span>}
                                    <span className="block text-xs text-muted-foreground" data-utilise-par>
                                        {(o.utilise_par ?? []).length > 0
                                            ? `${t({ en: "Used by", fr: "Utilisé par" })} : ${(o.utilise_par ?? []).map((a) => a.nom).join(", ")}`
                                            : t({ en: "Used by no agent", fr: "Utilisé par aucun agent" })}
                                    </span>
                                    <JaugeObjet taille={o.taille ?? 0} plafond={enregistre} />
                                </span>
                                <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                            </button>
                        ))}
                        {(vue.objets ?? []).length === 0 && (
                            <p className="text-sm text-muted-foreground">{t({ en: "No object yet.", fr: "Aucun objet pour l'instant." })}</p>
                        )}
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setOuvert("neuf")} data-testid="ajouter-objet">
                        <Plus className="h-3.5 w-3.5" /> {t({ en: "Add an object", fr: "Ajouter un objet" })}
                    </Button>
                    <ChampReglage
                        cle="plafond_caracteres"
                        idControle="objets-plafond"
                        libelle={{ en: "Ceiling of one object", fr: "Plafond d'un objet" }}
                        aides={[{ en: "Characters of the text the agent receives; an object over it is not saved (here or in the portal).", fr: "Caractères du texte que reçoit l'agent ; un objet au-delà n'est pas enregistré (ici comme au portail)." }]}
                        bornes={{ en: "100 to 50,000, default 3,000", fr: "100 à 50 000, 3 000 par défaut" }}
                        erreur={erreurPlafond ? { en: erreurPlafond, fr: erreurPlafond } : null}
                    >
                        <span className="flex items-center gap-2" data-reglage="plafond_caracteres">
                            <Input id="objets-plafond" type="number" className="h-9 w-32" value={plafond} onChange={(e) => setPlafond(e.target.value)} />
                            <Button size="sm" disabled={enCours || plafond === String(enregistre)} onClick={() => void enregistrerPlafond()} data-testid="enregistrer-plafond">
                                {t({ en: "Save the ceiling", fr: "Enregistrer le plafond" })}
                            </Button>
                        </span>
                    </ChampReglage>
                </>
            )}
            {ouvert && (
                <ModaleObjet
                    objet={ouvert === "neuf" ? null : ouvert}
                    plafond={enregistre}
                    etablissements={etablissements}
                    onFermer={(change) => {
                        setOuvert(null);
                        if (change) void relire();
                    }}
                />
            )}
        </Intertitre>
    );
};

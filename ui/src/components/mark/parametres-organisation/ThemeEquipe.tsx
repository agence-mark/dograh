"use client";

/**
 * [.mark] Theme « Team and routing » (chantier l-agent-travaille, L3; rangement validé le 06/10).
 *
 * The people of the company (by establishment or company-wide) and the routing: which
 * subject goes to whom, in order. Written in the client's database (B2), read by the
 * after-call (L4). A list to edit, so a modal (E4) on a copy: « Cancel » / « Save ».
 * Without an attached database, the theme says so: the team lives there.
 */
import { Plus, Trash2, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
    getEquipeApiV1OrganizationsEquipeGet,
    getEtablissementsApiV1OrganizationsEtablissementsGet,
    putEquipeApiV1OrganizationsEquipePut,
} from "@/client/sdk.gen";
import type { Equipe, Etablissement, Personne, Sujet } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { type Texte, useLangue } from "../langue/langue";
import { identifiantPour } from "./ModaleEtablissements";
import type { ProprietesThemeOrganisation } from "./ThemesOrganisation";

export const TITRE_EQUIPE: Texte = { en: "Team and routing", fr: "Équipe et routage" };

const VIDE: Equipe = { personnes: [], sujets: [] };

export const charge_utile_equipe = (equipe: Equipe): Equipe => ({
    personnes: (equipe.personnes ?? []).map((p) => ({
        ...p,
        prenom: p.prenom.trim(),
        nom: p.nom?.trim() || null,
        role: p.role?.trim() || null,
        mail: p.mail?.trim() || null,
        telephone: p.telephone?.trim() || null,
        etablissement: p.etablissement || null,
    })),
    sujets: (equipe.sujets ?? []).map((s) => ({
        ...s,
        libelle: s.libelle.trim(),
        mots_declencheurs: (s.mots_declencheurs ?? []).map((m) => m.trim()).filter(Boolean),
    })),
});

function ModaleEquipe({ ouverte, onFermer }: { ouverte: boolean; onFermer: (enregistre: boolean) => void }) {
    const { t } = useLangue();
    const [equipe, setEquipe] = useState<Equipe | null>(null);
    const [etablissements, setEtablissements] = useState<Etablissement[]>([]);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);

    useEffect(() => {
        if (!ouverte) return;
        setEquipe(null);
        setErreur(null);
        void (async () => {
            const [reponse, sites] = await Promise.all([
                getEquipeApiV1OrganizationsEquipeGet(),
                getEtablissementsApiV1OrganizationsEtablissementsGet(),
            ]);
            setEtablissements(sites.data?.etablissements ?? []);
            if (reponse.error || !reponse.data) {
                setErreur(detailFromError(reponse.error, "Team unreadable"));
                return;
            }
            setEquipe(reponse.data);
        })();
    }, [ouverte]);

    const personnes = equipe?.personnes ?? [];
    const sujets = equipe?.sujets ?? [];
    const modifierPersonne = (i: number, champ: Partial<Personne>) =>
        setEquipe((a) => (a ? { ...a, personnes: (a.personnes ?? []).map((p, j) => (j === i ? { ...p, ...champ } : p)) } : a));
    const modifierSujet = (i: number, champ: Partial<Sujet>) =>
        setEquipe((a) => (a ? { ...a, sujets: (a.sujets ?? []).map((s, j) => (j === i ? { ...s, ...champ } : s)) } : a));

    const fautes: string[] = [];
    personnes.forEach((p) => {
        if (!p.prenom.trim()) fautes.push(t({ en: "A person has no first name.", fr: "Une personne n'a pas de prénom." }));
    });
    sujets.forEach((s) => {
        if (!s.libelle.trim()) fautes.push(t({ en: "A subject has no name.", fr: "Un sujet n'a pas de nom." }));
    });

    const enregistrer = async () => {
        if (!equipe) return;
        setEnCours(true);
        setErreur(null);
        const reponse = await putEquipeApiV1OrganizationsEquipePut({ body: charge_utile_equipe(equipe) });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Team not saved"));
            return;
        }
        toast.success(t({ en: "Team saved", fr: "Équipe enregistrée" }));
        onFermer(true);
    };

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(false))}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl" data-testid="modale-equipe">
                <DialogHeader>
                    <DialogTitle>{t(TITRE_EQUIPE)}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "Who works where, and who receives each subject, in order. Someone removed is deactivated, never deleted: past requests keep their name.",
                            fr: "Qui travaille où, et qui reçoit chaque sujet, dans l'ordre. Une personne retirée est désactivée, jamais supprimée : les demandes passées gardent son nom.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert" data-testid="erreur-equipe">
                        {erreur}
                    </p>
                )}
                {equipe === null ? (
                    !erreur && <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : (
                    <div className="space-y-6">
                        <section className="space-y-2" data-testid="liste-personnes">
                            <h3 className="text-sm font-medium">{t({ en: "People", fr: "Personnes" })}</h3>
                            {personnes.map((p, i) => (
                                <div key={p.cle} className="grid gap-2 rounded border border-border p-2 sm:grid-cols-3">
                                    <Input aria-label={t({ en: "First name", fr: "Prénom" })} placeholder={t({ en: "First name", fr: "Prénom" })} value={p.prenom} onChange={(e) => modifierPersonne(i, { prenom: e.target.value })} />
                                    <Input aria-label={t({ en: "Last name", fr: "Nom" })} placeholder={t({ en: "Last name", fr: "Nom" })} value={p.nom ?? ""} onChange={(e) => modifierPersonne(i, { nom: e.target.value })} />
                                    <Input aria-label={t({ en: "Role", fr: "Rôle" })} placeholder={t({ en: "Role", fr: "Rôle" })} value={p.role ?? ""} onChange={(e) => modifierPersonne(i, { role: e.target.value })} />
                                    <Input aria-label={t({ en: "E-mail", fr: "E-mail" })} placeholder={t({ en: "E-mail", fr: "E-mail" })} value={p.mail ?? ""} onChange={(e) => modifierPersonne(i, { mail: e.target.value })} />
                                    <Input aria-label={t({ en: "Phone", fr: "Téléphone" })} value={p.telephone ?? ""} placeholder="+33612345678" onChange={(e) => modifierPersonne(i, { telephone: e.target.value })} />
                                    <select
                                        aria-label={t({ en: "Establishment", fr: "Établissement" })}
                                        className="rounded border border-border bg-background px-2 py-1 text-sm"
                                        value={p.etablissement ?? ""}
                                        onChange={(e) => modifierPersonne(i, { etablissement: e.target.value || null })}
                                    >
                                        <option value="">{t({ en: "Whole company", fr: "Toute l'entreprise" })}</option>
                                        {etablissements.map((e) => (
                                            <option key={e.id} value={e.id}>
                                                {e.nom}
                                            </option>
                                        ))}
                                    </select>
                                    <label className="flex items-center gap-2 text-sm">
                                        <input type="checkbox" checked={p.destinataire_defaut ?? false} onChange={(e) => modifierPersonne(i, { destinataire_defaut: e.target.checked })} />
                                        {t({ en: "Default recipient", fr: "Destinataire par défaut" })}
                                    </label>
                                    <label className="flex items-center gap-2 text-sm">
                                        <input type="checkbox" checked={p.actif ?? true} onChange={(e) => modifierPersonne(i, { actif: e.target.checked })} />
                                        {t({ en: "Active", fr: "Active" })}
                                    </label>
                                </div>
                            ))}
                            <Button
                                variant="outline"
                                size="sm"
                                data-testid="ajouter-personne"
                                onClick={() =>
                                    setEquipe((a) => {
                                        const avant = a ?? VIDE;
                                        const cle = identifiantPour(`personne-${(avant.personnes ?? []).length + 1}`, (avant.personnes ?? []).map((p) => p.cle));
                                        return { ...avant, personnes: [...(avant.personnes ?? []), { cle, prenom: "", destinataire_defaut: false, actif: true }] };
                                    })
                                }
                            >
                                <Plus className="mr-1 h-4 w-4" />
                                {t({ en: "Add a person", fr: "Ajouter une personne" })}
                            </Button>
                        </section>

                        <section className="space-y-2" data-testid="liste-sujets">
                            <h3 className="text-sm font-medium">{t({ en: "Routing by subject", fr: "Routage par sujet" })}</h3>
                            {sujets.map((s, i) => (
                                <div key={s.code} className="space-y-2 rounded border border-border p-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <Input className="min-w-0 flex-1" aria-label={t({ en: "Subject", fr: "Sujet" })} value={s.libelle} onChange={(e) => modifierSujet(i, { libelle: e.target.value })} />
                                        <code className="text-xs text-muted-foreground">{s.code}</code>
                                        <label className="flex items-center gap-1 text-sm">
                                            <input type="checkbox" checked={s.urgent ?? false} onChange={(e) => modifierSujet(i, { urgent: e.target.checked })} />
                                            {t({ en: "Urgent", fr: "Urgent" })}
                                        </label>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            aria-label={t({ en: "Remove this subject", fr: "Retirer ce sujet" })}
                                            onClick={() => setEquipe((a) => (a ? { ...a, sujets: (a.sujets ?? []).filter((_s, j) => j !== i) } : a))}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                    <Input
                                        aria-label={t({ en: "Trigger words", fr: "Mots déclencheurs" })}
                                        placeholder={t({ en: "Trigger words, comma-separated", fr: "Mots déclencheurs, séparés par des virgules" })}
                                        value={(s.mots_declencheurs ?? []).join(", ")}
                                        onChange={(e) => modifierSujet(i, { mots_declencheurs: e.target.value.split(",") })}
                                    />
                                    <div className="flex flex-wrap gap-3 text-sm">
                                        {personnes.map((p) => {
                                            const pris = (s.destinataires ?? []).includes(p.cle);
                                            return (
                                                <label key={p.cle} className="flex items-center gap-1">
                                                    <input
                                                        type="checkbox"
                                                        checked={pris}
                                                        onChange={() =>
                                                            modifierSujet(i, {
                                                                destinataires: pris
                                                                    ? (s.destinataires ?? []).filter((c) => c !== p.cle)
                                                                    : [...(s.destinataires ?? []), p.cle],
                                                            })
                                                        }
                                                    />
                                                    {p.prenom || p.cle}
                                                </label>
                                            );
                                        })}
                                    </div>
                                </div>
                            ))}
                            <Button
                                variant="outline"
                                size="sm"
                                data-testid="ajouter-sujet"
                                onClick={() =>
                                    setEquipe((a) => {
                                        const avant = a ?? VIDE;
                                        const codes = (avant.sujets ?? []).map((s) => s.code);
                                        let n = codes.length + 1;
                                        while (codes.includes(`sujet_${n}`)) n += 1;
                                        return {
                                            ...avant,
                                            sujets: [...(avant.sujets ?? []), { code: `sujet_${n}`, libelle: "", mots_declencheurs: [], urgent: false, actif: true, destinataires: [] }],
                                        };
                                    })
                                }
                            >
                                <Plus className="mr-1 h-4 w-4" />
                                {t({ en: "Add a subject", fr: "Ajouter un sujet" })}
                            </Button>
                        </section>
                        {fautes.length > 0 && (
                            <ul className="text-sm text-destructive" data-testid="fautes-equipe">
                                {fautes.map((f, i) => (
                                    <li key={i}>{f}</li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}
                <DialogFooter>
                    <Button variant="outline" onClick={() => onFermer(false)}>
                        {t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    <Button onClick={() => void enregistrer()} disabled={enCours || equipe === null || fautes.length > 0} data-testid="enregistrer-equipe">
                        {t({ en: "Save", fr: "Enregistrer" })}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export const ThemeEquipe = ({
    ouvert,
    onBasculer,
    baseRattachee,
}: ProprietesThemeOrganisation & { baseRattachee: boolean | null }) => {
    const { t } = useLangue();
    const [modale, setModale] = useState(false);
    return (
        <Theme
            id="equipe"
            icone={Users}
            titre={TITRE_EQUIPE}
            description={{
                en: "The people of the company and who receives each subject after a call.",
                fr: "Les personnes de l'entreprise et qui reçoit chaque sujet après un appel.",
            }}
            resume={[
                baseRattachee === null
                    ? t({ en: "Loading...", fr: "Chargement..." })
                    : baseRattachee
                      ? t({ en: "In the client's database", fr: "Dans la base du client" })
                      : t({ en: "No database attached", fr: "Aucune base rattachée" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={false}
            erreurs={[]}
        >
            <Intertitre id="equipe-liste" titre={TITRE_EQUIPE}>
                {baseRattachee ? (
                    <ChampReglage
                        cle="equipe"
                        libelle={{ en: "People and routing", fr: "Personnes et routage" }}
                        aides={[
                            {
                                en: "Written in the client's database; the client will change it from its own screen later.",
                                fr: "Écrits dans la base du client ; le client les modifiera plus tard depuis son propre écran.",
                            },
                        ]}
                        disposition="colonne"
                    >
                        <Button variant="outline" size="sm" onClick={() => setModale(true)} data-testid="ouvrir-equipe">
                            {t({ en: "Edit the team…", fr: "Modifier l'équipe…" })}
                        </Button>
                    </ChampReglage>
                ) : (
                    <p className="text-sm text-muted-foreground" data-testid="equipe-sans-base">
                        {t({
                            en: "Attach the client's database first (theme « Client data »): the team lives there.",
                            fr: "Rattachez d'abord la base du client (thème « Données du client ») : l'équipe y vit.",
                        })}
                    </p>
                )}
                <ModaleEquipe ouverte={modale} onFermer={() => setModale(false)} />
            </Intertitre>
        </Theme>
    );
};

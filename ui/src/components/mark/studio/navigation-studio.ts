/**
 * [.mark] Les menus des deux espaces (E2, E3, E31) et leur lien avec l'écran actuel.
 *
 * Une entrée du menu a DEUX adresses :
 *  - `adresse(base)` : sa place dans la refonte (`/labo/...` ou `/clients/<org>/...`) ;
 *  - `actuelle` : l'écran existant qui porte aujourd'hui sa fonction (carte de rangement, `10-carte-de-rangement.md`).
 * Tant qu'un écran n'est pas construit, l'entrée mène à l'écran actuel : rien de mort, rien d'inventé.
 *
 * `alias` : l'entrée mène à un écran qu'une autre entrée « possède » ; elle n'est jamais surlignée à sa place.
 * `provisoire` : entrée gardée le temps que son écran de destination existe (E109), à retirer ensuite.
 */
import {
    AudioLines,
    BellRing,
    Bot,
    ChartLine,
    Code,
    Database,
    Folder,
    Inbox,
    KeyRound,
    LayoutGrid,
    Library,
    type LucideIcon,
    Megaphone,
    MessagesSquare,
    Phone,
    Plug,
    Settings2,
    Sparkles,
    Store,
    Wrench,
} from "lucide-react";

import type { Texte } from "@/components/mark/langue/langue";

export type Espace = "labo" | "client";

export type EntreeMenu = {
    id: string;
    titre: Texte;
    icone: LucideIcon;
    /** Sa place dans la refonte ; `base` vaut `/labo` ou `/clients/<org>`. */
    adresse: (base: string) => string;
    /** L'écran existant qui porte sa fonction aujourd'hui. */
    actuelle: string;
    alias?: boolean;
    provisoire?: boolean;
};

export type GroupeMenu = { id: string; label?: Texte; entrees: EntreeMenu[] };

const e = (
    id: string,
    titre: Texte,
    icone: LucideIcon,
    suite: string,
    actuelle: string,
    options: Partial<Pick<EntreeMenu, "alias" | "provisoire">> = {},
): EntreeMenu => ({ id, titre, icone, adresse: (base) => (suite ? `${base}/${suite}` : base), actuelle, ...options });

const BUILDER = e("builder", { en: "Builder AI", fr: "Builder IA" }, Sparkles, "builder", "/workflow", { alias: true });
const CHAT = e("chat", { en: "Chat", fr: "Chat" }, MessagesSquare, "chat", "/workflow", { alias: true });
const A_AMELIORER = e("a-ameliorer", { en: "To improve", fr: "À améliorer" }, Inbox, "a-ameliorer", "/a-trier");
const AGENTS = e("agents", { en: "Agents", fr: "Agents" }, Bot, "agents", "/workflow");
const BIBLIOTHEQUE = e("bibliotheque", { en: "Library", fr: "Bibliothèque" }, Library, "bibliotheque", "/bibliotheque");
const OUTILS = e("outils", { en: "Tools", fr: "Outils" }, Wrench, "outils", "/tools");
const CONNAISSANCES = e("connaissances", { en: "Knowledge", fr: "Connaissances" }, Folder, "connaissances", "/files");
const ENTREPRISE = e("entreprise", { en: "Company", fr: "Entreprise" }, Store, "entreprise", "/settings", { alias: true });
const CAMPAGNES = e("campagnes", { en: "Campaigns", fr: "Campagnes" }, Megaphone, "campagnes", "/campaigns");
const BASE = e("base", { en: "Data and automations", fr: "Base et automatisations" }, Database, "base", "/settings", { alias: true });
const INTEGRATIONS = e("integrations", { en: "Integrations", fr: "Intégrations" }, Plug, "connecteurs", "/settings", { alias: true });
const MODELES = e("modeles", { en: "Models and keys", fr: "Modèles et clés" }, KeyRound, "modeles", "/model-configurations");
const CLES = e("cles", { en: "Keys", fr: "Clés" }, KeyRound, "cles", "/cles", { provisoire: true });
const TELEPHONIE = e("telephonie", { en: "Telephony", fr: "Téléphonie" }, Phone, "telephonie", "/telephony-configurations");
const QUALITE = e("qualite", { en: "Quality", fr: "Qualité" }, ChartLine, "qualite", "/reports");
const CONVERSATIONS = e("conversations", { en: "Conversations", fr: "Conversations" }, MessagesSquare, "conversations", "/usage");
const REGLAGES = e("reglages", { en: "Settings", fr: "Réglages" }, Settings2, "reglages", "/settings");
const ALERTES = e("alertes", { en: "Alerts", fr: "Alertes" }, BellRing, "a-ameliorer", "/alertes", { provisoire: true });
const SONS = e("sons", { en: "Sounds", fr: "Sons" }, AudioLines, "sons", "/recordings", { provisoire: true });
const DEVELOPPEURS = e("developpeurs", { en: "Developers", fr: "Développeurs" }, Code, "developpeurs", "/api-keys", { provisoire: true });

/** Espace Labo (E3, E31) : toutes les rubriques d'un client, plus l'atelier. */
export const MENU_LABO: GroupeMenu[] = [
    {
        id: "haut",
        entrees: [{ ...BUILDER, adresse: () => "/labo" }, { ...CHAT, adresse: () => "/labo/builder" }, A_AMELIORER],
    },
    {
        id: "construire",
        label: { en: "BUILD", fr: "CONSTRUIRE" },
        entrees: [AGENTS, BIBLIOTHEQUE, OUTILS, CONNAISSANCES, ENTREPRISE, CAMPAGNES],
    },
    { id: "brancher", label: { en: "CONNECT", fr: "BRANCHER" }, entrees: [BASE, INTEGRATIONS, MODELES, CLES, TELEPHONIE] },
    { id: "mesurer", label: { en: "MEASURE", fr: "MESURER" }, entrees: [QUALITE, CONVERSATIONS, ALERTES] },
    { id: "regler", label: { en: "SETTINGS", fr: "RÉGLER" }, entrees: [REGLAGES, SONS, DEVELOPPEURS] },
];

/** Espace Client (E3, E57) : le même ensemble, sans l'atelier, avec l'accueil du client. */
export const MENU_CLIENT: GroupeMenu[] = [
    {
        id: "haut",
        entrees: [
            e("accueil", { en: "Home", fr: "Accueil" }, LayoutGrid, "", "/workflow", { alias: true }),
            BUILDER,
            CHAT,
            A_AMELIORER,
        ],
    },
    {
        id: "agents",
        label: { en: "AGENTS", fr: "AGENTS" },
        entrees: [AGENTS, CONVERSATIONS, ALERTES, CAMPAGNES, CONNAISSANCES, ENTREPRISE, OUTILS],
    },
    { id: "brancher", label: { en: "CONNECT", fr: "BRANCHER" }, entrees: [BASE, INTEGRATIONS, MODELES, CLES, TELEPHONIE] },
    {
        id: "organisation",
        label: { en: "ORGANIZATION", fr: "ORGANISATION" },
        entrees: [REGLAGES, SONS, DEVELOPPEURS],
    },
];

/** L'espace d'une adresse : `/clients/<org>/...` est un client, tout le reste est le Labo. */
export function espaceDe(pathname: string): { espace: Espace; base: string; org: string | null } {
    const m = pathname.match(/^\/clients\/([^/]+)/);
    if (m) return { espace: "client", base: `/clients/${m[1]}`, org: decodeURIComponent(m[1]) };
    return { espace: "labo", base: "/labo", org: null };
}

export const menuDe = (espace: Espace): GroupeMenu[] => (espace === "client" ? MENU_CLIENT : MENU_LABO);

export const toutesLesEntrees = (groupes: GroupeMenu[]): EntreeMenu[] => groupes.flatMap((g) => g.entrees);

const sousChemin = (pathname: string, chemin: string) => pathname === chemin || pathname.startsWith(`${chemin}/`);

/**
 * L'entrée surlignée : celle dont l'adresse (nouvelle ou actuelle) est la plus longue parmi celles qui
 * contiennent l'adresse courante. Une entrée `alias` n'est jamais surlignée à la place de celle qui possède l'écran.
 */
export function entreeActive(groupes: GroupeMenu[], pathname: string, base: string): EntreeMenu | null {
    let meilleure: { entree: EntreeMenu; longueur: number } | null = null;
    for (const entree of toutesLesEntrees(groupes)) {
        const cibles = [entree.adresse(base), ...(entree.alias ? [] : [entree.actuelle])];
        for (const cible of cibles) {
            // L'accueil (`/labo`, `/clients/<org>`) ne couvre pas tout ce qui est dessous.
            const exacte = cible === base;
            if (exacte ? pathname === cible : sousChemin(pathname, cible)) {
                if (!meilleure || cible.length > meilleure.longueur) meilleure = { entree, longueur: cible.length };
            }
        }
    }
    return meilleure?.entree ?? null;
}

/** Le lien d'une entrée : l'écran actuel tant que la nouvelle adresse n'est pas construite (sous-lot 4). */
export const lienDe = (entree: EntreeMenu) => entree.actuelle;

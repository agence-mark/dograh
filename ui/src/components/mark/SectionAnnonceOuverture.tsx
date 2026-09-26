"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet,
  saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut,
} from "@/client/sdk.gen";
import type { ReglagesAnnonceOuverture } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";
import { useAuth } from "@/lib/auth";

import { type Texte, useLangue } from "./langue/langue";

/**
 * [.mark] What the agents say at pick-up when the business is closed, and the
 * state forced by hand (chantier reglages-annonce-ouverture, 18/09/2026).
 *
 * Why this card exists: the two sentences were written IN THE CODE. A setting
 * that changes what a caller hears is seen and changed on screen.
 *
 * ⚠️ These settings belong to the ORGANIZATION: they are true for the whole
 * company. The opening HOURS stay on each agent, because they describe a place.
 * Which is why a forced state closes every agent of the organization, and the
 * card says so: to close ONE site, the hours of that agent take a dated
 * exception (« 24/12/2026 : fermé »), which the format already allows.
 *
 * Split in three (chantier reorganisation-ecran-reglages, step 5): the state
 * and its save (`useAnnonceOuverture`), the fields (`ChampsAnnonceOuverture`),
 * and the card itself. The « Business » theme of the Platform Settings page
 * uses the first two with its own button: same read, same PUT, same guard.
 */

export const ETAT_CALCULE = "";

/** The states that can be forced, in the order they are offered. */
const ETATS: Array<{ valeur: string; libelle: Texte }> = [
  { valeur: "FERME", libelle: { en: "Closed", fr: "fermé" } },
  { valeur: "PAUSE", libelle: { en: "On a break", fr: "en pause" } },
  { valeur: "OUVERT", libelle: { en: "Open", fr: "ouvert" } },
  { valeur: "SUR_RENDEZ_VOUS", libelle: { en: "By appointment only", fr: "sur rendez-vous" } },
];

/** What the preview puts in « {reouverture} » -- an EXAMPLE, the server words the real one. */
const REOUVERTURE_EXEMPLE = "demain à 10 heures";

const VIDE: ReglagesAnnonceOuverture = {
  annonce_fermeture: "",
  annonce_pause: "",
  etat_force: null,
  etat_force_jusqu_a: null,
};

export const ANNONCE_ENREGISTREE: Texte = { en: "Announcement settings saved", fr: "Annonce enregistrée" };

/**
 * Put a sentence into the words the greeting will say.
 *
 * ⚠️ The same two rules as `rendre_annonce` on the server: what is in brackets
 * is said only when the reopening is known, and « {reouverture} » is replaced
 * by it. This copy is for the PREVIEW only -- what a caller hears is always
 * built by the server.
 */
export function rendreAnnonce(modele: string, reouverture: string): string {
  const texte = (modele ?? "").trim();
  if (!texte) return "";
  let sortie: string;
  if (reouverture) {
    sortie = texte.replace(/[[\]]/g, "");
  } else {
    // An unclosed « [ » is optional to the end, exactly like on the server.
    let profondeur = 0;
    sortie = "";
    for (const caractere of texte) {
      if (caractere === "[") profondeur += 1;
      else if (caractere === "]") profondeur = Math.max(0, profondeur - 1);
      else if (profondeur === 0) sortie += caractere;
    }
  }
  return sortie.split("{reouverture}").join(reouverture).replace(/\s+/g, " ").trim();
}

/** « 2026-12-24T10:00:00 » -> « 2026-12-24T10:00 », what the date field reads. */
function versChamp(valeur: string | null | undefined): string {
  return valeur ? valeur.slice(0, 16) : "";
}

const RIEN_ANNONCE: Texte = { en: "nothing is announced", fr: "rien n'est annoncé" };

function Apercu({ modele, titre }: { modele: string; titre: Texte }) {
  const { t } = useLangue();
  const avec = rendreAnnonce(modele, REOUVERTURE_EXEMPLE);
  const sans = rendreAnnonce(modele, "");
  return (
    <div className="rounded-md border bg-muted/40 p-3 text-xs">
      <p className="font-medium">{t(titre)}</p>
      <p className="mt-1 text-muted-foreground">
        {t({ en: "Reopening known (example):", fr: "Réouverture connue (exemple) :" })}{" "}
        <span className="text-foreground">{avec || t(RIEN_ANNONCE)}</span>
      </p>
      <p className="text-muted-foreground">
        {t({ en: "Reopening unknown:", fr: "Réouverture inconnue :" })}{" "}
        <span className="text-foreground">{sans || t(RIEN_ANNONCE)}</span>
      </p>
    </div>
  );
}

/** The state of the card: what is saved, what is being typed, how to save it. */
export function useAnnonceOuverture() {
  const [reglages, setReglages] = useState<ReglagesAnnonceOuverture>(VIDE);
  const [enregistre, setEnregistre] = useState<ReglagesAnnonceOuverture>(VIDE);
  const [chargement, setChargement] = useState(true);
  const [enregistrement, setEnregistrement] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [lu, setLu] = useState(false);
  const { user, loading: authLoading } = useAuth();
  const dejaLu = useRef(false);

  // ⛔ Convention of the repository: the token is attached only once auth is
  // loaded. Reading before that sends an unauthenticated request that fails in
  // silence, and the screen would show the defaults.
  useEffect(() => {
    if (authLoading || !user || dejaLu.current) return;
    dejaLu.current = true;
    void charger();
  }, [authLoading, user]);

  function reessayer() {
    // ⛔ Without this, a failed read locks the card for good: saving stays
    // asleep (which is right, it would overwrite) but the only way out is to
    // reload the page (independent review of 2026-09-18, Mineur 6).
    dejaLu.current = true;
    void charger();
  }

  async function charger() {
    setChargement(true);
    try {
      const reponse = await getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet();
      if (reponse.error || !reponse.data) {
        // ⛔ Saving REPLACES the settings whole: until what is saved has been
        // read, nothing may overwrite it.
        setLu(false);
        setErreur(detailFromError(reponse.error, "Failed to load the announcement settings"));
        return;
      }
      setReglages(reponse.data);
      setEnregistre(reponse.data);
      setLu(true);
      setErreur(null);
    } catch {
      setLu(false);
      setErreur("Failed to load the announcement settings");
    } finally {
      setChargement(false);
    }
  }

  /** True when the server took it. */
  async function enregistrer(succes: string): Promise<boolean> {
    setEnregistrement(true);
    setErreur(null);
    try {
      const reponse = await saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut({
        body: reglages,
      });
      if (reponse.error) {
        // The server's own message: an unclosed bracket, a placeholder that
        // does not exist, a date without a forced state.
        setErreur(detailFromError(reponse.error, "Failed to save the announcement settings"));
        return false;
      }
      setReglages(reponse.data ?? reglages);
      setEnregistre(reponse.data ?? reglages);
      toast.success(succes);
      return true;
    } catch {
      setErreur("Failed to save the announcement settings");
      return false;
    } finally {
      setEnregistrement(false);
    }
  }

  function modifier(champs: Partial<ReglagesAnnonceOuverture>) {
    setReglages((actuel) => ({ ...actuel, ...champs }));
    setErreur(null);
  }

  return { reglages, enregistre, modifier, chargement, enregistrement, erreur, lu, enregistrer, reessayer };
}

export type EtatAnnonceOuverture = ReturnType<typeof useAnnonceOuverture>;

/** The two sentences and the forced state, without any button. */
export function ChampsAnnonceOuverture({ annonce }: { annonce: EtatAnnonceOuverture }) {
  const { t } = useLangue();
  const { reglages, modifier } = annonce;
  const force = reglages.etat_force ?? null;
  const parle = force === "FERME" || force === "PAUSE";

  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">
        {t({
          en: "Said at pick-up, before the greeting, when the business is not reachable. An open business says nothing extra.",
          fr: "Dite au décroché, avant l'accueil, quand l'entreprise n'est pas joignable. Une entreprise ouverte ne dit rien de plus.",
        })}{" "}
        <code className="rounded bg-muted px-1 text-xs">{"{reouverture}"}</code>{" "}
        {t({ en: "is the reopening the agent announces, and what is inside", fr: "est la réouverture que l'agent annonce, et ce qui est entre" })}{" "}
        <code className="rounded bg-muted px-1 text-xs">[ ]</code>{" "}
        {t({
          en: "is said only when that reopening is known. An empty sentence announces nothing.",
          fr: "n'est dit que si cette réouverture est connue. Une phrase vide n'annonce rien.",
        })}
      </p>

      <p className="text-xs text-muted-foreground">
        {t({
          en: "Nothing is ever announced on an outbound call: we placed it, so telling the person we are closed would make no sense. The agent is still told the state.",
          fr: "Rien n'est jamais annoncé sur un appel sortant : c'est nous qui appelons, dire que nous sommes fermés n'aurait pas de sens. L'agent reçoit quand même l'état.",
        })}
      </p>

      <div className="space-y-2" id="reglage-annonce_fermeture" data-reglage="annonce_fermeture">
        <Label htmlFor="annonce_fermeture" className="text-xs">
          {t({ en: "When the business is closed", fr: "Quand l'entreprise est fermée" })}
        </Label>
        <Textarea
          id="annonce_fermeture"
          rows={2}
          maxLength={300}
          value={reglages.annonce_fermeture ?? ""}
          onChange={(e) => modifier({ annonce_fermeture: e.target.value })}
        />
        <Apercu modele={reglages.annonce_fermeture ?? ""} titre={{ en: "Closed, as it will be said", fr: "Fermé, tel que ce sera dit" }} />
      </div>

      <div className="space-y-2" id="reglage-annonce_pause" data-reglage="annonce_pause">
        <Label htmlFor="annonce_pause" className="text-xs">
          {t({ en: "When the business is on a break", fr: "Quand l'entreprise est en pause" })}
        </Label>
        <p className="text-xs text-muted-foreground">
          {t({
            en: "A break means already open today and reopening today, not lunch.",
            fr: "Une pause veut dire déjà ouvert aujourd'hui et réouverture aujourd'hui, pas le déjeuner.",
          })}
        </p>
        <Textarea
          id="annonce_pause"
          rows={2}
          maxLength={300}
          value={reglages.annonce_pause ?? ""}
          onChange={(e) => modifier({ annonce_pause: e.target.value })}
        />
        <Apercu modele={reglages.annonce_pause ?? ""} titre={{ en: "On a break, as it will be said", fr: "En pause, tel que ce sera dit" }} />
      </div>

      <div className="space-y-2 border-t pt-4" id="reglage-etat_force" data-reglage="etat_force">
        <Label htmlFor="etat_force" className="text-xs">
          {t({ en: "State of the business", fr: "État de l'entreprise" })}
        </Label>
        <select
          id="etat_force"
          aria-label={t({ en: "State of the business", fr: "État de l'entreprise" })}
          className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
          value={force ?? ETAT_CALCULE}
          onChange={(e) =>
            modifier(
              e.target.value === ETAT_CALCULE
                ? // Back to « computed »: the end date goes with it. It means
                  // nothing on its own, and the server refuses it alone.
                  { etat_force: null, etat_force_jusqu_a: null }
                : { etat_force: e.target.value as ReglagesAnnonceOuverture["etat_force"] },
            )
          }
        >
          <option value={ETAT_CALCULE}>
            {t({ en: "Computed from each agent's opening hours", fr: "Calculé depuis les horaires de chaque agent" })}
          </option>
          {ETATS.map((etat) => (
            <option key={etat.valeur} value={etat.valeur}>
              {t({ en: "Forced:", fr: "Forcé :" })} {t(etat.libelle)}
            </option>
          ))}
        </select>

        {force !== null && (
          <div className="space-y-2" id="reglage-etat_force_jusqu_a" data-reglage="etat_force_jusqu_a">
            <Label htmlFor="etat_force_jusqu_a" className="text-xs">
              {t({ en: "Until (Paris time)", fr: "Jusqu'au (heure de Paris)" })}
            </Label>
            <Input
              id="etat_force_jusqu_a"
              type="datetime-local"
              value={versChamp(reglages.etat_force_jusqu_a)}
              onChange={(e) => modifier({ etat_force_jusqu_a: e.target.value || null })}
            />
            <p className="text-xs text-muted-foreground">
              {t({
                en: "This moment lifts the forced state by itself: after it the agents go back to their opening hours, with nobody doing anything.",
                fr: "Ce moment lève l'état forcé tout seul : après lui, les agents reviennent à leurs horaires, sans que personne n'intervienne.",
              })}{" "}
              {parle
                ? t({
                    en: "What the agent announces as the reopening is the first opening of its own hours at or after this moment, so « until 02/01 00:00 » is said as « we reopen on the 2nd at 10 » — or later, if that day is closed. An agent with no opening hours announces this moment itself.",
                    fr: "La réouverture annoncée est la première ouverture des horaires de l'agent à partir de ce moment : « jusqu'au 02/01 00:00 » se dit « nous rouvrons le 2 à 10 heures », ou plus tard si ce jour est fermé. Un agent sans horaires annonce ce moment lui-même.",
                  })
                : ""}{" "}
              {parle
                ? t({
                    en: "Left empty, the forced state holds until someone comes back here, and no reopening is announced.",
                    fr: "Vide, l'état forcé tient jusqu'à ce que quelqu'un revienne ici, et aucune réouverture n'est annoncée.",
                  })
                : t({
                    en: "Left empty, the forced state holds until someone comes back here.",
                    fr: "Vide, l'état forcé tient jusqu'à ce que quelqu'un revienne ici.",
                  })}
            </p>
            {force === "PAUSE" && (
              <p className="text-xs text-muted-foreground">
                {t({
                  en: "A break means « open earlier today, back later today »: forcing it for several days says something the caller will find odd. For a longer closing, force Closed.",
                  fr: "Une pause veut dire « ouvert plus tôt aujourd'hui, de retour plus tard aujourd'hui » : la forcer plusieurs jours dit quelque chose d'étrange à l'appelant. Pour une fermeture plus longue, forcez Fermé.",
                })}
              </p>
            )}
            <p className="text-xs text-destructive">
              {t({
                en: "A forced state applies to EVERY agent of this organization. To close one site only, add a dated exception in that agent's opening hours (",
                fr: "Un état forcé s'applique à TOUS les agents de l'organisation. Pour fermer un seul site, ajoutez une exception datée dans les horaires de cet agent (",
              })}
              <code>24/12/2026 : fermé</code>).
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

/** The server's refusal, and the lock while the saved settings are unread, with « Retry ». */
export function EtatLectureAnnonce({ annonce }: { annonce: EtatAnnonceOuverture }) {
  const { t } = useLangue();
  return (
    <>
      {annonce.erreur && (
        <p role="alert" className="text-xs text-destructive">
          {annonce.erreur}
        </p>
      )}
      {!annonce.lu && (
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs text-destructive">
            {t({
              en: "Nothing was changed. Saving is disabled until the saved settings can be read.",
              fr: "Rien n'a été modifié. L'enregistrement de l'annonce est bloqué tant que les réglages enregistrés ne peuvent pas être lus.",
            })}
          </p>
          <Button type="button" variant="outline" onClick={annonce.reessayer}>
            {t({ en: "Retry", fr: "Réessayer" })}
          </Button>
        </div>
      )}
    </>
  );
}

/** The card on its own, with its button. */
export function SectionAnnonceOuverture() {
  const { t } = useLangue();
  const annonce = useAnnonceOuverture();

  if (annonce.chargement) {
    return <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>;
  }

  return (
    <div className="space-y-5">
      <ChampsAnnonceOuverture annonce={annonce} />
      <EtatLectureAnnonce annonce={annonce} />
      <Button
        type="button"
        disabled={annonce.enregistrement || !annonce.lu}
        onClick={() => void annonce.enregistrer(t(ANNONCE_ENREGISTREE))}
      >
        {annonce.enregistrement
          ? t({ en: "Saving…", fr: "Enregistrement…" })
          : t({ en: "Save announcement settings", fr: "Enregistrer l'annonce" })}
      </Button>
    </div>
  );
}

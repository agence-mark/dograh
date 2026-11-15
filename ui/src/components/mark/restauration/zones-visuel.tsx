"use client";

// Zones de livraison (Evan, 14/11) : un cercle par zone, à code couleur, étiqueté de son prix, de son minimum ou des deux ;
// dans la liste des communes, un badge de la même couleur et du même texte. Aucun point ni nom de commune dans les cercles.
// ⚠️ Fichier IDENTIQUE dans le fork et le portail (aucun import propre à l'un des deux) : le modifier des deux côtés.

type Traduire = (fr: string, en: string) => string;

/** Couleur d'une zone d'après son rang (0 = la plus proche), par les jetons `--zone-1` à `--zone-5`. */
export const couleurZone = (rang: number) => `var(--zone-${(rang % 5) + 1})`;

const euros = (c: number) => `${(c / 100).toFixed(c % 100 ? 2 : 0).replace(".", ",")} €`;

/** Le texte d'une zone : son prix (« Gratuit » à 0), son minimum, ou les deux, selon ce qui est réglé. */
export function texteZone(z: { frais_centimes: number | null; minimum_centimes: number | null }, t: Traduire) {
  const parts: string[] = [];
  if (z.frais_centimes !== null) parts.push(z.frais_centimes === 0 ? t("Gratuit", "Free") : euros(z.frais_centimes));
  if (z.minimum_centimes) parts.push(`min ${euros(z.minimum_centimes)}`);
  return parts.join(" · ") || t("Sans condition", "No condition");
}

/** Badge d'une zone : fond doux et pastille de sa couleur, texte à l'encre. Cliquable si `onClick`. */
export function BadgeZone({ rang, texte, onClick, titre }: { rang: number | null; texte: string; onClick?: () => void; titre?: string }) {
  const c = rang === null ? "var(--muted-foreground)" : couleurZone(rang);
  const classe = "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium tabular-nums text-foreground";
  const style = { background: `color-mix(in srgb, ${c} 12%, transparent)` };
  const contenu = <><span className="size-2 shrink-0 rounded-full" style={{ background: c }} aria-hidden />{texte}</>;
  return onClick
    ? <button type="button" onClick={(e) => { e.stopPropagation(); onClick(); }} title={titre} className={`${classe} cursor-pointer hover:font-semibold focus-visible:outline-2 focus-visible:outline-ring`} style={style}>{contenu}</button>
    : <span className={classe} style={style} title={titre}>{contenu}</span>;
}

/** Le schéma : les zones seules, du plus grand cercle au plus petit, le restaurant en point discret. Il ne bouge que si une
 *  zone change ; le curseur de recherche n'y touche pas (Evan, 14/11 : l'échelle qui suivait le curseur n'avait pas de logique). */
export function SchemaZones({ cercles, choisi, libelle }: {
  cercles: { cle: string; km: number; rang: number; texte: string }[];
  choisi?: string | null;
  libelle: string;
}) {
  const T = 360, c = T / 2;
  const max = Math.max(...cercles.map((z) => z.km), 1) * 1.04;
  const px = (km: number) => (km / max) * (c - 14);
  const tries = [...cercles].sort((a, b) => b.km - a.km);
  return (
    <div className="relative mx-auto w-full max-w-[360px]">
      <svg viewBox={`0 0 ${T} ${T}`} className="w-full" role="img" aria-label={libelle}>
        {tries.map((z) => (
          <circle key={z.cle} cx={c} cy={c} r={px(z.km)} fill={couleurZone(z.rang)} fillOpacity={choisi === z.cle ? 0.16 : 0.07}
            stroke={couleurZone(z.rang)} strokeOpacity={0.55} strokeWidth={choisi === z.cle ? 2 : 1.25} />
        ))}
        <circle cx={c} cy={c} r={4} fill="var(--foreground)" />
      </svg>
      {tries.map((z) => (
        <span key={z.cle} className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2" style={{ left: "50%", top: `${((c - px(z.km)) / T) * 100}%` }}>
          <span className="inline-flex rounded-full bg-background shadow-[0_0_0_1px_var(--border)]"><BadgeZone rang={z.rang} texte={z.texte} /></span>
        </span>
      ))}
    </div>
  );
}

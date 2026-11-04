/**
 * [.mark] Partie 3, lot 15 (SE-25, L-5) : un numéro de téléphone s'AFFICHE à la française, le stockage ne change pas.
 *
 * « +33344000002 » ou « 0344000002 » s'affiche « 03 44 00 00 02 » ; un numéro qui n'est pas français (ou qui ne tient pas
 * dans ce motif) s'affiche tel qu'il est écrit : on n'invente jamais un découpage. La valeur enregistrée reste celle saisie.
 */
export function formaterNumero(numero: string | null | undefined): string {
    const brut = (numero ?? "").trim();
    if (!brut) return "";
    const chiffres = brut.replace(/[\s.\-()]/g, "");
    const national = /^\+33[1-9]\d{8}$/.test(chiffres) ? `0${chiffres.slice(3)}` : /^0[1-9]\d{8}$/.test(chiffres) ? chiffres : null;
    return national ? national.replace(/(\d{2})(?=\d)/g, "$1 ").trim() : brut;
}

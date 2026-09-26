/**
 * [.mark] Finds the texts of our screens written in ONE language only
 * (chantier reorganisation-ecran-reglages, step 7, convention T2).
 *
 * Every text a person reads on our screens (`components/mark/`) is written in
 * English and French, as a `Texte` ({ en, fr }) shown by `t()`. This reads the
 * source with the TypeScript parser and reports what a person would read that
 * does not go through a `Texte`:
 *
 *   - text written directly between JSX tags (`<p>Save</p>`);
 *   - a string given to an attribute a person reads (`placeholder`, `title`,
 *     `aria-label`, `alt`) or to a toast (`toast.success("Saved")`).
 *
 * Not reported, on purpose (T4: never translated):
 *   - text inside `<code>`: a technical name, a placeholder of the prompts, an
 *     example of the format;
 *   - a string made only of what no language changes: digits, punctuation,
 *     symbols, technical names written like `{{adresse_etablissement}}`, or a
 *     single lowercase identifier (`first_name`), the example of a code.
 *
 * Its limit, said plainly: a string built in a variable and shown later is not
 * followed. The rule for those is the `Texte` type itself.
 */
import ts from "typescript";

export interface TexteUneLangue {
    fichier: string;
    /** The top-level declaration it sits in (a component), for the exceptions. */
    composant: string | null;
    ligne: number;
    texte: string;
}

const ATTRIBUTS_LUS = new Set(["placeholder", "title", "aria-label", "alt"]);

/** A string a person reads: at least two letters in a row, outside a technical name. */
const estUnTexte = (brut: string): boolean => {
    // One identifier alone (`first_name`, `qualified`): an example of a code.
    if (/^[a-z][a-z0-9_]*$/.test(brut.trim())) return false;
    const sansTechnique = brut
        .replace(/\{\{[^}]*\}\}/g, "")
        .replace(/\{[a-z_]+\}/g, "")
        .replace(/https?:\/\/\S+/g, "");
    return /\p{L}{2,}/u.test(sansTechnique);
};

const dansUnCode = (noeud: ts.Node): boolean => {
    for (let parent = noeud.parent; parent; parent = parent.parent) {
        if (ts.isJsxElement(parent) && parent.openingElement.tagName.getText() === "code") return true;
    }
    return false;
};

export const textesUneLangue = (fichier: string, source: string): TexteUneLangue[] => {
    const arbre = ts.createSourceFile(fichier, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const trouves: TexteUneLangue[] = [];
    const composantDe = (noeud: ts.Node): string | null => {
        let haut = noeud;
        while (haut.parent && haut.parent !== arbre) haut = haut.parent;
        if (ts.isFunctionDeclaration(haut)) return haut.name?.text ?? null;
        if (ts.isVariableStatement(haut)) return haut.declarationList.declarations[0]?.name.getText() ?? null;
        return null;
    };
    const noter = (noeud: ts.Node, texte: string) =>
        trouves.push({
            fichier,
            composant: composantDe(noeud),
            ligne: arbre.getLineAndCharacterOfPosition(noeud.getStart()).line + 1,
            texte: texte.replace(/\s+/g, " ").trim(),
        });

    /** A string shown as it is: `{ok ? "Saved" : "Failed"}` between tags, or in a read attribute. */
    const afficheeTelleQuelle = (chaine: ts.StringLiteralLike): boolean => {
        let noeud: ts.Node = chaine;
        while (
            ts.isParenthesizedExpression(noeud.parent)
            || (ts.isConditionalExpression(noeud.parent) && noeud.parent.condition !== noeud)
            || (ts.isBinaryExpression(noeud.parent)
                && [ts.SyntaxKind.BarBarToken, ts.SyntaxKind.QuestionQuestionToken, ts.SyntaxKind.AmpersandAmpersandToken].includes(
                    noeud.parent.operatorToken.kind,
                )
                && noeud.parent.right === noeud)
        ) {
            noeud = noeud.parent;
        }
        const expression = noeud.parent;
        if (!expression || !ts.isJsxExpression(expression) || noeud === chaine) return false;
        const porteur = expression.parent;
        if (ts.isJsxElement(porteur) || ts.isJsxFragment(porteur)) return !dansUnCode(expression);
        return ts.isJsxAttribute(porteur) && ATTRIBUTS_LUS.has(porteur.name.getText());
    };

    const visiter = (noeud: ts.Node) => {
        if (ts.isStringLiteralLike(noeud) && estUnTexte(noeud.text) && afficheeTelleQuelle(noeud)) {
            noter(noeud, noeud.text);
        } else if (ts.isJsxText(noeud) && estUnTexte(noeud.text) && !dansUnCode(noeud)) {
            noter(noeud, noeud.text);
        } else if (ts.isJsxAttribute(noeud) && ATTRIBUTS_LUS.has(noeud.name.getText())) {
            const valeur = noeud.initializer;
            const chaine =
                valeur && ts.isStringLiteral(valeur)
                    ? valeur
                    : valeur && ts.isJsxExpression(valeur) && valeur.expression && ts.isStringLiteralLike(valeur.expression)
                      ? valeur.expression
                      : null;
            if (chaine && estUnTexte(chaine.text)) noter(noeud, chaine.text);
        } else if (
            ts.isCallExpression(noeud)
            && /^toast\.(success|error|info|warning|message)$/.test(noeud.expression.getText())
            && noeud.arguments[0]
            && ts.isStringLiteralLike(noeud.arguments[0])
            && estUnTexte(noeud.arguments[0].text)
        ) {
            noter(noeud, noeud.arguments[0].text);
        }
        ts.forEachChild(noeud, visiter);
    };
    visiter(arbre);
    return trouves;
};

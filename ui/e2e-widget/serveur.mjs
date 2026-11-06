// Page d'essai du widget + fausse API (reponses enregistrees). Servi en local, jamais expose.
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { dirname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ici = dirname(fileURLToPath(import.meta.url));
const publicDir = join(ici, '..', 'public');
const PORT = Number(process.env.PORT || 4777);
const journal = [];

const TYPES = { '.js': 'text/javascript', '.html': 'text/html; charset=utf-8', '.woff2': 'font/woff2', '.json': 'application/json' };
const json = (res, corps, statut = 200) => {
  res.writeHead(statut, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(corps));
};

const CONFIG = (token) => ({
  actif: true, token, widget_type: 'voice', apparence: { declenchement: 'delai', delai_s: 1 }, couleurs: {},
  turn_enabled: false, force_turn_relay: false,
});
const TOUR = { id: 't1', status: 'completed', user_message: null, assistant_message: { text: 'Bonjour, je vous écoute.' } };

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  let corps = '';
  for await (const morceau of req) corps += morceau;
  const donnees = corps ? JSON.parse(corps) : null;

  if (url.pathname === '/__journal') return json(res, journal);
  if (url.pathname === '/__reset') { journal.length = 0; return json(res, { ok: true }); }

  if (url.pathname.startsWith('/api/v1/public/embed/')) {
    const reste = url.pathname.replace('/api/v1/public/embed/', '');
    journal.push({ methode: req.method, chemin: reste, corps: donnees });
    const site = reste.match(/^site\/([^/]+)\/config$/);
    if (site) return json(res, site[1] === 'site_AUCUN' ? { actif: false } : CONFIG('emb_ESSAI_' + site[1]));
    if (reste === 'evenement') return json(res, { ok: true });
    if (reste === 'init') {
      if (donnees.token.endsWith('site_PLAFOND')) return json(res, { detail: { code: 'monthly_cap_reached', message: 'x' } }, 403);
      return json(res, {
        session_token: 'emb_session_ESSAI', workflow_run_id: 1, config: { workflow_id: 1 }, widget_type: 'chat',
        chat_session: { revision: 1, state: 'running', is_completed: false, turns: [TOUR] },
      });
    }
    if (reste.endsWith('/messages')) {
      return json(res, {
        revision: 3, state: 'running', is_completed: false,
        turns: [TOUR, { id: 't2', status: 'completed', user_message: { text: donnees.text }, assistant_message: { text: 'C’est noté.' } }],
      });
    }
    if (reste.endsWith('/end')) return json(res, { revision: 4, state: 'completed', is_completed: true, turns: [] });
    if (reste.startsWith('avis/') || reste.startsWith('rappel/')) return json(res, { ok: true });
    return json(res, { detail: 'inconnu' }, 404);
  }

  const cible = url.pathname === '/essai'
    ? join(ici, 'pages', 'essai.html')
    : join(publicDir, normalize(url.pathname).replace(/^(\.\.[/\\])+/, ''));
  try {
    const contenu = await readFile(cible);
    res.writeHead(200, { 'Content-Type': TYPES[cible.slice(cible.lastIndexOf('.'))] || 'application/octet-stream' });
    res.end(contenu);
  } catch {
    res.writeHead(404);
    res.end();
  }
}).listen(PORT, '127.0.0.1');

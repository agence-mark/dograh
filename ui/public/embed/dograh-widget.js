/**
 * Widget .mark (U10 / lot S4) : l'assistant vocal posé sur le site d'un client.
 *
 * Un seul script par site :  <script async src=".../embed/dograh-widget.js?site={cle}&apiEndpoint=..."></script>
 * La page du client n'a rien d'autre à faire : l'agent qui sert la page (chemin le plus précis, sinon « tout le
 * site ») et toute l'apparence viennent du serveur, relus à chaque chargement de la page.
 *
 * Compatibilité : une adresse qui porte ?token= (script par jeton posé avant) charge le script historique
 * `dograh-widget-jeton.js`, inchangé, avec la même adresse et les mêmes attributs : il marche comme avant.
 *
 * Règles tenues ici (plan du portail v4, lot S4) :
 *  - rien n'est stocké avant le clic, ni cookie, ni stockage du navigateur (jamais) ; toutes les requêtes sont
 *    sans identifiants (credentials: omit) ;
 *  - polices hébergées chez nous (même origine que ce script), jamais celles d'un site tiers ;
 *  - le texte de la conversation ne s'affiche jamais, sauf le secours écrit (micro refusé ou voix impossible) ;
 *  - tous les textes lus par le visiteur viennent de l'apparence (18 textes), sauf les questions de l'avis liées
 *    aux colonnes de la table « avis » ;
 *  - repères data-zone sur chaque élément réglable : invisibles, ils servent à l'éditeur du portail, qui monte
 *    ce même widget dans son aperçu (window.MarkWidget.apercu), jamais une deuxième copie du rendu.
 */
(function () {
  'use strict';

  if (window.MarkWidget) return;

  // ---------------------------------------------------------------------------------------------------------------
  // Ce script, son origine, ses paramètres
  // ---------------------------------------------------------------------------------------------------------------
  var script = document.currentScript || document.querySelector('script[src*="dograh-widget.js"]');

  function parametresDe(el) {
    try {
      var url = new URL(el.src);
      return {
        url: url,
        site: url.searchParams.get('site'),
        token: url.searchParams.get('token'),
        apiEndpoint: url.searchParams.get('apiEndpoint'),
      };
    } catch (e) {
      return null;
    }
  }

  var P = script ? parametresDe(script) : null;

  /** L'ancien script par jeton : même adresse (autre fichier), mêmes attributs data-*. */
  function chargerLeScriptParJeton(el, url) {
    var cible = new URL(url.href);
    cible.pathname = cible.pathname.replace(/dograh-widget\.js$/, 'dograh-widget-jeton.js');
    var s = document.createElement('script');
    s.src = cible.href;
    s.async = true;
    for (var i = 0; i < el.attributes.length; i += 1) {
      var a = el.attributes[i];
      if (a.name.indexOf('data-') === 0) s.setAttribute(a.name, a.value);
    }
    (document.head || document.documentElement).appendChild(s);
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Textes fixes : uniquement ce que la table « avis » impose (D199) et les libellés d'accessibilité
  // ---------------------------------------------------------------------------------------------------------------
  var FIXE = {
    mention: 'Assistant IA conçu par .mark',
    obtenu_question: 'Avez-vous obtenu ce que vous cherchiez ?',
    obtenus: [['oui', 'Oui'], ['en_partie', 'En partie'], ['non', 'Non']],
    raisons_decu: ['Pas compris ma demande', 'Réponse fausse', 'Trop lent', 'Je voulais parler à quelqu’un'],
    raisons_content: ['Rapide', 'Réponses claires', 'Disponible à toute heure', 'Rendez-vous facile à prendre'],
    raisons_question_decu: 'Qu’est-ce qui n’a pas été ?',
    raisons_question_content: 'Qu’avez-vous le plus apprécié ?',
    case_rappel: 'Je souhaite qu’un conseiller me rappelle',
    case_publication: 'J’accepte que mon avis soit affiché',
    commentaire: 'Un commentaire ? (facultatif)',
    nom: 'Votre nom',
    contact: 'Téléphone ou mail',
    etoile: function (n) { return n + ' étoile' + (n > 1 ? 's' : ''); },
    couper_micro: 'Couper le micro',
    retablir_micro: 'Rétablir le micro',
    assistant: 'Assistant virtuel',
    indisponible: 'Le service est momentanément indisponible. Réessayez dans un instant.',
    confidentialite: 'Confidentialité',
    envoye: 'Envoyé.',
  };

  var COULEUR_MARK = '#1b5fb0';

  // ---------------------------------------------------------------------------------------------------------------
  // Couleurs
  // ---------------------------------------------------------------------------------------------------------------
  function rvb(hex) {
    var h = String(hex || '').replace('#', '');
    if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
    h = (h + '000000').slice(0, 6);
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function luminance(hex) {
    var c = rvb(hex).map(function (v) {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  }
  /** Texte noir ou blanc, le plus lisible sur ce fond (contraste). */
  function surFond(hex) {
    return luminance(hex) > 0.4 ? '#0f1c2e' : '#ffffff';
  }
  function eclaircir(hex, part) {
    var c = rvb(hex).map(function (v) { return Math.round(v + (255 - v) * part); });
    return '#' + c.map(function (v) { return v.toString(16).padStart(2, '0'); }).join('');
  }
  function sRgb(hex) {
    return rvb(hex).map(function (v) { return v / 255; });
  }

  // ---------------------------------------------------------------------------------------------------------------
  // L'orbe « nuage » (D200) : WebGL seul, repris de maquette/components/orbes/orbe-nuage.tsx (sans React).
  // Sans WebGL : un disque de la couleur, sans animation.
  // ---------------------------------------------------------------------------------------------------------------
  var VERTEX = 'attribute vec2 p; void main() { gl_Position = vec4(p, 0.0, 1.0); }';
  var FRAGMENT = [
    'precision highp float;',
    'uniform vec2 uRes; uniform float uTemps; uniform float uRayon; uniform vec3 uCouleur; uniform vec3 uClaire; uniform float uDouceur;',
    'float hash(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }',
    'float bruit(vec2 p) { vec2 i = floor(p), f = fract(p); vec2 u = f * f * (3.0 - 2.0 * f);',
    '  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y); }',
    'float fbm(vec2 p) { float v = 0.0, a = 0.5; mat2 m = mat2(0.8, 0.6, -0.6, 0.8);',
    '  for (int i = 0; i < 4; i++) { v += a * bruit(p); p = m * p * 2.02; a *= 0.5; } return v; }',
    'void main() {',
    '  vec2 p = (gl_FragCoord.xy * 2.0 - uRes) / min(uRes.x, uRes.y) * (1.0 + 1.6 * uDouceur);',
    '  float r = length(p);',
    '  float bord = 1.5 / min(uRes.x, uRes.y);',
    '  float adouci = uDouceur > 0.0 ? 0.03 * uRayon : bord;',
    '  float alpha = 1.0 - smoothstep(uRayon - adouci, uRayon + bord, r);',
    '  float halo = 0.0;',
    '  if (uDouceur > 0.0 && r > uRayon - adouci) { float d = (r - (uRayon - adouci)) / (uDouceur * uRayon); halo = 0.55 * exp(-d * d * 2.2); }',
    '  vec3 couleurHalo = mix(uCouleur, uClaire, 0.45);',
    '  if (alpha <= 0.0) { gl_FragColor = vec4(couleurHalo * halo, halo); return; }',
    '  vec2 q = p / uRayon * 0.95;',
    '  float t = uTemps * 0.09;',
    '  vec2 w = vec2(fbm(q + vec2(t, -0.6 * t)), fbm(q + vec2(-0.8 * t, t) + 4.3));',
    '  float n = fbm(q + 1.7 * w + vec2(0.0, 1.3 * t));',
    '  float haut = clamp(0.5 + 0.5 * p.y / uRayon, 0.0, 1.0);',
    '  vec3 ciel = mix(uCouleur, uClaire, 0.1 + 0.6 * haut);',
    '  float nuages = smoothstep(0.36, 0.8, n + 0.12 * haut);',
    '  vec3 c = mix(ciel, mix(uClaire, vec3(1.0), 0.8), nuages);',
    '  c *= 1.0 - 0.12 * smoothstep(0.55 * uRayon, uRayon, r);',
    '  float a = alpha + halo * (1.0 - alpha);',
    '  vec3 sortie = c * alpha + couleurHalo * halo * (1.0 - alpha);',
    '  gl_FragColor = vec4(sortie, a);',
    '}',
  ].join('\n');
  var HALO_ORBE = 0.04;

  function vers(a, b, k) { return a + (b - a) * k; }

  /**
   * Une orbe dans un élément. États : repos, ecoute, reflexion, parole. ``fige`` : immobile.
   * Rend { setEtat, setVolume, setFige, detruire, webgl }.
   */
  function creerOrbe(taille, couleur, options) {
    options = options || {};
    var etat = options.etat || 'repos';
    var volume = 0;
    var fige = !!options.fige;
    var hote = document.createElement('span');
    hote.setAttribute('data-zone', 'orbe');
    hote.style.cssText = 'display:inline-flex;width:' + taille + 'px;height:' + taille + 'px;border-radius:50%;flex:none';
    hote.setAttribute('role', 'img');
    hote.setAttribute('aria-hidden', 'true');
    var canvas = document.createElement('canvas');
    canvas.style.cssText = 'width:' + taille + 'px;height:' + taille + 'px;display:block';
    var gl = null;
    try {
      gl = canvas.getContext && canvas.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: true });
    } catch (e) {
      gl = null;
    }
    if (!gl) {
      // Repli sans WebGL : un disque de la couleur, sans animation.
      var disque = document.createElement('span');
      disque.style.cssText = 'display:block;width:100%;height:100%;border-radius:50%;background:' + couleur +
        ';box-shadow:0 6px 20px rgba(0,0,0,.14)';
      hote.appendChild(disque);
      return { element: hote, setEtat: function () {}, setVolume: function () {}, setFige: function () {}, detruire: function () {}, webgl: false };
    }
    hote.appendChild(canvas);
    function shader(type, src) {
      var s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      return s;
    }
    var prog = gl.createProgram();
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(prog);
    gl.useProgram(prog);
    var tampon = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, tampon);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var u = {};
    ['uRes', 'uTemps', 'uRayon', 'uCouleur', 'uClaire', 'uDouceur'].forEach(function (n) { u[n] = gl.getUniformLocation(prog, n); });
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    var cCiel = new Float32Array(sRgb(couleur));
    var cClaire = new Float32Array(sRgb(eclaircir(couleur, 0.55)));
    var calme = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    var temps = 0, vitesse = 0.5, rayon = 0.86, voix = 0, avant = performance.now(), image = 0, vivant = true;
    function tour(maintenant) {
      if (!vivant) return;
      var dt = Math.min((maintenant - avant) / 1000, 0.05);
      avant = maintenant;
      var s = maintenant / 1000;
      voix = vers(voix, etat === 'parole' ? volume : 0, 0.25);
      var cible =
        etat === 'repos' ? { v: 0.35, r: 0.84 + 0.006 * Math.sin(s * 0.9) } :
        etat === 'ecoute' ? { v: 0.7, r: 0.86 + 0.022 * Math.sin(s * 3.2) } :
        etat === 'reflexion' ? { v: 2.2, r: 0.83 + 0.008 * Math.sin(s * 6.0) } :
        { v: 1.1 + 1.6 * voix, r: 0.84 + 0.11 * voix };
      vitesse = fige ? 0 : vers(vitesse, calme ? 0.2 : cible.v, 0.06);
      rayon = vers(rayon, calme || fige ? 0.86 : cible.r, 0.18);
      temps += dt * vitesse;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      var l = Math.round(canvas.clientWidth * dpr) || taille, h = Math.round(canvas.clientHeight * dpr) || taille;
      if (canvas.width !== l || canvas.height !== h) { canvas.width = l; canvas.height = h; }
      gl.viewport(0, 0, l, h);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.uniform2f(u.uRes, l, h);
      gl.uniform1f(u.uTemps, temps);
      gl.uniform1f(u.uRayon, rayon);
      gl.uniform3fv(u.uCouleur, cCiel);
      gl.uniform3fv(u.uClaire, cClaire);
      gl.uniform1f(u.uDouceur, HALO_ORBE);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      image = requestAnimationFrame(tour);
    }
    image = requestAnimationFrame(tour);
    return {
      element: hote,
      setEtat: function (e) { etat = e; },
      setVolume: function (v) { volume = Math.max(0, Math.min(1, v)); },
      setFige: function (f) { fige = !!f; },
      detruire: function () { vivant = false; cancelAnimationFrame(image); },
      webgl: true,
    };
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Polices : hébergées chez nous (même origine que ce script). Jamais un site tiers.
  // ---------------------------------------------------------------------------------------------------------------
  var POLICES = {
    switzer: "'Mark Switzer', system-ui, -apple-system, 'Segoe UI', sans-serif",
    // Inter n'est pas hébergée (fichier non livré) : la police installée chez le visiteur si elle y est, sinon le système.
    inter: "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif",
    systeme: 'system-ui, -apple-system, "Segoe UI", sans-serif',
    site: 'inherit',
  };
  var policesChargees = false;
  function chargerLesPolices(origine) {
    if (policesChargees || typeof FontFace === 'undefined' || !document.fonts) return;
    policesChargees = true;
    [[400, 'Switzer-400'], [600, 'Switzer-600']].forEach(function (p) {
      try {
        var f = new FontFace('Mark Switzer', 'url(' + origine + '/embed/fonts/' + p[1] + '.woff2) format("woff2")', {
          weight: String(p[0]), display: 'swap',
        });
        f.load().then(function (ok) { document.fonts.add(ok); }, function () {});
      } catch (e) { /* la police du système prend le relais */ }
    });
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Petits outils d'élément
  // ---------------------------------------------------------------------------------------------------------------
  function el(nom, attrs, enfants) {
    var e = document.createElement(nom);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        var v = attrs[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'texte') e.textContent = v;
        else if (k === 'style') e.style.cssText = v;
        else if (k.indexOf('on') === 0 && typeof v === 'function') e.addEventListener(k.slice(2), v);
        else e.setAttribute(k, v === true ? '' : String(v));
      });
    }
    (enfants || []).forEach(function (c) { if (c) e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return e;
  }
  var SVG = {
    ferme: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    micro: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
    microCoupe: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3l18 18M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V6a3 3 0 0 0-5.7-1.3M5 11a7 7 0 0 0 11.3 5.5M19 11a7 7 0 0 1-.6 2.8M12 18v3"/></svg>',
    raccrocher: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 15.5c5-4.7 13-4.7 18 0l-2.4 2.4a1 1 0 0 1-1.2.2l-2.3-1.2a1 1 0 0 1-.5-1.1l.2-1a12 12 0 0 0-5.6 0l.2 1a1 1 0 0 1-.5 1.1l-2.3 1.2a1 1 0 0 1-1.2-.2z"/></svg>',
    envoi: '<svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><path d="M3.4 20.4 20.85 12.92a1 1 0 0 0 0-1.84L3.4 3.6a.99.99 0 0 0-1.39.91L2 9.12c0 .5.37.93.87.99L17 12 2.87 13.88c-.5.07-.87.5-.87 1l.01 4.61c0 .71.73 1.2 1.39.91z"/></svg>',
    etoile: '<svg viewBox="0 0 24 24" width="32" height="32" fill="CURRENT_FILL" stroke="currentColor" stroke-width="1.25" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6L2.5 9.4l6.6-.8z"/></svg>',
    valide: '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  };
  function icone(nom, remplissage) {
    var s = document.createElement('span');
    s.style.cssText = 'display:inline-flex;align-items:center;justify-content:center';
    s.innerHTML = (SVG[nom] || '').replace('CURRENT_FILL', remplissage || 'none'); // SVG fixes écrits ici, jamais du texte reçu
    return s;
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Le widget
  // ---------------------------------------------------------------------------------------------------------------
  var BASE_CSS = [
    ':host{all:initial}',
    '*,*::before,*::after{box-sizing:border-box}',
    '.mk{font-size:15px;line-height:1.35;-webkit-font-smoothing:antialiased}',
    'button{font:inherit;cursor:pointer;border:0;background:none;color:inherit;padding:0}',
    'button:disabled{cursor:not-allowed;opacity:.4}',
    'button:focus-visible,input:focus-visible,textarea:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--mk-focus);outline-offset:2px}',
    'input,textarea{font:inherit;color:inherit}',
    '.mk-ancre{position:fixed;z-index:2147483000}',
    '.mk-rond{width:56px;height:56px;border-radius:50%;transition:transform .15s}',
    '.mk-rond:hover{transform:scale(1.05)}',
    '.mk-accroche{width:max-content;max-width:calc(100vw - 72px);white-space:pre-wrap;border-radius:16px;padding:12px 16px;text-align:left;font-size:15px;font-weight:600;box-shadow:0 6px 20px rgba(0,0,0,.14);animation:mk-entre .3s ease both}',
    '.mk-x{width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.92);color:#444;box-shadow:0 1px 4px rgba(0,0,0,.2);display:flex;align-items:center;justify-content:center;flex:none}',
    '.mk-voile{position:fixed;inset:0;z-index:2147483001;background:rgba(0,0,0,.35)}',
    '.mk-fenetre{position:fixed;z-index:2147483002;border-radius:22px;box-shadow:0 20px 60px rgba(0,0,0,.28);border:1px solid rgba(0,0,0,.06);overflow:hidden;animation:mk-entre .3s ease both;display:flex;flex-direction:column;max-height:calc(100vh - 32px)}',
    '.mk-fenetre.mk-plein{inset:0!important;border-radius:0;max-height:none;width:auto!important;transform:none!important}',
    '.mk-entete{display:flex;align-items:center;justify-content:flex-end;padding:12px 16px 4px}',
    '.mk-fermer{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;opacity:.7}',
    '.mk-fermer:hover{background:rgba(0,0,0,.06);opacity:1}',
    '.mk-corps{padding:4px 20px 16px;overflow:auto;display:flex;flex-direction:column;gap:16px}',
    '.mk-plein .mk-corps{flex:1;justify-content:center}',
    '.mk-centre{display:flex;flex-direction:column;align-items:center;gap:12px;text-align:center}',
    '.mk-btn{display:flex;align-items:center;justify-content:center;height:46px;padding:0 30px;border-radius:999px;font-weight:600;margin:0 auto;width:max-content}',
    '.mk-rond-btn{width:48px;height:48px;border-radius:50%;display:flex;align-items:center;justify-content:center}',
    '.mk-ligne{display:flex;gap:16px;justify-content:center;align-items:center}',
    '.mk-champ{display:flex;align-items:center;gap:8px;border:1px solid rgba(0,0,0,.12);border-radius:999px;padding:0 6px 0 16px;height:44px}',
    '.mk-champ input{flex:1;min-width:0;background:none;border:0;outline:none;font-size:14px;color:inherit}',
    '.mk-champ button{width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none}',
    '.mk-saisie{width:100%;height:44px;border:1px solid rgba(0,0,0,.12);border-radius:12px;padding:0 12px;background:transparent;font-size:14px}',
    '.mk-fil{display:flex;flex-direction:column;gap:8px;max-height:240px;overflow-y:auto}',
    '.mk-bulle{max-width:85%;padding:8px 14px;border-radius:16px;font-size:14px;white-space:pre-wrap;word-break:break-word}',
    '.mk-etoiles{display:flex;gap:6px;justify-content:center}',
    '.mk-etoiles button{padding:0;border-radius:6px;transition:transform .12s}',
    '.mk-etoiles button:hover{transform:scale(1.1)}',
    '.mk-puces{display:flex;flex-wrap:wrap;gap:8px}',
    '.mk-puce{height:32px;padding:0 12px;border-radius:999px;border:1px solid rgba(0,0,0,.15);font-size:14px}',
    '.mk-case{display:flex;gap:8px;align-items:flex-start;font-size:14px;cursor:pointer}',
    '.mk-case input{margin-top:3px}',
    '.mk-petit{font-size:13px;opacity:.75}',
    '.mk-etat{font-size:14px;opacity:.75;min-height:20px}',
    '.mk-mention{text-align:center;font-size:11px;opacity:.5;padding:0 0 12px}',
    '.mk-erreur{font-size:13px;border-radius:12px;padding:8px 12px;background:rgba(0,0,0,.05)}',
    '.mk-vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}',
    '@keyframes mk-entre{from{opacity:0;transform:translateY(8px) scale(.98)}to{opacity:1;transform:none}}',
    '@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}',
  ].join('\n');

  /**
   * Crée un widget. ``options`` :
   *  - hote            : élément où monter (défaut document.body)
   *  - conteneur       : true = aperçu du portail (positionné dans son cadre, aucune requête)
   *  - apparence, couleurs : l'apparence reçue du serveur (ou celle de l'aperçu)
   *  - api             : { base, site, token, chemin, origineStatique, turnActif, relaisForce, contexte }
   *  - etat, etoiles, microRefuse, plafondAtteint : états forcés (aperçu seulement)
   */
  function creerWidget(options) {
    var ap = options.apparence;
    var k = options.couleurs;
    var textes = ap.textes;
    var apercu = !!options.conteneur;
    var api = options.api || {};
    var largeurCadre = options.largeurCadre;

    var etat = options.etat || 'repos';
    var accrocheFermee = false;
    var ouvert = false;
    var conv = {
      mode: null, // voix | ecrit
      sessionToken: null, workflowRunId: null, workflowId: null,
      pc: null, ws: null, stream: null, pcId: null, turn: null,
      microCoupe: false, phase: 'ecoute', revision: null, tours: [], attente: false,
      erreur: null, termine: false, aMonte: false,
    };
    var avis = { etoiles: options.etoiles || 0, obtenu: null, raisons: [], rappel: false, publication: false, commentaire: '', nom: '', contact: '' };
    var orbes = [];
    var minuteurs = [];
    var analyse = null;
    var detruit = false;

    var hote = document.createElement('div');
    hote.setAttribute('data-mark-widget', apercu ? 'apercu' : 'site');
    var racine = hote.attachShadow ? hote.attachShadow({ mode: 'open' }) : hote;
    var style = document.createElement('style');
    style.textContent = BASE_CSS;
    racine.appendChild(style);
    var scene = el('div', { class: 'mk' });
    scene.style.cssText =
      '--mk-focus:' + k.boutons + ';font-family:' + (POLICES[ap.police] || POLICES.switzer) + ';color:' + ap.texte_fenetre;
    racine.appendChild(scene);
    (options.hote || document.body).appendChild(hote);

    var audio = document.createElement('audio');
    audio.autoplay = true;
    audio.setAttribute('playsinline', '');
    audio.style.display = 'none';
    scene.appendChild(audio);

    var live = el('div', { class: 'mk-vh', 'aria-live': 'polite', role: 'status' });
    scene.appendChild(live);
    function annoncer(texte) { live.textContent = texte; }

    function temporiser(fn, ms) {
      var id = setTimeout(fn, ms);
      minuteurs.push(id);
      return id;
    }

    // ----------------------------------------------------------------- requêtes
    function http(methode, chemin, corps) {
      var init = {
        method: methode,
        credentials: 'omit',
        headers: { 'Content-Type': 'application/json' },
      };
      if (corps !== undefined) init.body = JSON.stringify(corps);
      return fetch(api.base + '/api/v1/public/embed' + chemin, init);
    }
    function evenement(nom) {
      if (apercu) return;
      var corps = { evenement: nom, chemin: api.chemin };
      if (api.site) corps.cle = api.site; else corps.token = api.token;
      try {
        http('POST', '/evenement', corps).catch(function () {});
      } catch (e) { /* compteur anonyme : jamais bloquant */ }
    }

    // ----------------------------------------------------------------- dessin
    function mobile() {
      if (apercu) return (largeurCadre || 999) < 500;
      return window.innerWidth < 500;
    }
    function vider(n) { while (n.firstChild) n.removeChild(n.firstChild); }
    function nettoyerOrbes() { orbes.forEach(function (o) { o.detruire(); }); orbes = []; }
    function nouvelleOrbe(taille, options2) {
      var o = creerOrbe(taille, k.orbe, options2);
      orbes.push(o);
      return o;
    }
    function bouton(texte, zone, onclick, extra) {
      return el('button', Object.assign({
        type: 'button', 'data-zone': zone, class: 'mk-btn', texte: texte, onclick: onclick,
        style: 'background:' + k.boutons + ';color:' + surFond(k.boutons),
      }, extra || {}));
    }
    function cote() { return ap.position === 'bas-gauche' ? 'left:20px' : 'right:20px'; }
    function positionner(n) {
      n.style.position = apercu ? 'absolute' : '';
    }

    function emblemeRond(taille, anime) {
      if (ap.embleme === 'logo' && ap.logo_url) {
        var img = el('img', { src: ap.logo_url, alt: '', width: taille, height: taille, referrerpolicy: 'no-referrer', loading: 'lazy' });
        img.style.cssText = 'width:' + taille + 'px;height:' + taille + 'px;border-radius:50%;object-fit:cover;background:' + k.rond_accroche;
        return img;
      }
      var o = nouvelleOrbe(taille, { etat: 'repos', fige: !anime });
      return o.element;
    }

    function dessiner() {
      if (detruit) return;
      nettoyerOrbes();
      Array.prototype.slice.call(scene.children).forEach(function (c) { if (c !== audio && c !== live) scene.removeChild(c); });
      if (!ouvert && etat !== 'information' && ['information', 'conversation', 'avis', 'merci', 'plafond'].indexOf(etat) === -1) {
        dessinerRepli();
      } else {
        dessinerFenetre();
      }
    }

    function dessinerRepli() {
      var ancre = el('div', { class: 'mk-ancre', style: 'bottom:20px;' + cote() + ';display:flex;align-items:flex-end;gap:8px;' +
        (ap.position === 'bas-gauche' ? '' : 'flex-direction:row-reverse') });
      if (apercu) ancre.style.position = 'absolute';
      var libelle = textes.accroche;
      if (etat === 'accroche') {
        ancre.appendChild(el('button', {
          type: 'button', class: 'mk-accroche', 'data-zone': 'accroche', texte: textes.accroche,
          style: 'white-space:pre-wrap;width:max-content;background:' + k.rond_accroche + ';color:' + surFond(k.rond_accroche) + (largeurCadre ? ';max-width:' + (largeurCadre - 72) + 'px' : ''),
          onclick: ouvrir,
        }));
        if (!apercu) {
          ancre.appendChild(el('button', {
            type: 'button', class: 'mk-x', 'aria-label': textes.fermer, onclick: function () {
              accrocheFermee = true; etat = 'repos'; dessiner();
            },
          }, [icone('ferme')]));
        }
      } else {
        var rond = el('button', {
          type: 'button', class: 'mk-rond', 'data-zone': 'rond', 'aria-label': libelle.replace(/\n/g, ' '),
          'aria-haspopup': 'dialog',
          onclick: ouvrir,
          onmouseenter: function () {
            if (!apercu && ap.declenchement === 'clic' && !accrocheFermee && etat === 'repos') { etat = 'accroche'; dessiner(); }
          },
        }, [emblemeRond(56, ap.orbe_animee !== false)]);
        ancre.appendChild(rond);
      }
      scene.appendChild(ancre);
    }

    function dessinerFenetre() {
      var plein = mobile();
      var centree = ap.fenetre === 'centree';
      if (centree && !plein) {
        var voile = el('div', { class: 'mk-voile', onclick: function () { if (etat !== 'conversation') fermer(); } });
        if (apercu) voile.style.position = 'absolute';
        scene.appendChild(voile);
      }
      var pos = plein ? '' : centree
        ? 'top:50%;left:50%;transform:translate(-50%,-50%);width:min(400px,calc(100vw - 32px))'
        : 'bottom:20px;' + cote() + ';width:min(380px,calc(100vw - 32px))';
      var fenetre = el('div', {
        class: 'mk-fenetre' + (plein ? ' mk-plein' : ''), role: 'dialog', 'aria-modal': centree || plein ? 'true' : 'false',
        'aria-label': FIXE.assistant, 'data-zone': 'fenetre', tabindex: '-1',
        style: 'background:' + k.fenetre + ';color:' + ap.texte_fenetre + ';' + pos + (apercu ? ';position:absolute' : ''),
        onkeydown: function (ev) {
          if (ev.key === 'Escape' && etat !== 'conversation') { ev.stopPropagation(); fermer(); }
        },
      });
      var entete = el('div', { class: 'mk-entete' }, [
        el('button', { type: 'button', class: 'mk-fermer', 'aria-label': textes.fermer, onclick: fermer }, [icone('ferme')]),
      ]);
      fenetre.appendChild(entete);
      var corps = el('div', { class: 'mk-corps' });
      fenetre.appendChild(corps);
      if (etat === 'information') vueInformation(corps);
      else if (etat === 'plafond') vuePlafond(corps);
      else if (etat === 'conversation') vueConversation(corps);
      else if (etat === 'avis') vueAvis(corps);
      else if (etat === 'merci') vueMerci(corps);
      fenetre.appendChild(el('p', { class: 'mk-mention', texte: FIXE.mention }));
      scene.appendChild(fenetre);
      var premier = fenetre.querySelector('button[data-zone="demarrer"],input,button[data-zone="avisEnvoyer"],button[data-zone="fermer"],button[data-zone="plafondBouton"]');
      try { (premier && !premier.disabled ? premier : fenetre).focus({ preventScroll: true }); } catch (e) { /* aperçu hors page */ }
    }

    function vueInformation(corps) {
      var c = el('div', { class: 'mk-centre' });
      c.appendChild(nouvelleOrbe(130, { etat: 'repos' }).element);
      corps.appendChild(c);
      corps.appendChild(el('p', { 'data-zone': 'information', class: 'mk-petit', texte: textes.annonce_ia }));
      var caseConf = el('input', { type: 'checkbox', id: 'mk-c1' });
      var caseMicro = el('input', { type: 'checkbox', id: 'mk-c2' });
      var libConf = el('span', null, [textes.case_confidentialite + ' ']);
      if (ap.lien_confidentialite) {
        libConf.appendChild(el('a', { href: ap.lien_confidentialite, target: '_blank', rel: 'noopener noreferrer', texte: FIXE.confidentialite, style: 'text-decoration:underline' }));
      }
      var go = bouton(textes.bouton_demarrer, 'demarrer', function () { demarrer(); });
      function maj() { go.disabled = !(caseConf.checked && caseMicro.checked); }
      caseConf.addEventListener('change', maj);
      caseMicro.addEventListener('change', maj);
      corps.appendChild(el('label', { class: 'mk-case', 'data-zone': 'caseConfidentialite' }, [caseConf, libConf]));
      corps.appendChild(el('label', { class: 'mk-case', 'data-zone': 'caseMicro' }, [caseMicro, el('span', { texte: textes.case_micro })]));
      if (conv.erreur) corps.appendChild(el('p', { class: 'mk-erreur', role: 'alert', texte: conv.erreur }));
      go.disabled = true;
      corps.appendChild(go);
    }

    function vuePlafond(corps) {
      corps.appendChild(el('p', { 'data-zone': 'plafond', class: 'mk-petit', style: mobile() ? 'text-align:center' : '', texte: textes.plafond_message }));
      var nom = el('input', { class: 'mk-saisie', placeholder: FIXE.nom, 'aria-label': FIXE.nom, autocomplete: 'name', maxlength: '200' });
      var coord = el('input', { class: 'mk-saisie', placeholder: FIXE.contact, 'aria-label': FIXE.contact, autocomplete: 'email', maxlength: '254' });
      var erreur = el('p', { class: 'mk-erreur', role: 'alert', style: 'display:none' });
      corps.appendChild(nom);
      corps.appendChild(coord);
      corps.appendChild(erreur);
      var b = bouton(textes.plafond_bouton, 'plafondBouton', function () {
        var contact = contactDe(nom.value, coord.value);
        if (!contact) { erreur.textContent = FIXE.contact; erreur.style.display = ''; coord.focus(); return; }
        b.disabled = true;
        envoyerRappel(contact).then(function (ok) {
          if (ok) { etat = 'merci'; dessiner(); } else { erreur.textContent = FIXE.indisponible; erreur.style.display = ''; b.disabled = false; }
        });
      });
      corps.appendChild(b);
    }

    /** « 06 12 34 56 78 » ou « a@b.fr » dans un seul champ → { nom, telephone | mail }, ou null. */
    function contactDe(nom, coord) {
      var texte = String(coord || '').trim();
      if (!texte) return null;
      var c = {};
      if (nom && nom.trim()) c.nom = nom.trim();
      if (texte.indexOf('@') !== -1) c.mail = texte; else c.telephone = texte;
      return c;
    }

    function vueConversation(corps) {
      if (conv.mode === 'ecrit') {
        corps.appendChild(el('p', { 'data-zone': 'microRefuse', class: 'mk-erreur', texte: textes.erreur_micro }));
        var fil = el('div', { class: 'mk-fil', role: 'log', 'aria-live': 'polite', 'data-fil': '1' });
        corps.appendChild(fil);
        conv.tours.forEach(function (t) { ajouterBulles(fil, t); });
        if (conv.attente) fil.appendChild(bulle('…', 'agent'));
        fil.scrollTop = fil.scrollHeight;
      } else {
        var c = el('div', { class: 'mk-centre', style: 'padding:8px 0' });
        var o = nouvelleOrbe(170, { etat: apercu ? 'ecoute' : 'ecoute' });
        conv.orbe = o;
        c.appendChild(o.element);
        c.appendChild(el('p', { class: 'mk-etat', 'data-etat': '1', texte: libelleEtat() }));
        corps.appendChild(c);
        if (conv.erreur) corps.appendChild(el('p', { class: 'mk-erreur', role: 'alert', texte: conv.erreur }));
      }
      var ligne = el('div', { class: 'mk-ligne' });
      if (conv.mode !== 'ecrit') {
        ligne.appendChild(el('button', {
          type: 'button', class: 'mk-rond-btn', style: 'border:1px solid rgba(0,0,0,.12)',
          'aria-label': conv.microCoupe ? FIXE.retablir_micro : FIXE.couper_micro, 'aria-pressed': conv.microCoupe ? 'true' : 'false',
          onclick: function () { basculerMicro(); },
        }, [icone(conv.microCoupe ? 'microCoupe' : 'micro')]));
      }
      ligne.appendChild(el('button', {
        type: 'button', class: 'mk-rond-btn', 'data-zone': 'raccrocher', 'aria-label': textes.raccrocher, title: textes.raccrocher,
        style: 'background:' + k.raccrocher + ';color:' + surFond(k.raccrocher), onclick: function () { raccrocher(); },
      }, [icone('raccrocher')]));
      corps.appendChild(ligne);
      if (conv.mode === 'ecrit') {
        var champ = el('input', { placeholder: textes.champ_saisie, 'aria-label': textes.champ_saisie, maxlength: '4000', autocomplete: 'off' });
        var envoyer = el('button', {
          type: 'button', 'data-zone': 'envoyer', 'aria-label': textes.envoyer, title: textes.envoyer,
          style: 'background:' + k.boutons + ';color:' + surFond(k.boutons),
        }, [icone('envoi')]);
        var soumettre = function () {
          var t = champ.value.trim();
          if (!t || conv.attente) return;
          champ.value = '';
          envoyerTexte(t);
        };
        envoyer.addEventListener('click', soumettre);
        champ.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); soumettre(); } });
        corps.appendChild(el('div', { class: 'mk-champ', 'data-zone': 'saisieEcrite', style: 'background:' + k.champ_saisie + ';color:' + surFond(k.champ_saisie) }, [champ, envoyer]));
      }
    }

    function libelleEtat() {
      if (conv.microCoupe) return '';
      return conv.phase === 'parole' ? textes.parle : conv.phase === 'reflexion' ? textes.reflexion : textes.ecoute;
    }
    function bulle(texte, qui) {
      var agent = qui === 'agent';
      var b = el('div', { style: 'display:flex;justify-content:' + (agent ? 'flex-start' : 'flex-end') }, [
        el('p', {
          class: 'mk-bulle', 'data-zone': agent ? 'bulleAgent' : 'bulleVisiteur', texte: texte,
          style: agent ? 'background:rgba(0,0,0,.06);color:' + ap.texte_fenetre : 'background:' + k.bulles_ecrit + ';color:' + surFond(k.bulles_ecrit),
        }),
      ]);
      return b;
    }
    function ajouterBulles(fil, tour) {
      if (tour.user_message && tour.user_message.text) fil.appendChild(bulle(tour.user_message.text, 'visiteur'));
      if (tour.assistant_message && tour.assistant_message.text) fil.appendChild(bulle(tour.assistant_message.text, 'agent'));
    }

    function vueAvis(corps) {
      var tete = el('div', { class: 'mk-centre', style: 'gap:8px' });
      tete.appendChild(el('p', { 'data-zone': 'avisQuestion', style: 'font-weight:600', texte: textes.avis_question }));
      var etoiles = el('div', { class: 'mk-etoiles', role: 'group', 'aria-label': textes.avis_question, 'data-zone': 'etoiles' });
      for (var n = 1; n <= 5; n += 1) {
        (function (n2) {
          var plein = n2 <= avis.etoiles;
          var b = el('button', {
            type: 'button', 'aria-label': FIXE.etoile(n2), 'aria-pressed': avis.etoiles === n2 ? 'true' : 'false',
            style: 'color:' + (plein ? k.etoiles : '#d4d4d8'),
            onclick: function () { avis.etoiles = n2; dessiner(); },
          }, [icone('etoile', plein ? k.etoiles : 'none')]);
          etoiles.appendChild(b);
        })(n);
      }
      tete.appendChild(etoiles);
      corps.appendChild(tete);

      if (avis.etoiles > 0) {
        var decu = avis.etoiles <= 3;
        var choixObtenu = el('div', { class: 'mk-puces' });
        FIXE.obtenus.forEach(function (o) { choixObtenu.appendChild(puce(o[1], avis.obtenu === o[0], function () { avis.obtenu = o[0]; dessiner(); })); });
        corps.appendChild(el('div', { style: 'display:flex;flex-direction:column;gap:8px' }, [
          el('p', { class: 'mk-petit', texte: FIXE.obtenu_question }), choixObtenu,
        ]));
        var puces = el('div', { class: 'mk-puces' });
        (decu ? FIXE.raisons_decu : FIXE.raisons_content).forEach(function (r) {
          puces.appendChild(puce(r, avis.raisons.indexOf(r) !== -1, function () {
            avis.raisons = avis.raisons.indexOf(r) !== -1 ? avis.raisons.filter(function (x) { return x !== r; }) : avis.raisons.concat([r]);
            dessiner();
          }));
        });
        corps.appendChild(el('div', { style: 'display:flex;flex-direction:column;gap:8px' }, [
          el('p', { class: 'mk-petit', texte: decu ? FIXE.raisons_question_decu : FIXE.raisons_question_content }), puces,
        ]));
        var caseAvis = el('input', { type: 'checkbox' });
        caseAvis.checked = decu ? avis.rappel : avis.publication;
        caseAvis.addEventListener('change', function () {
          if (decu) avis.rappel = caseAvis.checked; else avis.publication = caseAvis.checked;
          dessiner();
        });
        corps.appendChild(el('label', { class: 'mk-case', 'data-zone': decu ? 'caseRappel' : 'casePublication' }, [
          caseAvis, el('span', { texte: decu ? FIXE.case_rappel : FIXE.case_publication }),
        ]));
        if (decu && avis.rappel) {
          var nom = el('input', { class: 'mk-saisie', placeholder: FIXE.nom, 'aria-label': FIXE.nom, value: avis.nom, autocomplete: 'name', maxlength: '200' });
          var coord = el('input', { class: 'mk-saisie', placeholder: FIXE.contact, 'aria-label': FIXE.contact, value: avis.contact, autocomplete: 'email', maxlength: '254' });
          nom.addEventListener('input', function () { avis.nom = nom.value; });
          coord.addEventListener('input', function () { avis.contact = coord.value; });
          corps.appendChild(nom);
          corps.appendChild(coord);
        }
        var commentaire = el('textarea', {
          rows: '2', class: 'mk-saisie', style: 'height:auto;padding:8px 12px;resize:none', placeholder: FIXE.commentaire,
          'aria-label': FIXE.commentaire, maxlength: '2000',
        });
        commentaire.value = avis.commentaire;
        commentaire.addEventListener('input', function () { avis.commentaire = commentaire.value; });
        corps.appendChild(commentaire);
      }
      var erreur = el('p', { class: 'mk-erreur', role: 'alert', style: 'display:none' });
      corps.appendChild(erreur);
      var ligne = el('div', { class: 'mk-ligne' });
      ligne.appendChild(el('button', {
        type: 'button', 'data-zone': 'avisPasser', texte: textes.fermer, style: 'height:44px;padding:0 16px;opacity:.7',
        onclick: function () { etat = 'merci'; dessiner(); },
      }));
      var envoyer = bouton(textes.avis_envoyer, 'avisEnvoyer', function () {
        var contact = avis.rappel ? contactDe(avis.nom, avis.contact) : null;
        if (avis.rappel && !contact) { erreur.textContent = FIXE.contact; erreur.style.display = ''; return; }
        envoyer.disabled = true;
        envoyerAvis(contact).then(function (ok) {
          if (ok) { etat = 'merci'; dessiner(); } else { erreur.textContent = FIXE.indisponible; erreur.style.display = ''; envoyer.disabled = false; }
        });
      });
      envoyer.style.margin = '0';
      envoyer.disabled = avis.etoiles === 0;
      ligne.appendChild(envoyer);
      corps.appendChild(ligne);
    }
    function puce(texte, actif, onclick) {
      return el('button', {
        type: 'button', class: 'mk-puce', 'data-zone': 'choix', texte: texte, 'aria-pressed': actif ? 'true' : 'false', onclick: onclick,
        style: actif ? 'background:' + k.reponses_choisies + ';color:' + surFond(k.reponses_choisies) + ';border-color:' + k.reponses_choisies : '',
      });
    }

    function vueMerci(corps) {
      corps.appendChild(el('div', { class: 'mk-centre', style: 'padding:8px 0' }, [
        el('span', {
          'data-zone': 'merciIcone', style: 'width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:' + k.boutons + ';color:' + surFond(k.boutons),
        }, [icone('valide')]),
        el('p', { 'data-zone': 'merci', style: 'font-weight:600;font-size:18px', texte: textes.merci }),
      ]));
      corps.appendChild(el('button', {
        type: 'button', 'data-zone': 'fermer', class: 'mk-btn', texte: textes.fermer, onclick: fermer,
        style: 'border:1px solid rgba(0,0,0,.12)',
      }));
      annoncer(textes.merci);
    }

    // ----------------------------------------------------------------- les gestes
    function ouvrir() {
      if (ouvert && etat !== 'repos' && etat !== 'accroche') return;
      ouvert = true;
      etat = 'information';
      evenement('ouvert');
      dessiner();
    }
    function fermer() {
      if (conv.mode && !conv.termine) arreterTout();
      ouvert = false;
      accrocheFermee = true;
      etat = 'repos';
      conv.mode = null; conv.termine = false; conv.sessionToken = null; conv.erreur = null; conv.tours = [];
      avis = { etoiles: 0, obtenu: null, raisons: [], rappel: false, publication: false, commentaire: '', nom: '', contact: '' };
      dessiner();
      var rond = scene.querySelector('[data-zone="rond"]');
      if (rond && rond.focus) try { rond.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    }

    function messageDeRefus(reponse, detail) {
      var code = detail && detail.code;
      return code || (reponse && reponse.status);
    }

    /** Ouvre la session : voix (micro accordé) ou écrit (secours). Rend 'ok' | 'plafond' | 'erreur'. */
    async function ouvrirSession(mode) {
      var corps = { token: api.token, context_variables: api.contexte || {} };
      if (mode === 'ecrit') corps.mode = 'ecrit';
      var reponse;
      try {
        reponse = await http('POST', '/init', corps);
      } catch (e) {
        return 'erreur';
      }
      if (!reponse.ok) {
        var detail = null;
        try { detail = (await reponse.json()).detail; } catch (e) { detail = null; }
        var code = detail && typeof detail === 'object' ? detail.code : null;
        if (code === 'monthly_cap_reached' || code === 'address_rate_limited') return 'plafond';
        return 'erreur';
      }
      var d = await reponse.json();
      conv.sessionToken = d.session_token;
      conv.workflowRunId = d.workflow_run_id;
      conv.workflowId = d.config && d.config.workflow_id;
      conv.mode = d.widget_type === 'chat' ? 'ecrit' : 'voix';
      if (d.chat_session) {
        conv.revision = d.chat_session.revision;
        conv.tours = d.chat_session.turns || [];
      }
      return 'ok';
    }

    async function demarrer() {
      conv.erreur = null;
      conv.termine = false;
      var micro = null;
      var microOk = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && typeof RTCPeerConnection !== 'undefined');
      if (microOk) {
        try {
          micro = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e) {
          micro = null;
        }
      }
      if (!micro) return demarrerALEcrit();
      conv.stream = micro;
      var r = await ouvrirSession('voix');
      if (r === 'plafond') { arreterMicro(); etat = 'plafond'; dessiner(); return; }
      if (r !== 'ok') { arreterMicro(); conv.erreur = FIXE.indisponible; dessiner(); return; }
      if (conv.mode === 'ecrit') { arreterMicro(); etat = 'conversation'; dessiner(); return; }
      etat = 'conversation';
      conv.phase = 'ecoute';
      dessiner();
      try {
        await connecterVoix();
      } catch (e) {
        // Voix impossible (réseau, ICE, signalisation) : l'écrit avec le même agent, une nouvelle session.
        arreterTout(true);
        return demarrerALEcrit();
      }
    }

    async function demarrerALEcrit() {
      var r = await ouvrirSession('ecrit');
      if (r === 'plafond') { etat = 'plafond'; dessiner(); return; }
      if (r !== 'ok') { conv.erreur = FIXE.indisponible; etat = 'information'; dessiner(); return; }
      conv.mode = 'ecrit';
      etat = 'conversation';
      dessiner();
    }

    // ----------------------------------------------------------------- voix (WebRTC)
    function arreterMicro() {
      if (conv.stream) { conv.stream.getTracks().forEach(function (t) { t.stop(); }); conv.stream = null; }
    }
    function arreterAnalyse() {
      if (analyse) {
        if (analyse.image) cancelAnimationFrame(analyse.image);
        try { analyse.ctx.close(); } catch (e) { /* ignore */ }
        analyse = null;
      }
    }
    function arreterTout(silencieux) {
      conv.termine = true;
      arreterAnalyse();
      if (conv.ws) { var w = conv.ws; conv.ws = null; try { w.close(); } catch (e) { /* ignore */ } }
      if (conv.pc) { var p = conv.pc; conv.pc = null; try { p.close(); } catch (e) { /* ignore */ } }
      arreterMicro();
      audio.srcObject = null;
      if (!silencieux) annoncer('');
    }

    async function turnCredentials() {
      if (api.turnActif === false || !conv.sessionToken) return null;
      try {
        var r = await http('GET', '/turn-credentials/' + conv.sessionToken);
        return r.ok ? await r.json() : null;
      } catch (e) {
        return null;
      }
    }

    async function connecterVoix() {
      var creds = await turnCredentials();
      var serveurs = [];
      if (creds && creds.uris && creds.uris.length) {
        serveurs.push({ urls: creds.uris, username: creds.username, credential: creds.password });
      } else if (!api.relaisForce) {
        // Sans serveur TURN chez nous, le serveur STUN public de Google, comme le script historique.
        serveurs.push({ urls: ['stun:stun.l.google.com:19302'] });
      }
      var config = { iceServers: serveurs };
      if (api.relaisForce) config.iceTransportPolicy = 'relay';
      var pc = new RTCPeerConnection(config);
      conv.pc = pc;
      conv.stream.getTracks().forEach(function (t) { pc.addTrack(t, conv.stream); });
      pc.ontrack = function (ev) {
        if (ev.track.kind === 'audio') { audio.srcObject = ev.streams[0]; demarrerAnalyse(ev.streams[0]); }
      };
      var pcId = 'PC-' + Array.from(crypto.getRandomValues(new Uint8Array(16))).map(function (b) { return b.toString(16).padStart(2, '0'); }).join('');
      conv.pcId = pcId;
      var verdict = new Promise(function (resolve, reject) {
        pc.onconnectionstatechange = function () {
          if (pc.connectionState === 'connected') { conv.aMonte = true; resolve(); }
          if (pc.connectionState === 'failed' && !conv.aMonte) reject(new Error('ice'));
          if ((pc.connectionState === 'failed' || pc.connectionState === 'disconnected' || pc.connectionState === 'closed') && conv.aMonte && !conv.termine) {
            terminerLaConversation();
          }
        };
        temporiser(function () { if (!conv.aMonte) reject(new Error('delai')); }, 20000);
      });
      pc.onicecandidate = function (ev) {
        if (conv.ws && conv.ws.readyState === 1) {
          conv.ws.send(JSON.stringify({
            type: 'ice-candidate',
            payload: {
              candidate: ev.candidate ? { candidate: ev.candidate.candidate, sdpMid: ev.candidate.sdpMid, sdpMLineIndex: ev.candidate.sdpMLineIndex } : null,
              pc_id: pcId,
            },
          }));
        }
      };
      await new Promise(function (resolve, reject) {
        var url = api.base.replace(/^http/, 'ws') + '/api/v1/ws/public/signaling/' + conv.sessionToken;
        var ws = new WebSocket(url);
        conv.ws = ws;
        ws.onopen = function () { resolve(); };
        ws.onerror = function () { reject(new Error('ws')); };
        ws.onclose = function (ev) {
          conv.ws = null;
          if (ev && ev.reason === 'call ended') terminerLaConversation();
        };
        ws.onmessage = async function (ev) {
          try {
            var m = JSON.parse(ev.data);
            if (m.type === 'answer') await pc.setRemoteDescription({ type: 'answer', sdp: m.payload.sdp });
            else if (m.type === 'ice-candidate' && m.payload.candidate) {
              await pc.addIceCandidate({ candidate: m.payload.candidate.candidate, sdpMid: m.payload.candidate.sdpMid, sdpMLineIndex: m.payload.candidate.sdpMLineIndex });
            } else if (m.type === 'call-ended') terminerLaConversation();
          } catch (e) { /* un message illisible ne coupe pas la conversation */ }
        };
      });
      var offre = await pc.createOffer();
      await pc.setLocalDescription(offre);
      conv.ws.send(JSON.stringify({
        type: 'offer',
        payload: { sdp: offre.sdp, type: 'offer', pc_id: pcId, workflow_id: parseInt(conv.workflowId, 10), workflow_run_id: parseInt(conv.workflowRunId, 10) },
      }));
      await verdict;
    }

    /** L'orbe suit le son : la voix de l'agent (flux distant) et la parole du visiteur (micro). */
    function demarrerAnalyse(flux) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC || analyse) return;
      try {
        var ctx = new AC();
        var dist = ctx.createAnalyser(); dist.fftSize = 256;
        ctx.createMediaStreamSource(flux).connect(dist);
        var loc = null;
        if (conv.stream) { loc = ctx.createAnalyser(); loc.fftSize = 256; ctx.createMediaStreamSource(conv.stream).connect(loc); }
        var tampon = new Uint8Array(128);
        var derniereParole = 0;
        analyse = { ctx: ctx, image: 0 };
        var niveau = function (a) {
          a.getByteTimeDomainData(tampon);
          var s = 0;
          for (var i = 0; i < tampon.length; i += 1) { var v = (tampon[i] - 128) / 128; s += v * v; }
          return Math.sqrt(s / tampon.length);
        };
        var boucle = function () {
          if (!analyse) return;
          var vd = niveau(dist);
          var vl = loc && !conv.microCoupe ? niveau(loc) : 0;
          var maintenant = Date.now();
          if (vl > 0.04) derniereParole = maintenant;
          var phase = vd > 0.02 ? 'parole' : (maintenant - derniereParole < 4000 && derniereParole ? 'reflexion' : 'ecoute');
          if (conv.orbe) { conv.orbe.setEtat(phase); conv.orbe.setVolume(Math.min(1, vd * 6)); }
          if (phase !== conv.phase) {
            conv.phase = phase;
            var t = scene.querySelector('[data-etat]');
            if (t) t.textContent = libelleEtat();
          }
          analyse.image = requestAnimationFrame(boucle);
        };
        analyse.image = requestAnimationFrame(boucle);
      } catch (e) { analyse = null; }
    }

    function basculerMicro() {
      conv.microCoupe = !conv.microCoupe;
      if (conv.stream) conv.stream.getAudioTracks().forEach(function (t) { t.enabled = !conv.microCoupe; });
      dessiner();
    }

    function terminerLaConversation() {
      if (conv.termine) return;
      arreterTout(true);
      if (etat === 'conversation') { etat = ap.avis === false ? 'merci' : 'avis'; dessiner(); }
    }

    async function raccrocher() {
      if (apercu) { etat = ap.avis === false ? 'merci' : 'avis'; dessiner(); return; }
      var ecrit = conv.mode === 'ecrit';
      if (ecrit && conv.sessionToken && !conv.termine) {
        try {
          var r = await http('POST', '/chat/' + conv.sessionToken + '/end', { expected_revision: conv.revision });
          if (r.ok) { var d = await r.json(); conv.revision = d.revision; }
        } catch (e) { /* la conversation se ferme côté serveur à son expiration */ }
      }
      conv.termine = true;
      arreterTout(true);
      etat = ap.avis === false ? 'merci' : 'avis';
      dessiner();
    }

    // ----------------------------------------------------------------- écrit
    async function envoyerTexte(texte) {
      conv.attente = true;
      conv.tours = conv.tours.concat([{ id: 'local', status: 'pending', user_message: { text: texte } }]);
      dessiner();
      try {
        var r = await http('POST', '/chat/' + conv.sessionToken + '/messages', { text: texte, expected_revision: conv.revision });
        if (r.ok) {
          var d = await r.json();
          conv.revision = d.revision;
          conv.tours = d.turns || conv.tours;
        } else {
          conv.erreur = FIXE.indisponible;
        }
      } catch (e) {
        conv.erreur = FIXE.indisponible;
      }
      conv.attente = false;
      dessiner();
      var champ = scene.querySelector('.mk-champ input');
      if (champ && champ.focus) champ.focus();
    }

    // ----------------------------------------------------------------- avis, rappel
    async function envoyerAvis(contact) {
      if (apercu) return true;
      if (!conv.sessionToken) return true; // aucune conversation à noter
      var corps = {
        etoiles: avis.etoiles, raisons: avis.raisons,
        rappel_demande: !!(avis.rappel && contact), publication_acceptee: avis.etoiles > 3 && avis.publication,
      };
      if (avis.obtenu) corps.obtenu = avis.obtenu;
      if (avis.commentaire.trim()) corps.commentaire = avis.commentaire.trim();
      if (contact) corps.contact = contact;
      // La conversation se termine côté serveur quelques instants après le raccroché : on réessaie.
      for (var essai = 0; essai < 6; essai += 1) {
        try {
          var r = await http('POST', '/avis/' + conv.sessionToken, corps);
          if (r.ok) return true;
          var detail = null;
          try { detail = (await r.json()).detail; } catch (e) { detail = null; }
          var code = detail && detail.code;
          if (code === 'review_already_given') return true;
          if (code !== 'conversation_not_finished') return false;
        } catch (e) {
          return false;
        }
        await new Promise(function (ok) { temporiser(ok, 1500); });
      }
      return false;
    }
    async function envoyerRappel(contact) {
      if (apercu) return true;
      try {
        var r = await http('POST', '/rappel/' + api.site, { chemin: api.chemin, contact: contact });
        return r.ok;
      } catch (e) {
        return false;
      }
    }

    // ----------------------------------------------------------------- cycle de vie
    function detruire() {
      detruit = true;
      arreterTout(true);
      nettoyerOrbes();
      minuteurs.forEach(clearTimeout);
      if (hote.parentNode) hote.parentNode.removeChild(hote);
    }

    function afficher() {
      // Le déclenchement de l'accroche, réglé par le client : tout de suite (délai 0), après un délai, ou au survol.
      dessiner();
      if (apercu) return;
      evenement('affiche');
      if (ap.declenchement === 'delai') {
        temporiser(function () {
          if (!accrocheFermee && etat === 'repos' && !ouvert) { etat = 'accroche'; dessiner(); }
        }, Math.max(0, ap.delai_s || 0) * 1000);
      }
    }
    if (apercu) {
      if (options.etat === 'plafond' || options.plafondAtteint) etat = 'plafond';
      if (etat !== 'repos' && etat !== 'accroche') ouvert = true;
      if (etat === 'conversation') conv.mode = options.microRefuse ? 'ecrit' : 'voix';
    }
    afficher();

    return {
      detruire: detruire,
      element: hote,
      racine: racine,
      etat: function () { return etat; },
      ouvrir: ouvrir,
      fermer: fermer,
      majApercu: function (opts) {
        if (!apercu) return;
        if (opts.apparence) { ap = opts.apparence; textes = ap.textes; }
        if (opts.couleurs) k = opts.couleurs;
        if (opts.etat) { etat = opts.etat; ouvert = ['repos', 'accroche'].indexOf(etat) === -1; }
        if (typeof opts.etoiles === 'number') avis.etoiles = opts.etoiles;
        if (opts.microRefuse !== undefined) conv.mode = opts.microRefuse ? 'ecrit' : 'voix';
        scene.style.fontFamily = POLICES[ap.police] || POLICES.switzer;
        scene.style.color = ap.texte_fenetre;
        dessiner();
      },
    };
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Apparence par défaut (l'aperçu et les champs absents) : le bleu .mark
  // ---------------------------------------------------------------------------------------------------------------
  var TEXTES_DEFAUT = {
    accroche: 'Une question ?\nParlez-moi.', bouton_demarrer: 'Parler',
    annonce_ia: 'Vous parlez à un assistant virtuel (intelligence artificielle).',
    case_confidentialite: 'J’ai lu la politique de confidentialité.',
    case_micro: 'J’accepte que ma voix soit transmise pour cette conversation.',
    ecoute: 'Je vous écoute', reflexion: 'Je réfléchis', parle: 'Je vous réponds',
    champ_saisie: 'Écrire un message', envoyer: 'Envoyer', raccrocher: 'Raccrocher', fermer: 'Fermer',
    erreur_micro: 'Le micro n’est pas disponible. Vous pouvez m’écrire.',
    avis_question: 'Cette conversation vous a-t-elle aidé ?', avis_envoyer: 'Envoyer mon avis', merci: 'Merci, à bientôt.',
    plafond_message: 'Je ne suis pas disponible pour le moment. Laissez vos coordonnées, vous serez rappelé.',
    plafond_bouton: 'Être rappelé',
  };
  function apparenceComplete(brute) {
    var a = brute || {};
    var textes = Object.assign({}, TEXTES_DEFAUT, a.textes || {});
    return Object.assign({
      couleur_base: COULEUR_MARK, fond_fenetre: '#ffffff', texte_fenetre: '#0f1c2e', police: 'switzer', embleme: 'orbe',
      logo_url: null, orbe_animee: true, position: 'bas-droite', fenetre: 'ancree', declenchement: 'clic', delai_s: 0,
      lien_confidentialite: null, avis: true,
    }, a, { textes: textes });
  }
  function couleursCompletes(ap, brutes) {
    var base = ap.couleur_base;
    return Object.assign({
      rond_accroche: base, fenetre: ap.fond_fenetre, orbe: base, boutons: base, raccrocher: base, champ_saisie: ap.fond_fenetre,
      bulles_ecrit: base, etoiles: base, reponses_choisies: base, icones: base,
    }, brutes || {});
  }

  // ---------------------------------------------------------------------------------------------------------------
  // Démarrage sur une page du client
  // ---------------------------------------------------------------------------------------------------------------
  function baseDeLApi(p) {
    var ep = p.apiEndpoint;
    if (ep) return /^https?:\/\//.test(ep) ? ep.replace(/\/+$/, '') : 'https://' + ep.replace(/\/+$/, '');
    if (p.url.origin.indexOf('localhost') !== -1) return 'http://localhost:8000';
    return p.url.origin.replace(/:\d+$/, ':8000');
  }
  function contexteDeLaPage(el2) {
    var c = {
      // Le chemin seulement : jamais les paramètres ni l'ancre (ils peuvent porter des identifiants).
      page_url: location.origin + location.pathname,
      page_title: String(document.title || '').slice(0, 200),
      today: new Date().toISOString().slice(0, 10),
      referrer: document.referrer ? (function () { try { return new URL(document.referrer).origin; } catch (e) { return ''; } })() : '',
      langue: navigator.language || 'fr',
    };
    try {
      var perso = el2 && el2.getAttribute && el2.getAttribute('data-dograh-context');
      if (perso) Object.assign(c, JSON.parse(perso));
    } catch (e) { /* un attribut mal écrit n'empêche pas le widget */ }
    return c;
  }

  var instance = null;
  async function demarrerSurLaPage(p, el2) {
    var base = baseDeLApi(p);
    var chemin = location.pathname || '/';
    var reponse;
    try {
      reponse = await fetch(base + '/api/v1/public/embed/site/' + encodeURIComponent(p.site) + '/config?chemin=' + encodeURIComponent(chemin), {
        method: 'GET', credentials: 'omit',
      });
    } catch (e) {
      return; // le site du client reste intact : pas de widget
    }
    if (!reponse.ok) return;
    var config = await reponse.json();
    if (!config || config.actif === false) return; // aucune agent pour cette page
    var ap = apparenceComplete(config.apparence);
    var couleurs = couleursCompletes(ap, config.couleurs);
    chargerLesPolices(p.url.origin);
    instance = creerWidget({
      apparence: ap, couleurs: couleurs,
      api: {
        base: base, site: p.site, token: config.token, chemin: chemin,
        turnActif: config.turn_enabled, relaisForce: !!config.force_turn_relay, contexte: contexteDeLaPage(el2),
      },
    });
  }

  // Pour l'éditeur du portail : le même widget, dans un cadre, sans requête.
  window.MarkWidget = {
    apercu: function (conteneur, options) {
      options = options || {};
      var ap = apparenceComplete(options.apparence);
      var couleurs = couleursCompletes(ap, options.couleurs);
      chargerLesPolices(options.origineStatique || (P && P.url.origin) || location.origin);
      return creerWidget({
        hote: conteneur, conteneur: true, apparence: ap, couleurs: couleurs, etat: options.etat || 'accroche',
        etoiles: options.etoiles, microRefuse: !!options.microRefuse, plafondAtteint: !!options.plafondAtteint, largeurCadre: options.largeurCadre,
      });
    },
    instance: function () { return instance; },
  };

  if (P && P.site) {
    var lancer = function () { demarrerSurLaPage(P, script); };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', lancer); else lancer();
  } else if (P && P.token) {
    chargerLeScriptParJeton(script, P.url);
  } else if (script) {
    // Ni site ni jeton : rien à afficher (le script sert aussi à l'aperçu du portail).
  }
})();

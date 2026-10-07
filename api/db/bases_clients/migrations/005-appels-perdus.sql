-- =====================================================================
--  005 : les appels perdus pendant une panne (chantier l-agent-travaille,
--  L7, PN5). Additive seulement.
--
--  Quand notre serveur est tombé, Twilio a joué la consigne de secours
--  (TwiML Bin) et Dograh n'a rien écrit. Au retour, le rattrapage relit le
--  journal des appels Twilio du client et recrée, pour chacun, la demande
--  « à rappeler ». mark.recevoir_appel_perdu(...) l'écrit UNE fois : un
--  même appel Twilio (call_sid) rejoué rend la demande déjà créée.
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS appel_perdu (
    call_sid    text PRIMARY KEY,                 -- l'appel chez Twilio : idempotence
    numero      text,
    numero_appele text,
    debut       timestamptz NOT NULL,
    statut_twilio text,
    demande_id  bigint REFERENCES demande(id) ON DELETE SET NULL,
    recu_le     timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION recevoir_appel_perdu(
    p_call_sid text, p_numero text, p_numero_appele text, p_debut timestamptz, p_statut text
) RETURNS jsonb LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_existant  appel_perdu%ROWTYPE;
    v_contact   bigint;
    v_site      bigint;
    v_demande   bigint;
BEGIN
    INSERT INTO appel_perdu (call_sid, numero, numero_appele, debut, statut_twilio)
    VALUES (p_call_sid, nullif(p_numero, ''), nullif(p_numero_appele, ''), p_debut, p_statut)
    ON CONFLICT (call_sid) DO NOTHING;
    IF NOT FOUND THEN
        SELECT * INTO v_existant FROM appel_perdu WHERE call_sid = p_call_sid;
        RETURN jsonb_build_object('demande_id', v_existant.demande_id, 'doublon', true);
    END IF;

    IF nullif(p_numero_appele, '') IS NOT NULL THEN
        SELECT site_id INTO v_site FROM site_numero WHERE numero = p_numero_appele;
    END IF;
    IF nullif(p_numero, '') IS NOT NULL THEN
        SELECT contact_id INTO v_contact FROM telephone WHERE numero = p_numero;
        IF v_contact IS NULL THEN
            INSERT INTO contact DEFAULT VALUES RETURNING id INTO v_contact;
            INSERT INTO telephone (numero, contact_id) VALUES (p_numero, v_contact)
            ON CONFLICT (numero) DO UPDATE SET contact_id = coalesce(telephone.contact_id, EXCLUDED.contact_id);
        END IF;
    END IF;

    INSERT INTO demande (contact_id, site_id, type, priorite, resume, creee_le)
    VALUES (v_contact, v_site, 'autre', 1,
            'Appel perdu pendant une panne de l''agent (consigne de secours jouée par Twilio) : à rappeler.',
            p_debut)
    RETURNING id INTO v_demande;
    UPDATE appel_perdu SET demande_id = v_demande WHERE call_sid = p_call_sid;
    RETURN jsonb_build_object('demande_id', v_demande, 'contact_id', v_contact, 'doublon', false);
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON appel_perdu TO mark_ecriture;

INSERT INTO schema_version (version, description) VALUES
    (5, 'Appels perdus pendant une panne : appel_perdu, recevoir_appel_perdu (rattrapage, une fois par appel Twilio)');

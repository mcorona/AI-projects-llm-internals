-- Semana 14, actividad 5: un rol de PostgreSQL por perfil de scopes (idempotente; se corre como administrador).
-- El servidor MCP se conecta como copilot_nlq y en cada transacción hace SET LOCAL ROLE al rol del perfil del token:
-- la base es la última línea de defensa aunque el guard fallara. Las FK cuentan: art_prv (proveedor) y art_cst (costo)
-- solo los lee legado_r_proveedores.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['legado_r_leer', 'legado_r_ventas', 'legado_r_proveedores',
                           'legado_perfil_l', 'legado_perfil_lv', 'legado_perfil_lp', 'legado_perfil_lvp'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT', r);
    END IF;
  END LOOP;
END $$;

-- partir de cero en cada corrida (también revoca los privilegios por columna)
REVOKE ALL ON ALL TABLES IN SCHEMA legado FROM legado_r_leer, legado_r_ventas, legado_r_proveedores;
REVOKE ALL ON SCHEMA legado FROM legado_r_leer, legado_r_ventas, legado_r_proveedores;

GRANT USAGE ON SCHEMA legado TO legado_r_leer, legado_r_ventas, legado_r_proveedores;
GRANT SELECT ON legado.almmst, legado.exidet, legado.artnot TO legado_r_leer;
GRANT SELECT (art_cd, art_dsc, art_lin, art_ptr, art_crt) ON legado.artmst TO legado_r_leer;
GRANT SELECT ON legado.vtadia TO legado_r_ventas;
GRANT SELECT ON legado.prvmst, legado.ocpcab, legado.artmst TO legado_r_proveedores;

GRANT legado_r_leer TO legado_perfil_l, legado_perfil_lv, legado_perfil_lp, legado_perfil_lvp;
GRANT legado_r_ventas TO legado_perfil_lv, legado_perfil_lvp;
GRANT legado_r_proveedores TO legado_perfil_lp, legado_perfil_lvp;

-- el rol de conexión solo puede cambiar a estos perfiles (NOINHERIT: no suma sus privilegios por sí mismo)
GRANT legado_perfil_l, legado_perfil_lv, legado_perfil_lp, legado_perfil_lvp TO copilot_nlq;

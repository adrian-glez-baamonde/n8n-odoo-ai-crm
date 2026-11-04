-- Usuario de SOLO LECTURA para el asistente de IA (flujo 02).
-- Principio de mínimo privilegio: el agente genera SQL a partir de lenguaje natural,
-- así que la base de datos debe impedir cualquier escritura aunque el modelo se equivoque
-- o alguien intente manipularlo ("borra todos los leads").
--
-- Uso (desde la raíz del repo; la contraseña se pasa como variable de psql):
--   docker compose exec -T db psql -U odoo -d modanorte -v pwd="LA_CONTRASEÑA" < scripts/create_readonly_user.sql
-- Es idempotente: se puede ejecutar varias veces.

-- 1) Crear el rol si no existe (\gexec ejecuta el texto generado por la SELECT).
SELECT format('CREATE ROLE asistente_ro LOGIN PASSWORD %L', :'pwd')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asistente_ro')
\gexec

-- Si ya existía, actualizar la contraseña.
ALTER ROLE asistente_ro WITH LOGIN PASSWORD :'pwd';

-- 2) Defensa en profundidad: aunque tuviera permisos, sus transacciones son de solo lectura
--    y ninguna consulta puede durar más de 5 s (evita consultas que bloqueen la BD).
ALTER ROLE asistente_ro SET default_transaction_read_only = on;
ALTER ROLE asistente_ro SET statement_timeout = '5s';

-- 3) Permisos mínimos: conectarse, ver el esquema y leer SOLO estas 5 tablas.
SELECT format('GRANT CONNECT ON DATABASE %I TO asistente_ro', current_database())
\gexec
GRANT USAGE ON SCHEMA public TO asistente_ro;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM asistente_ro;
GRANT SELECT ON crm_lead, crm_tag, crm_tag_rel, crm_stage, res_partner TO asistente_ro;

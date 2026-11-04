# Decisiones técnicas y aprendizajes

Registro fase a fase de qué se hizo, por qué, y qué aprendí. Base para preparar la entrevista.

---

## Fase 1 — Infraestructura con Docker Compose

**Qué:** `docker-compose.yml` con 3 servicios (`db` PostgreSQL 16, `odoo` 18, `n8n`), volúmenes con nombre y configuración por `.env`.

**Decisiones:**

- **Red de Compose y nombres de servicio.** Compose crea una red privada para el proyecto y un DNS interno: cada servicio es accesible por su nombre. Por eso Odoo se conecta a la base de datos con `HOST=db` y no con una IP ni con `localhost` (dentro de un contenedor, `localhost` es *el propio contenedor*). Lo mismo usará n8n en la fase 4: se conectará a Postgres como `db:5432`.
- **PostgreSQL no expuesto al host.** Solo Odoo y n8n (dentro de la red) necesitan llegar a él. Si no se publica el puerto, la superficie de ataque es menor. Para depurar se puede descomentar `ports: 5432:5432`.
- **Volúmenes con nombre** (`odoo-db-data`, `odoo-web-data`, `n8n-data`): los contenedores son desechables y los datos no. `docker compose down` conserva los datos y `down -v` los borra.
- **`depends_on` con `condition: service_healthy`.** Con un simple `depends_on`, Docker solo espera a que el contenedor *arranque*, no a que Postgres *acepte conexiones*. El `healthcheck` con `pg_isready` evita que Odoo falle al arrancar.
- **`N8N_ENCRYPTION_KEY` fija en `.env`.** n8n cifra las credenciales (OpenAI, Telegram, Odoo...) con esta clave. Si no se fija, n8n genera una dentro del volumen. Al fijarla, queda controlada y se puede hacer backup de ella. Si se pierde, las credenciales dejan de poder descifrarse.
- **`WEBHOOK_URL`.** n8n la usa para construir las URLs de los webhooks y del chat que muestra en la interfaz. En local es `http://localhost:5678/`. En producción sería el dominio público con HTTPS.
- **n8n con su SQLite por defecto**, separado de la base de datos de Odoo. Así se mantiene el aislamiento: si se reinicia o rompe una, no afecta a la otra. Para producción con mucho volumen se movería n8n a Postgres.
- **Secretos solo en `.env`** (ignorado por git). En el repo solo está `.env.example`, con valores de ejemplo.

---

## Fase 2 — Datos de prueba en Odoo

**Qué:** `scripts/seed_odoo.py` crea 5 etiquetas CRM y 20 oportunidades de ejemplo usando la API externa de Odoo (XML-RPC).

**Decisiones:**

- **XML-RPC con API key.** Es la API externa oficial de Odoo y viene incluida en Python (`xmlrpc.client`), así que el script no tiene dependencias. Funciona en dos pasos:
  - `/xmlrpc/2/common` → `authenticate()` devuelve el `uid` del usuario.
  - `/xmlrpc/2/object` → `execute_kw(db, uid, key, modelo, método, args, kwargs)` llama a cualquier método del ORM (`search`, `create`, `search_read`...).
  - La API key sustituye a la contraseña: se puede revocar sin cambiar la contraseña del usuario y tiene caducidad.
- **Una API key por consumidor** (`seed-script-local` y, en la fase 3, `n8n-local`). Si una se filtra, se revoca solo esa.
- **Idempotencia:** antes de crear un registro se busca por su nombre. Para los leads, la búsqueda usa `active_test=False`, que incluye también los archivados o perdidos. Ejecutarlo dos veces no duplica nada.
- **Campos many2many con comandos:** `tag_ids: [(6, 0, [id])]` significa "reemplaza las etiquetas por esta lista". Es la sintaxis del ORM de Odoo para relaciones.
- **Prioridad:** en Odoo, `priority` es una selección de `'0'` a `'3'` (las estrellas). El mapeo `baja→'1'`, `media→'2'`, `alta→'3'` es el mismo que usará n8n en la fase 3.
- **`create_date` no se puede escribir por la API:** es un campo "mágico" que gestiona el ORM. Para tener fechas realistas en la demo ("quejas de esta semana"), el script hace un `UPDATE` directo en Postgres con `docker compose exec`, y solo sobre los leads recién creados. En datos reales no se haría.

**`crm.lead` vs `res.partner`:**

- **`res.partner`** es la *libreta de direcciones* de Odoo: personas y empresas. La comparten todos los módulos (ventas, facturación, CRM, inventario). Un cliente existe una sola vez aquí.
- **`crm.lead`** es una *oportunidad de negocio*: algo que puede acabar en venta, con etapa, prioridad, importe esperado y probabilidad. Un mismo partner puede tener muchas oportunidades.
  - Un lead puede tener `partner_id` (cliente ya conocido) o solo datos sueltos (`contact_name`, `email_from`, `phone`) si es alguien nuevo.
  - Al convertir o ganar el lead, Odoo puede crear el partner.
  - Por eso los leads que llegan del formulario se guardan con datos sueltos: no ensuciamos la libreta de clientes con contactos que quizá nunca compren.
- En base de datos: tablas `crm_lead` y `res_partner`, unidas por `crm_lead.partner_id`.

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

---

## Fase 3 — Flujo 01: captación y clasificación con IA

**Qué:** Webhook `POST /webhook/contacto` → validación → GPT clasifica (categoría, prioridad, resumen, idioma) → se busca la etiqueta en Odoo → se crea la oportunidad (`crm.lead`) → si la prioridad es alta, aviso por Telegram → respuesta `200 {"ok": true, "lead_id": N}`. Exportado en `workflows/01-captacion-leads.json`. Mensajes de prueba en `tests/contacto/`.

**Decisiones:**

- **`Respond to Webhook` en lugar de responder al instante.** Así controlamos el código HTTP: `400` si los datos no son válidos, `200` con el `lead_id` cuando todo ha ido bien. Además, el cliente (la web) sabe si de verdad se guardó su mensaje.
- **URL de test y URL de producción.** `/webhook-test/...` solo escucha mientras pulsas *Execute workflow* y muestra los datos en el lienzo. `/webhook/...` solo existe con el flujo activo/publicado, y sus ejecuciones se ven en *Executions*.
- **Validación antes de llamar a la IA:** no se gasta una llamada a OpenAI (dinero y tiempo) con datos basura. Fallo real que tuve: el campo izquierdo del If estaba en modo *Fixed* y comparaba el texto literal `{{ $json.body.email }}`. En el JSON se distingue porque las expresiones empiezan por `=`.
- **Basic LLM Chain + OpenAI Chat Model + Structured Output Parser.** La cadena junta el prompt y el modelo, y el parser obliga a que la salida cumpla un JSON Schema. Si no lo cumple, el nodo falla en lugar de dejar pasar datos malos.
- **JSON Schema con `enum`** en vez de "generar desde un ejemplo": el esquema limita los valores posibles de `categoria` y `prioridad` a los que existen en Odoo, así que el modelo no puede inventarse una categoría.
- **`temperature: 0`:** clasificar es una tarea determinista, y el mismo mensaje debe dar siempre la misma categoría. Una temperatura alta da variedad, útil para redactar y perjudicial para etiquetar.
- **`gpt-4.1-mini`:** es barato (una fracción de céntimo por mensaje) y suficiente para clasificar. Los modelos de razonamiento (GPT-5) no permiten cambiar la `temperature` y son más lentos y caros para esta tarea.
- **Diseño del prompt:**
  - rol + tarea;
  - definición de cada categoría;
  - regla de desempate (Queja > Devolución > Mayorista > Pedido > Información);
  - criterios de prioridad;
  - 3 ejemplos *few-shot* (uno en inglés y uno mayorista).
- **Defensa contra inyección de prompts:** el mensaje va entre `<mensaje>...</mensaje>` y el prompt indica que es *dato a clasificar* e ignorar cualquier instrucción que contenga.
- **Iteración del prompt:** "quería pedir dos camisas... ¿cuánto tarda el envío?" salía con prioridad *baja*, porque la regla de "consulta informativa" ganaba a la de pedido. Añadí "cualquier mensaje con intención clara de compra es como mínimo media" y pasó a *media*. El ciclo es: probar → ver el fallo → ajustar la regla → volver a probar.
- **¿Y si la IA clasifica mal?** No rompe nada: el lead se crea igual con el mensaje original y el comercial lo recoloca. La IA prioriza y ordena, pero no decide sola. El mensaje ambiguo ("Lo de la otra vez sigue igual") salió como Queja con prioridad media, algo defendible.
- **Etiqueta buscada por nombre** (`crm.tag` con `name = categoria`) en lugar de IDs escritos a mano: los IDs cambian entre instalaciones.
- **Nodo Odoo v2 y Odoo 18:** la autenticación "API Key (Recommended)" del nodo usa el endpoint `/json/2`, que **solo existe en Odoo 19+**. Con Odoo 18 daba `response.sort is not a function`, porque Odoo devolvía una página de error en vez de JSON. Revisé el código del nodo y cambié a "Username & Password", que usa `/jsonrpc`. En el campo de la contraseña se puede poner una API key.
- **`Site URL = http://odoo:8069`:** desde el contenedor de n8n, `localhost` sería el propio n8n. Se llega a Odoo por el nombre del servicio en la red de Compose.
- **Etiquetas y "Map Automatically":** en modo manual, el nodo Odoo v2 oculta los campos many2many (`tag_ids`). Por eso un *Edit Fields* prepara el JSON exacto de `crm.lead` (incluido `tag_ids: [id]`) y el nodo lo envía tal cual. Antes de hacerlo, comprobé por XML-RPC que Odoo acepta una lista simple de IDs.
- **`$('Nombre del nodo').item.json`:** cada nodo solo recibe en `$json` la salida del nodo anterior. Para datos de nodos anteriores se les llama por su nombre, así que conviene ponerles nombres claros.
- **Prioridad:** se traduce de texto a las estrellas de Odoo con `{ baja: '1', media: '2', alta: '3' }`, el mismo mapeo que en el script de datos de prueba.
- **Telegram y *escaping*:** el nodo mandaba el mensaje en Markdown, y el `_` de `view_type` en el enlace se interpretó como cursiva sin cerrar ("can't parse entities"). Lo pasé a HTML, donde solo `<`, `>` y `&` son especiales, y usé la URL corta de Odoo 18 `/odoo/crm/<id>`. Es el mismo principio que la inyección SQL: los datos del usuario dentro de un formato deben escaparse o ir en un formato que no los interprete.
- **El JSON exportado no lleva secretos:** solo referencias a las credenciales (id + nombre). El `chat_id` de Telegram se sustituye por `TU_CHAT_ID` antes de subirlo.

**Mejoras futuras:** autenticación en el webhook (cabecera con un token), deduplicar leads por email, y guardar el idioma en un campo propio de Odoo.

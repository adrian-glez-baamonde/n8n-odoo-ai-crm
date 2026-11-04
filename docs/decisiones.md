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

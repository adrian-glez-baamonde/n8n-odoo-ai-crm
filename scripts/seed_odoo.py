"""
Carga datos de prueba en el CRM de Odoo para "Moda Norte".

- Crea las etiquetas CRM (Pedido, Devolución, Mayorista, Queja, Información).
- Crea ~20 oportunidades de ejemplo con distintas prioridades, etapas y fechas.
- Es idempotente: si algo ya existe (por nombre), no lo duplica.

Usa la API externa de Odoo (XML-RPC) autenticándose con una API key.
Solo librería estándar de Python: no hace falta instalar nada.

Uso (desde la raíz del repo, con los contenedores levantados):
    python scripts/seed_odoo.py
"""

import subprocess
import sys
import xmlrpc.client
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Prioridad de Odoo (crm.lead.priority): '0' sin estrellas ... '3' tres estrellas.
# Mismo mapeo que usará el flujo de n8n en la fase 3.
PRIORIDAD = {"baja": "1", "media": "2", "alta": "3"}

ETIQUETAS = {  # nombre -> color (índice de la paleta de Odoo)
    "Pedido": 10,
    "Devolución": 2,
    "Mayorista": 4,
    "Queja": 1,
    "Información": 7,
}

# (nombre, contacto, empresa, email, teléfono, mensaje, etiqueta, prioridad, etapa, días atrás, importe)
# etapa = posición en el pipeline: 0 Nuevo, 1 Calificado, 2 Propuesta, 3 Ganado
LEADS = [
    ("Pedido 3 abrigos de lana talla M", "Lucía Fernández", None, "lucia.fernandez@ejemplo.com", "+34 611 234 567",
     "Hola, quiero pedir 3 abrigos de lana gris en talla M. ¿Tenéis stock para envío esta semana?", "Pedido", "media", 1, 2, 267.0),
    ("Pedido no recibido tras 15 días", "Javier Ruiz", None, "jruiz@ejemplo.com", "+34 622 345 678",
     "Hice el pedido #4512 hace 15 días y todavía no me ha llegado. Nadie me responde al teléfono. Es inaceptable.", "Queja", "alta", 0, 1, 0.0),
    ("Devolución vaqueros talla incorrecta", "Marta López", None, "marta.lopez@ejemplo.com", "+34 633 456 789",
     "Me llegaron unos vaqueros en talla 40 y pedí la 38. ¿Cómo hago la devolución?", "Devolución", "media", 0, 3, 0.0),
    ("Tienda Boutique Aurora: 200 camisetas básicas", "Carmen Díaz", "Boutique Aurora SL", "compras@boutiqueaurora.es", "+34 944 112 233",
     "Somos una boutique en Bilbao y queremos 200 camisetas básicas de algodón en varios colores. ¿Precio mayorista?", "Mayorista", "alta", 2, 4, 1800.0),
    ("Consulta guía de tallas de vestidos", "Ana Martín", None, "ana.martin@ejemplo.com", None,
     "¿Las tallas de los vestidos son europeas? Normalmente uso una S.", "Información", "baja", 0, 6, 0.0),
    ("Abrigo llegó con una costura rota", "Pedro Sánchez", None, "pedro.sanchez@ejemplo.com", "+34 644 567 890",
     "El abrigo que compré tiene una costura abierta en la manga. Quiero un cambio o el reembolso.", "Queja", "alta", 1, 2, 0.0),
    ("Pedido 2 jerséis de punto para regalo", "Elena Gómez", None, "elena.gomez@ejemplo.com", "+34 655 678 901",
     "Quiero 2 jerséis de punto beige, uno talla S y otro M. ¿Podéis envolverlos para regalo?", "Pedido", "baja", 3, 9, 119.8),
    ("Order: 4 linen shirts size L", "James Walker", None, "james.walker@example.co.uk", "+44 7700 900123",
     "Hi, I'd like to order 4 linen shirts in size L, white and navy. Do you ship to the UK?", "Pedido", "media", 1, 4, 196.0),
    ("Cadena Urbana Style: colección otoño", "Raúl Ortega", "Urbana Style SA", "raul.ortega@urbanastyle.es", "+34 915 223 344",
     "Tenemos 5 tiendas en Madrid y nos interesa la colección de otoño completa. ¿Podemos hablar de condiciones?", "Mayorista", "alta", 1, 0, 12500.0),
    ("Cargo duplicado en la tarjeta", "Sofía Navarro", None, "sofia.navarro@ejemplo.com", "+34 666 789 012",
     "Me habéis cobrado dos veces el mismo pedido (89,90 €). Necesito que me devolváis uno de los cargos ya.", "Queja", "alta", 0, 0, 0.0),
    ("Devolución bolso por cambio de opinión", "Laura Romero", None, "laura.romero@ejemplo.com", None,
     "Compré un bolso hace una semana y no me convence el color. ¿Puedo devolverlo aunque no tenga defecto?", "Devolución", "baja", 1, 5, 0.0),
    ("Horario y dirección de la tienda física", "Diego Torres", None, "diego.torres@ejemplo.com", None,
     "¿Tenéis tienda física en Oviedo? ¿Qué horario tiene?", "Información", "baja", 3, 12, 0.0),
    ("Pedido vestido de fiesta para boda", "Irene Molina", None, "irene.molina@ejemplo.com", "+34 677 890 123",
     "Necesito el vestido verde esmeralda en talla 36 antes del día 20 para una boda. ¿Llegaría a tiempo?", "Pedido", "alta", 2, 1, 129.0),
    ("Return: wrong colour received", "Emily Clarke", None, "emily.clarke@example.com", None,
     "I ordered a red scarf but received a brown one. How can I return it?", "Devolución", "media", 0, 2, 0.0),
    ("Uniformes para Hotel Mirador", "Andrés Vega", "Hotel Mirador SL", "rrhh@hotelmirador.es", "+34 985 334 455",
     "Buscamos proveedor para 60 uniformes (camisa y pantalón) para el personal del hotel.", "Mayorista", "media", 2, 8, 4200.0),
    ("¿Hacéis envíos a Canarias?", "Paula Castro", None, "paula.castro@ejemplo.com", None,
     "Vivo en Tenerife. ¿Hacéis envíos a Canarias y cuánto cuestan?", "Información", "baja", 0, 3, 0.0),
    ("Atención al cliente no responde", "Sergio Iglesias", None, "sergio.iglesias@ejemplo.com", "+34 688 901 234",
     "Llevo tres correos sin respuesta sobre mi devolución. Si no me contestáis, pondré una reclamación.", "Queja", "media", 0, 5, 0.0),
    ("Pedido zapatillas edición limitada", "Nuria Herrera", None, "nuria.herrera@ejemplo.com", "+34 699 012 345",
     "¿Os quedan zapatillas de la edición limitada en talla 39? Quiero 1 par.", "Pedido", "media", 3, 15, 95.0),
    ("Devolución pedido completo", "Alberto Ramos", None, "alberto.ramos@ejemplo.com", "+34 600 123 456",
     "Quiero devolver el pedido entero (3 prendas), ninguna me queda bien. ¿Me enviáis etiqueta de devolución?", "Devolución", "media", 1, 10, 0.0),
    ("Programa de puntos y descuentos", "Cristina Gil", None, "cristina.gil@ejemplo.com", None,
     "¿Tenéis algún programa de fidelización o código de descuento para la primera compra?", "Información", "baja", 0, 1, 0.0),
]


def cargar_env(path: Path) -> dict:
    """Lee un .env sencillo (CLAVE=valor) sin dependencias externas."""
    if not path.exists():
        sys.exit(f"No encuentro {path}. Copia .env.example a .env y rellénalo.")
    env = {}
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            env[clave.strip()] = valor.strip()
    return env


def main() -> None:
    env = cargar_env(ROOT / ".env")
    faltan = [k for k in ("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_API_KEY") if not env.get(k)]
    if faltan:
        sys.exit(f"Faltan variables en .env: {', '.join(faltan)}")

    url, db, user, key = env["ODOO_URL"], env["ODOO_DB"], env["ODOO_USER"], env["ODOO_API_KEY"]

    # 1) Autenticación: /xmlrpc/2/common devuelve el uid del usuario.
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    uid = common.authenticate(db, user, key, {})
    if not uid:
        sys.exit("Autenticación fallida: revisa ODOO_DB, ODOO_USER (login/email) y ODOO_API_KEY.")
    print(f"Conectado a {url} (db={db}) como uid={uid}")

    # 2) /xmlrpc/2/object.execute_kw(db, uid, key, modelo, método, args, kwargs) llama al ORM.
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    def call(model, method, *args, **kwargs):
        return models.execute_kw(db, uid, key, model, method, list(args), kwargs)

    # --- Etiquetas ---
    tag_ids = {}
    for nombre, color in ETIQUETAS.items():
        existentes = call("crm.tag", "search", [("name", "=", nombre)], limit=1)
        if existentes:
            tag_ids[nombre] = existentes[0]
            print(f"  = etiqueta '{nombre}' ya existe")
        else:
            tag_ids[nombre] = call("crm.tag", "create", {"name": nombre, "color": color})
            print(f"  + etiqueta '{nombre}' creada")
        # El nombre de la etiqueta es traducible (en BD es JSONB: {"en_US": ..., "es_ES": ...}).
        # Sin contexto de idioma solo se guarda en_US; guardamos también es_ES para que
        # las consultas SQL del asistente (fase 4) funcionen con cualquiera de los dos.
        call("crm.tag", "write", [tag_ids[nombre]], {"name": nombre},
             context={"lang": "es_ES"})

    # --- Etapas del pipeline (las crea Odoo al instalar CRM), ordenadas ---
    etapas = call("crm.stage", "search_read", [], fields=["name"], order="sequence, id")
    if len(etapas) < 4:
        sys.exit("Esperaba al menos 4 etapas en el CRM. ¿Está instalado el módulo CRM?")

    # --- Oportunidades ---
    nuevas = []  # (id, días atrás) de las creadas en esta ejecución
    for (nombre, contacto, empresa, email, tel, mensaje,
         etiqueta, prioridad, etapa, dias, importe) in LEADS:
        # active_test=False: también encuentra leads archivados/perdidos, para no duplicarlos.
        ya = call("crm.lead", "search", [("name", "=", nombre)], limit=1,
                  context={"active_test": False})
        if ya:
            print(f"  = lead '{nombre}' ya existe")
            continue
        lead_id = call("crm.lead", "create", {
            "type": "opportunity",
            "name": nombre,
            "contact_name": contacto,
            "partner_name": empresa or False,
            "email_from": email,
            "phone": tel or False,
            "description": mensaje,
            "priority": PRIORIDAD[prioridad],
            "tag_ids": [(6, 0, [tag_ids[etiqueta]])],  # comando 6 = reemplazar por esta lista
            "stage_id": etapas[etapa]["id"],
            "expected_revenue": importe,
        })
        nuevas.append((lead_id, dias))
        print(f"  + lead '{nombre}' creado (id={lead_id})")

    # --- Fechas de creación variadas (solo para los leads nuevos) ---
    # El ORM de Odoo no deja escribir create_date por la API (es un campo "mágico"
    # que gestiona él). Para tener datos realistas de "esta semana / este mes",
    # lo ajustamos con un UPDATE directo en Postgres. Solo para datos de demo.
    if nuevas:
        retrasar_fechas(env, db, nuevas)

    print(f"\nListo: {len(nuevas)} leads nuevos, {len(LEADS) - len(nuevas)} ya existían.")


def retrasar_fechas(env: dict, db: str, nuevas: list) -> None:
    valores = ", ".join(f"({i}, {d})" for i, d in nuevas)
    sql = (
        "UPDATE crm_lead l SET create_date = now() - make_interval(days => v.d) "
        f"FROM (VALUES {valores}) AS v(id, d) WHERE l.id = v.id;"
    )
    cmd = ["docker", "compose", "exec", "-T", "db",
           "psql", "-U", env.get("POSTGRES_USER", "odoo"), "-d", db, "-c", sql]
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True)
        print(f"  ~ fechas de creación ajustadas ({out.stdout.strip()})")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        detalle = getattr(e, "stderr", "") or str(e)
        print(f"  ! No se pudieron ajustar las fechas (los leads se han creado igual): {detalle.strip()}")


if __name__ == "__main__":
    main()

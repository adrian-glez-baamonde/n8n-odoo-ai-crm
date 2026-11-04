// ─────────────────────────────────────────────────────────────
// Configuración: URLs de producción de los flujos de n8n.
// (Si importas los flujos en otra instalación, la URL del chat cambia:
//  cópiala del nodo "When chat message received" del flujo 02.)
// ─────────────────────────────────────────────────────────────
const CONFIG = {
  CONTACT_WEBHOOK_URL: 'http://localhost:5678/webhook/contacto',
  CHAT_WEBHOOK_URL: 'http://localhost:5678/webhook/1d5015a8-695d-4d4f-99f2-489b2fcfd492/chat',
  CHAT_LIB_URL: 'https://cdn.jsdelivr.net/npm/@n8n/chat@1.43.1/dist/chat.bundle.es.js',
  TIMEOUT_MS: 30000, // la clasificación con IA tarda unos segundos
};

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ── Formulario de contacto (index.html) → flujo 01 ──────────
const form = document.getElementById('contact-form');
if (form) {
  const status = document.getElementById('form-status');
  const button = form.querySelector('button[type="submit"]');

  const showStatus = (type, text) => {
    status.hidden = false;
    status.className = `form-status is-${type}`;
    status.textContent = text;
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const data = {
      nombre: form.nombre.value.trim(),
      email: form.email.value.trim(),
      telefono: form.telefono.value.trim(),
      mensaje: form.mensaje.value.trim(),
    };

    // Validación en el navegador (comodidad para el usuario).
    // La validación que cuenta es la del servidor: el flujo 01 vuelve a comprobarlo.
    if (!data.nombre || !EMAIL_RE.test(data.email) || !data.mensaje) {
      showStatus('error', 'Revisa los campos: nombre, un email válido y el mensaje son obligatorios.');
      return;
    }

    button.disabled = true;
    button.textContent = 'Enviando…';
    status.hidden = true;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), CONFIG.TIMEOUT_MS);

    try {
      const res = await fetch(CONFIG.CONTACT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
        signal: controller.signal,
      });

      if (res.ok) {
        form.reset();
        showStatus('success', '¡Gracias! Hemos recibido tu mensaje y te responderemos en menos de 24 horas.');
      } else if (res.status === 400) {
        showStatus('error', 'Revisa el email y el mensaje: parece que falta algún dato.');
      } else {
        // 500 "Error in workflow" u otros: el equipo ya recibe un aviso por Telegram (flujo 99).
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (err) {
      console.error('Error enviando el formulario:', err);
      showStatus('error', 'Ahora mismo no podemos recibir tu mensaje. Inténtalo de nuevo en unos minutos.');
    } finally {
      clearTimeout(timer);
      button.disabled = false;
      button.textContent = 'Enviar mensaje';
    }
  });
}

// ── Chat del asistente (interno.html) → flujo 02 ─────────────
const chatTarget = document.getElementById('n8n-chat');
if (chatTarget) {
  const { createChat } = await import(CONFIG.CHAT_LIB_URL);
  createChat({
    webhookUrl: CONFIG.CHAT_WEBHOOK_URL,
    target: '#n8n-chat',
    mode: 'fullscreen',
    showWelcomeScreen: false,
    loadPreviousSession: false,
    initialMessages: [
      '¡Hola! Soy el asistente del CRM de Moda Norte.',
      'Puedo consultar leads y crear oportunidades nuevas. ¿Qué necesitas?',
    ],
    i18n: {
      en: {
        title: 'Asistente CRM',
        subtitle: 'Consultas en lenguaje natural sobre Odoo',
        footer: '',
        getStarted: 'Nueva conversación',
        inputPlaceholder: 'Escribe tu pregunta…',
        closeButtonTooltip: 'Cerrar',
      },
    },
  });
}

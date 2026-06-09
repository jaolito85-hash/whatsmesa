const state = {
  lastCount: 0,
  billing: null,
  failedRefreshes: 0,
  initialized: false,
};

// ---- Som de comanda nova (cozinha barulhenta não fica olhando tela) ----
// O navegador só libera áudio depois de um toque na página; o primeiro
// clique em qualquer lugar "destrava" o sino.
let audioCtx = null;

function ensureAudio() {
  if (!audioCtx) {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (error) {
      audioCtx = null;
    }
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume();
  }
}

function beepNewTicket() {
  if (!audioCtx || audioCtx.state !== "running") return;
  [0, 0.25].forEach((delay) => {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.frequency.value = 880;
    const t = audioCtx.currentTime + delay;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.6, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
    osc.start(t);
    osc.stop(t + 0.24);
  });
}

const sectorLabels = {
  bar: "Bar",
  cozinha: "Cozinha",
  salao: "Salão",
  caixa: "Caixa",
};

const billingStatusLabels = {
  ativo: "Ativo",
  aguardando_setup: "Aguardando setup",
  suspenso: "Suspenso",
  cancelado: "Cancelado",
};

const billingStatusLines = {
  ativo: "Conta em dia. Cada mesa aberta é cobrada por R$ 3,97.",
  aguardando_setup:
    "Aguardando pagamento da taxa de ativação. O bot ainda não aceita pedidos.",
  suspenso:
    "Conta suspensa. O bot responde pedindo para chamar um atendente no WhatsApp.",
  cancelado: "Conta cancelada. Entre em contato para reativar.",
};

const monthNames = [
  "jan",
  "fev",
  "mar",
  "abr",
  "mai",
  "jun",
  "jul",
  "ago",
  "set",
  "out",
  "nov",
  "dez",
];

function timeLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function elapsedMinutes(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
}

function relativeLabel(value) {
  const mins = elapsedMinutes(value);
  if (mins === null) return "";
  if (mins < 1) return "agora";
  if (mins === 1) return "há 1 min";
  return `há ${mins} min`;
}

function elapsedBucket(item) {
  const mins = elapsedMinutes(item.horario);
  if (mins === null) return "fresh";
  const urgent = item.status === "pronto" || item.status === "em_atendimento";
  const warnAt = urgent ? 2 : 3;
  const lateAt = urgent ? 5 : 7;
  if (mins >= lateAt) return "late";
  if (mins >= warnAt) return "warn";
  return "fresh";
}

function statusLabel(value) {
  return String(value || "").replaceAll("_", " ");
}

function actionLabel(item, next) {
  if (item.kind === "request") {
    if (next === "em_atendimento") return "Atender";
    if (next === "concluida")
      return item.tipo === "fechar_conta" ? "Fechar mesa 💰" : "Concluir";
  }
  return statusLabel(next);
}

function ticketHtml(item) {
  const next = item.next_status;
  const actionTarget = item.kind === "item" ? "items" : "requests";
  const nextLabel = next ? actionLabel(item, next) : "ok";
  const bucket = elapsedBucket(item);
  return `
    <article class="ticket" data-status="${item.status}" data-elapsed="${bucket}">
      <div class="ticket-top">
        <span class="mesa">Mesa ${item.mesa}</span>
        <span class="status">${statusLabel(item.status)}</span>
      </div>
      <h3>${item.quantidade > 1 ? `${item.quantidade}x ` : ""}${escapeHtml(item.titulo)}</h3>
      <p>${escapeHtml(item.observacoes || "Sem observações")} · <span class="elapsed">${relativeLabel(item.horario)}</span></p>
      <div class="actions">
        ${
          next
            ? `<button data-update="${actionTarget}" data-id="${item.id}" data-status="${next}">${nextLabel}</button>`
            : `<button disabled>finalizado</button>`
        }
        <button class="secondary" data-update="${actionTarget}" data-id="${item.id}" data-status="${
          item.kind === "item" ? "cancelado" : "cancelada"
        }">×</button>
      </div>
    </article>
  `;
}

function pendingHtml(order) {
  const items = (order.items || [])
    .map((item) => `${item.quantidade} ${item.nome_snapshot}`)
    .join(", ");
  return `
    <article class="pending-chip">
      <strong>Mesa ${order.mesa_numero}</strong>
      <p>${escapeHtml(items || order.texto_original)}</p>
      <div class="actions">
        <button data-confirm-order="${order.id}" data-mesa="${order.mesa_numero}">Enviar pra cozinha ✓</button>
      </div>
    </article>
  `;
}

async function confirmDraft(orderId, mesaNumero) {
  const ok = confirm(
    `Confirmar o pedido da mesa ${mesaNumero} pelo cliente e enviar para a cozinha?`,
  );
  if (!ok) return;
  const response = await fetch(`/api/orders/${orderId}/confirm`, { method: "POST" });
  if (!response.ok) throw new Error("Falha ao confirmar o pedido");
  await refreshDashboard();
}

function renderDashboard(data) {
  const columns = data.columns || {};
  let total = 0;

  Object.keys(sectorLabels).forEach((sector) => {
    const list = columns[sector] || [];
    total += list.length;
    const target = document.getElementById(`${sector}-list`);
    const count = document.querySelector(`[data-count="${sector}"]`);
    if (count) count.textContent = `${sectorLabels[sector]} ${list.length}`;
    if (!target) return;
    target.innerHTML = list.length
      ? list.map(ticketHtml).join("")
      : `<div class="empty">Nada novo por aqui.</div>`;
  });

  const pending = document.getElementById("pending-orders");
  const pendingOrders = data.pending_orders || [];
  if (pending) {
    pending.innerHTML = pendingOrders.length
      ? pendingOrders.map(pendingHtml).join("")
      : `<div class="empty">Nenhum rascunho esperando confirmação.</div>`;
  }

  const wa = data.whatsapp;
  const waBanner = document.getElementById("whatsapp-banner");
  if (waBanner && wa) {
    waBanner.hidden = !(wa.configured && (wa.state === "close" || wa.state === "connecting"));
  }

  // O primeiro render (carga da página) só calibra o contador — não apita.
  // Depois disso, QUALQUER aumento apita, inclusive a primeira comanda do
  // turno com o painel vazio (0 -> 1).
  if (state.initialized && total > state.lastCount) {
    beepNewTicket();
  }
  state.initialized = true;
  state.lastCount = total;
}

async function refreshDashboard() {
  try {
    const response = await fetch("/api/dashboard");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.failedRefreshes = 0;
    const offline = document.getElementById("offline-banner");
    if (offline) offline.hidden = true;
    renderDashboard(data);
  } catch (error) {
    // Wi-fi do salão caiu: a tela congela mostrando dados velhos. Sem a tarja,
    // a equipe acha que está tranquilo enquanto chovem pedidos no servidor.
    state.failedRefreshes += 1;
    if (state.failedRefreshes >= 2) {
      const offline = document.getElementById("offline-banner");
      if (offline) offline.hidden = false;
    }
  }
}

function pendingValidationHtml(session) {
  const remote = String(session.cliente_whatsapp || "").replace(/\D/g, "");
  return `
    <article class="pending-chip pending-validation-chip">
      <strong>Mesa ${session.mesa_numero}</strong>
      <p>Cliente: ${escapeHtml(remote || "?")}</p>
      <div class="actions">
        <button data-validate="${session.id}">validar</button>
        <button class="secondary" data-reject="${session.id}">recusar</button>
      </div>
    </article>
  `;
}

async function refreshPendingValidation() {
  try {
    const response = await fetch("/api/sessions/pending");
    if (!response.ok) return;
    const data = await response.json();
    const list = data.sessions || [];
    const band = document.getElementById("pending-validation-band");
    const target = document.getElementById("pending-validation");
    if (!band || !target) return;
    if (list.length === 0) {
      band.hidden = true;
      target.innerHTML = "";
      return;
    }
    band.hidden = false;
    target.innerHTML = list.map(pendingValidationHtml).join("");
  } catch (error) {
    console.error("Falha ao carregar mesas pendentes", error);
  }
}

async function validateSession(sessionId) {
  const response = await fetch(`/api/sessions/${sessionId}/validate`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Falha ao validar mesa");
  await refreshPendingValidation();
  await refreshDashboard();
}

async function rejectSession(sessionId) {
  const response = await fetch(`/api/sessions/${sessionId}/reject`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Falha ao recusar mesa");
  await refreshPendingValidation();
  await refreshDashboard();
}

function tablePillHtml(table) {
  const occupied = (table.sessoes_abertas || 0) > 0 || table.status !== "mesa_livre";
  return `
    <div class="table-pill" data-table-status="${table.status}">
      <a href="/qr/${table.id}" target="_blank" title="Abrir QR da mesa ${table.numero}">
        <strong>${table.numero}</strong>
      </a>
      <span>${statusLabel(table.status)}</span>
      ${
        occupied
          ? `<button class="secondary table-close" data-close-table="${table.id}" data-mesa="${table.numero}">fechar mesa</button>`
          : ""
      }
    </div>
  `;
}

async function refreshTables() {
  try {
    const response = await fetch("/api/tables");
    if (!response.ok) return;
    const data = await response.json();
    const grid = document.getElementById("table-grid");
    if (!grid) return;
    grid.innerHTML = (data.tables || []).map(tablePillHtml).join("");
  } catch (error) {
    console.error("Falha ao carregar mesas", error);
  }
}

async function closeTable(mesaId, mesaNumero) {
  const ok = confirm(
    `Fechar a mesa ${mesaNumero}? Todas as comandas abertas dela serão encerradas.`,
  );
  if (!ok) return;
  const response = await fetch(`/api/tables/${mesaId}/close`, { method: "POST" });
  if (!response.ok) throw new Error("Falha ao fechar a mesa");
  await refreshTables();
  await refreshDashboard();
}

async function updateStatus(kind, id, status) {
  const response = await fetch(`/api/${kind}/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) throw new Error("Falha ao atualizar status");
  await refreshDashboard();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatBRL(value) {
  const num = Number(value || 0);
  return num.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatPeriodo(periodo) {
  if (!periodo) return "--";
  const [year, month] = String(periodo).split("-");
  const idx = Number(month) - 1;
  const label = monthNames[idx] || month;
  return `${label}/${year}`;
}

function invoiceStatusLabel(status) {
  return {
    aberta: "aberta",
    enviada: "enviada",
    paga: "paga",
    cancelada: "cancelada",
  }[status] || status;
}

function renderBilling(usage, invoices) {
  state.billing = { usage, invoices };
  if (!usage) return;

  const account = usage.account || {};
  const status = account.status || "aguardando_setup";

  const pillDot = document.querySelector(".billing-pill-dot");
  const pillValue = document.getElementById("billing-pill-value");
  const pillMeta = document.getElementById("billing-pill-meta");
  if (pillDot) pillDot.setAttribute("data-billing-status", status);
  if (pillValue) pillValue.textContent = `R$ ${formatBRL(usage.valor_pedidos)}`;
  if (pillMeta) {
    pillMeta.textContent = `${usage.qtd_pedidos} mesa${usage.qtd_pedidos === 1 ? "" : "s"}`;
  }

  const badge = document.querySelector(".billing-badge");
  if (badge) {
    badge.setAttribute("data-billing-status", status);
    badge.textContent = billingStatusLabels[status] || status;
  }
  const statusLine = document.getElementById("billing-status-line");
  if (statusLine) {
    statusLine.textContent = billingStatusLines[status] || "";
  }

  document.getElementById("billing-amount-value").textContent = formatBRL(
    usage.valor_pedidos,
  );
  document.getElementById("billing-period").textContent = formatPeriodo(usage.periodo);
  document.getElementById("billing-orders-count").textContent = String(
    usage.qtd_pedidos,
  );
  document.getElementById("billing-unit-price").textContent = `R$ ${formatBRL(
    usage.preco_por_pedido,
  )}`;

  const setupBlock = document.getElementById("billing-setup");
  const setupStatus = document.getElementById("billing-setup-status");
  const setupValue = document.getElementById("billing-setup-value");
  const setupNote = document.getElementById("billing-setup-note");
  if (setupBlock && setupStatus && setupValue && setupNote) {
    const setupPaid = Boolean(account.setup_fee_paid_em);
    const setupFee = account.setup_fee != null ? account.setup_fee : 147;
    setupValue.textContent = `R$ ${formatBRL(setupFee)}`;
    if (setupPaid) {
      setupBlock.hidden = status !== "ativo";
      setupStatus.textContent = "pago";
      setupNote.textContent = "Taxa de ativação já foi paga. Cobrança recorrente por mesa aberta.";
    } else {
      setupBlock.hidden = false;
      setupStatus.textContent = "pendente";
      setupNote.textContent =
        "Assim que a taxa de ativação for paga, o bot libera pedidos no WhatsApp.";
    }
  }

  const list = document.getElementById("billing-invoices-list");
  if (list) {
    const items = Array.isArray(invoices) ? invoices : [];
    if (items.length === 0) {
      list.innerHTML = `<div class="empty">Ainda não há faturas fechadas.</div>`;
    } else {
      list.innerHTML = items
        .map((inv) => {
          const invStatus = inv.status || "aberta";
          return `
            <article class="billing-invoice-row">
              <span class="billing-invoice-period">${formatPeriodo(inv.periodo_ano_mes)}</span>
              <span class="billing-invoice-detail">${inv.qtd_pedidos} mesa${inv.qtd_pedidos === 1 ? "" : "s"}</span>
              <span class="billing-invoice-value">R$ ${formatBRL(inv.valor_total)}</span>
              <span class="billing-invoice-status" data-invoice-status="${invStatus}">${invoiceStatusLabel(invStatus)}</span>
            </article>
          `;
        })
        .join("");
    }
  }
}

async function refreshBilling() {
  try {
    const [usageRes, invoicesRes] = await Promise.all([
      fetch("/api/billing/usage"),
      fetch("/api/billing/invoices"),
    ]);
    const usage = usageRes.ok ? await usageRes.json() : null;
    const invoicesData = invoicesRes.ok ? await invoicesRes.json() : { invoices: [] };
    renderBilling(usage, invoicesData.invoices || []);
  } catch (error) {
    console.error("Falha ao carregar billing", error);
  }
}

function openBillingDrawer() {
  const drawer = document.getElementById("billing-drawer");
  const backdrop = document.getElementById("billing-backdrop");
  const pill = document.getElementById("billing-pill");
  if (!drawer || !backdrop) return;
  drawer.hidden = false;
  backdrop.hidden = false;
  if (pill) pill.setAttribute("aria-expanded", "true");
  refreshBilling();
}

function closeBillingDrawer() {
  const drawer = document.getElementById("billing-drawer");
  const backdrop = document.getElementById("billing-backdrop");
  const pill = document.getElementById("billing-pill");
  if (!drawer || !backdrop) return;
  drawer.hidden = true;
  backdrop.hidden = true;
  if (pill) pill.setAttribute("aria-expanded", "false");
}

document.addEventListener("click", (event) => {
  ensureAudio();
  const confirmBtn = event.target.closest("[data-confirm-order]");
  if (confirmBtn) {
    confirmDraft(confirmBtn.dataset.confirmOrder, confirmBtn.dataset.mesa).catch((error) =>
      alert(error.message),
    );
    return;
  }
  const update = event.target.closest("[data-update]");
  if (update) {
    updateStatus(update.dataset.update, update.dataset.id, update.dataset.status).catch((error) => {
      alert(error.message);
    });
    return;
  }
  const validate = event.target.closest("[data-validate]");
  if (validate) {
    validateSession(validate.dataset.validate).catch((error) => alert(error.message));
    return;
  }
  const reject = event.target.closest("[data-reject]");
  if (reject) {
    rejectSession(reject.dataset.reject).catch((error) => alert(error.message));
    return;
  }
  const closeBtn = event.target.closest("[data-close-table]");
  if (closeBtn) {
    closeTable(closeBtn.dataset.closeTable, closeBtn.dataset.mesa).catch((error) =>
      alert(error.message),
    );
    return;
  }
});

document.getElementById("demo-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const text = form.get("text");
  const remoteJid = form.get("remote_jid");
  const response = await fetch("/api/demo/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message_id: crypto.randomUUID(),
      remote_jid: remoteJid,
      text,
    }),
  });
  const data = await response.json();
  document.getElementById("demo-reply").textContent = data.reply || JSON.stringify(data, null, 2);
  event.currentTarget.elements.text.value = data.action === "session_activated"
    ? "Me vê 2 Corona e uma porção de batata"
    : data.action === "order_draft_created"
      ? "1"
      : "";
  await refreshDashboard();
});

document.getElementById("billing-pill")?.addEventListener("click", openBillingDrawer);
document.getElementById("billing-close")?.addEventListener("click", closeBillingDrawer);
document.getElementById("billing-backdrop")?.addEventListener("click", closeBillingDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeBillingDrawer();
});

renderDashboard(window.__INITIAL_DASHBOARD__ || {});
refreshBilling();
refreshPendingValidation();
refreshTables();
setInterval(refreshDashboard, 4000);
setInterval(refreshPendingValidation, 5000);
setInterval(refreshTables, 5000);
setInterval(refreshBilling, 30000);


const state = {
  lastCount: 0,
  billing: null,
};

const sectorLabels = {
  bar: "Bar",
  cozinha: "Cozinha",
  salao: "Salao",
  caixa: "Caixa",
};

const billingStatusLabels = {
  ativo: "Ativo",
  aguardando_setup: "Aguardando setup",
  suspenso: "Suspenso",
  cancelado: "Cancelado",
};

const billingStatusLines = {
  ativo: "Conta em dia. Pedidos confirmados sao cobrados por R$ 1,97.",
  aguardando_setup:
    "Aguardando pagamento da taxa de ativacao. O bot ainda nao aceita pedidos.",
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

function statusLabel(value) {
  return String(value || "").replaceAll("_", " ");
}

function ticketHtml(item) {
  const next = item.next_status;
  const actionTarget = item.kind === "item" ? "items" : "requests";
  const nextLabel = next ? statusLabel(next) : "ok";
  return `
    <article class="ticket">
      <div class="ticket-top">
        <span class="mesa">Mesa ${item.mesa}</span>
        <span class="status">${statusLabel(item.status)}</span>
      </div>
      <h3>${item.quantidade > 1 ? `${item.quantidade}x ` : ""}${escapeHtml(item.titulo)}</h3>
      <p>${escapeHtml(item.observacoes || "Sem observacoes")} · ${timeLabel(item.horario)}</p>
      <div class="actions">
        ${
          next
            ? `<button data-update="${actionTarget}" data-id="${item.id}" data-status="${next}">${nextLabel}</button>`
            : `<button disabled>finalizado</button>`
        }
        <button class="secondary" data-update="${actionTarget}" data-id="${item.id}" data-status="${
          item.kind === "item" ? "cancelado" : "cancelada"
        }">cancelar</button>
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
    </article>
  `;
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
      : `<div class="empty">Nenhum rascunho esperando confirmacao.</div>`;
  }

  state.lastCount = total;
}

async function refreshDashboard() {
  const response = await fetch("/api/dashboard");
  const data = await response.json();
  renderDashboard(data);
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
    pillMeta.textContent = `${usage.qtd_pedidos} pedido${usage.qtd_pedidos === 1 ? "" : "s"}`;
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
    const setupFee = account.setup_fee != null ? account.setup_fee : 99;
    setupValue.textContent = `R$ ${formatBRL(setupFee)}`;
    if (setupPaid) {
      setupBlock.hidden = status !== "ativo";
      setupStatus.textContent = "pago";
      setupNote.textContent = "Taxa de ativacao ja foi paga. Cobranca recorrente por pedido confirmado.";
    } else {
      setupBlock.hidden = false;
      setupStatus.textContent = "pendente";
      setupNote.textContent =
        "Assim que a taxa de ativacao for paga, o bot libera pedidos no WhatsApp.";
    }
  }

  const list = document.getElementById("billing-invoices-list");
  if (list) {
    const items = Array.isArray(invoices) ? invoices : [];
    if (items.length === 0) {
      list.innerHTML = `<div class="empty">Ainda nao ha faturas fechadas.</div>`;
    } else {
      list.innerHTML = items
        .map((inv) => {
          const invStatus = inv.status || "aberta";
          return `
            <article class="billing-invoice-row">
              <span class="billing-invoice-period">${formatPeriodo(inv.periodo_ano_mes)}</span>
              <span class="billing-invoice-detail">${inv.qtd_pedidos} pedido${inv.qtd_pedidos === 1 ? "" : "s"}</span>
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
  const button = event.target.closest("[data-update]");
  if (!button) return;
  updateStatus(button.dataset.update, button.dataset.id, button.dataset.status).catch((error) => {
    alert(error.message);
  });
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
    ? "Me ve 2 Corona e uma porcao de batata"
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
setInterval(refreshDashboard, 4000);
setInterval(refreshBilling, 30000);


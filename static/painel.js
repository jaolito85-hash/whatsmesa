// Modo Painel (KDS). Reusa a API /api/dashboard do painel normal, mas mostra
// um setor por vez, em tela cheia, com letras grandes — para rodar num tablet
// ou TV na cozinha/bar.

const SETORES = {
  cozinha: "Cozinha",
  bar: "Bar",
  salao: "Salão",
  caixa: "Caixa",
  todos: "Todos os setores",
};
const STORE_KEY = "klink_painel_setor";

const state = {
  setor: null,
  lastCount: 0,
  initialized: false,
  failed: 0,
};

// ---- Som de comanda nova (cozinha barulhenta não fica olhando tela) ----
let audioCtx = null;
function unlockAudio() {
  if (!audioCtx) {
    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    } catch (e) {
      audioCtx = null;
    }
  }
  if (audioCtx && audioCtx.state === "suspended") audioCtx.resume();
  if (audioCtx && audioCtx.state === "running") {
    const hint = document.getElementById("sound-hint");
    if (hint) hint.hidden = true;
  }
}
function beep() {
  if (!audioCtx || audioCtx.state !== "running") return;
  [0, 0.28].forEach((delay) => {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.frequency.value = 880;
    const t = audioCtx.currentTime + delay;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.6, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.24);
    osc.start(t);
    osc.stop(t + 0.26);
  });
}

// ---- Utilidades ----
function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
function elapsedMinutes(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
}
function relativeLabel(value) {
  const m = elapsedMinutes(value);
  if (m === null) return "";
  if (m < 1) return "agora";
  if (m === 1) return "há 1 min";
  return `há ${m} min`;
}
function elapsedBucket(item) {
  const m = elapsedMinutes(item.horario);
  if (m === null) return "fresh";
  const urgent = item.status === "pronto" || item.status === "em_atendimento";
  const warnAt = urgent ? 2 : 3;
  const lateAt = urgent ? 5 : 7;
  if (m >= lateAt) return "late";
  if (m >= warnAt) return "warn";
  return "fresh";
}
const STATUS_PT = {
  novo: "novo",
  em_preparo: "em preparo",
  pronto: "pronto",
  entregue: "entregue",
  nova: "nova",
  em_atendimento: "em atendimento",
};
function goLabel(item) {
  const n = item.next_status;
  if (item.kind === "request") {
    if (n === "em_atendimento") return "Atender";
    if (n === "concluida") return item.tipo === "fechar_conta" ? "Fechar mesa 💰" : "Concluir ✓";
  }
  if (n === "em_preparo") return "Começar 👨‍🍳";
  if (n === "pronto") return "Pronto ✓";
  if (n === "entregue") return "Entregue ✓";
  return "OK";
}

// ---- Render ----
function ticketHtml(item) {
  const kindTarget = item.kind === "item" ? "items" : "requests";
  const cancel = item.kind === "item" ? "cancelado" : "cancelada";
  const next = item.next_status;
  const qtd = item.quantidade > 1 ? `<span class="tk-qtd">${item.quantidade}x</span>` : "";
  const obs = (item.observacoes || "").trim();
  const obsHtml = obs && obs !== "Sem observações" ? `<p class="tk-obs">${escapeHtml(obs)}</p>` : "";
  const goBtn = next
    ? `<button class="tk-go" data-update="${kindTarget}" data-id="${item.id}" data-status="${next}">${goLabel(item)}</button>`
    : `<button class="tk-go" data-done="1" disabled>finalizado</button>`;
  return `
    <article class="tk" data-elapsed="${elapsedBucket(item)}">
      <div class="tk-top">
        <span class="tk-mesa">Mesa ${escapeHtml(item.mesa)}</span>
        <span class="tk-time">${relativeLabel(item.horario)}</span>
      </div>
      <div class="tk-body">
        <div class="tk-item">${qtd}${escapeHtml(item.titulo)}</div>
        ${obsHtml}
        <p class="tk-status">${STATUS_PT[item.status] || escapeHtml(item.status)}</p>
      </div>
      <div class="tk-actions">
        ${goBtn}
        <button class="tk-x" data-update="${kindTarget}" data-id="${item.id}" data-status="${cancel}" title="Cancelar">×</button>
      </div>
    </article>
  `;
}

function ticketsForSetor(columns) {
  let list;
  if (state.setor === "todos") {
    list = Object.keys(SETORES)
      .filter((k) => k !== "todos")
      .flatMap((k) => columns[k] || []);
  } else {
    list = columns[state.setor] || [];
  }
  // Mais antigo primeiro: o pedido mais velho é o mais urgente pra cozinha.
  return list.slice().sort((a, b) => {
    const ta = new Date(a.horario || 0).getTime();
    const tb = new Date(b.horario || 0).getTime();
    return ta - tb;
  });
}

function render(data) {
  const board = document.getElementById("board");
  const list = ticketsForSetor(data.columns || {});
  document.getElementById("ticket-count").textContent = String(list.length);

  board.innerHTML = list.length
    ? list.map(ticketHtml).join("")
    : `<div class="board-empty"><span>🍃</span>Nenhum pedido por aqui agora.</div>`;

  // Primeiro carregamento só calibra o contador (não apita). Depois, qualquer
  // aumento na fila deste setor apita.
  if (state.initialized && list.length > state.lastCount) beep();
  state.initialized = true;
  state.lastCount = list.length;
}

async function refresh() {
  try {
    const resp = await fetch("/api/dashboard", { headers: { "Cache-Control": "no-cache" } });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    state.failed = 0;
    document.getElementById("offline-banner").hidden = true;
    render(data);
  } catch (e) {
    state.failed += 1;
    if (state.failed >= 2) document.getElementById("offline-banner").hidden = false;
  }
}

async function updateStatus(kind, id, status) {
  const resp = await fetch(`/api/${kind}/${id}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!resp.ok) throw new Error("Falha ao atualizar o pedido");
  await refresh();
}

// ---- Setor (lembrado no aparelho) ----
function aplicarSetor(setor) {
  state.setor = setor;
  state.initialized = false;
  state.lastCount = 0;
  localStorage.setItem(STORE_KEY, setor);
  document.getElementById("setor-nome").textContent = SETORES[setor] || "—";
  document.getElementById("setor-picker").hidden = true;
  refresh();
}
function abrirPicker() {
  document.getElementById("setor-picker").hidden = false;
}

// ---- Relógio ----
function tickClock() {
  const el = document.getElementById("clock");
  if (el) {
    el.textContent = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }
}

// ---- Eventos ----
document.addEventListener("click", (event) => {
  unlockAudio();

  const pick = event.target.closest("[data-pick]");
  if (pick) {
    aplicarSetor(pick.dataset.pick);
    return;
  }
  const update = event.target.closest("[data-update]");
  if (update) {
    updateStatus(update.dataset.update, update.dataset.id, update.dataset.status).catch((e) =>
      alert(e.message),
    );
    return;
  }
});
document.getElementById("btn-trocar").addEventListener("click", abrirPicker);
document.getElementById("btn-tela").addEventListener("click", () => {
  if (document.fullscreenElement) {
    document.exitFullscreen?.();
  } else {
    document.documentElement.requestFullscreen?.();
  }
});

// ---- Service worker (PWA / abre offline) ----
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/painel/sw.js", { scope: "/painel/" }).catch(() => {});
  });
}

// ---- Arranque ----
const salvo = localStorage.getItem(STORE_KEY);
if (salvo && SETORES[salvo]) {
  aplicarSetor(salvo);
} else {
  abrirPicker();
}
document.getElementById("sound-hint").hidden = false;
tickClock();
setInterval(tickClock, 15000);
setInterval(refresh, 4000);

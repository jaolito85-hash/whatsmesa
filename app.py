from __future__ import annotations

import base64
import hmac
import json
import os
import re
import urllib.request
from datetime import timedelta
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from klink.audio_service import AudioService
from klink.billing_service import BillingService
from klink.config import get_settings
from klink.menu_service import MenuService
from klink.openai_interpreter import OpenAIInterpreter
from klink.order_service import OrderService
from klink.qr_service import QRService
from klink.restaurant_agent import RestaurantAgent
from klink.storage import DEMO_SLUG, Database
from klink.table_session_service import TableSessionService
from klink.sdr_agent import SDRAgent
from klink.whatsapp_adapter import WhatsAppAdapter


from klink.text_utils import format_brl as _format_brl


def team_message_for(result: dict) -> str | None:
    """Monta a mensagem de WhatsApp para a equipe (cozinha/garçom/caixa).

    É o caminho "sem tablet": o pedido confirmado vira uma comanda de texto no
    celular da cozinha — que já apita sozinho — em vez de existir só no painel.
    Devolve None quando a ação não interessa à equipe.
    """
    action = result.get("action")
    session = result.get("session") or {}
    mesa = session.get("mesa_numero")
    if mesa is None:
        return None

    if action == "order_confirmed" and result.get("order"):
        order = result["order"]
        lines = [f"🍽️ MESA {mesa} — pedido confirmado"]
        total = 0.0
        for item in order.get("items", []):
            if item.get("status") == "cancelado":
                continue
            line = f"{item['quantidade']}x {item['nome_snapshot']}"
            observacoes = (item.get("observacoes") or "").strip()
            if observacoes:
                line += f" ({observacoes})"
            lines.append(line)
            total += item["quantidade"] * float(item["preco_unitario_snapshot"])
        lines.append(f"Total parcial: R$ {_format_brl(total)}")
        return "\n".join(lines)

    if action == "account_requested":
        # A descrição do ticket já vem com o total ("Fechar conta da Mesa 12 —
        # Total R$ 121,00"): a equipe vê o valor sem abrir o painel.
        descricao = ((result.get("request") or {}).get("descricao") or "").strip()
        return f"💰 {descricao}" if descricao else f"💰 MESA {mesa} pediu a conta."

    if action in ("service_requested", "human_called") and result.get("request"):
        descricao = (result["request"].get("descricao") or "").strip()
        return f"🙋 {descricao}" if descricao else f"🙋 MESA {mesa} chamou atendimento."

    return None


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
    # Cookie de login da Área do Vendedor é assinado com esta chave. Em produção
    # use KLINK_SECRET_KEY; sem ela, a senha do painel serve de semente (secreta e
    # estável). O fallback de dev só vale fora de produção.
    app.secret_key = (
        settings.flask_secret_key or settings.dashboard_password or "klink-dev-secret"
    )
    # Cookie só viaja em HTTPS e fica invisível ao JavaScript (defesa básica).
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=not settings.dev_mode,
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )
    # Pasta com o Kit de Vendas (hub, apresentação, guia, imagens). Servida só
    # para vendedores autenticados, sob /vendedores/.
    material_vendas_dir = Path(__file__).resolve().parent / "material-vendas"
    if not settings.dev_mode and not settings.dashboard_password:
        # Sem senha de painel e fora de dev = painel aberto a qualquer um. Em produção
        # abortamos o boot (à prova de esquecimento); sob testes (pytest) apenas avisamos.
        if "PYTEST_CURRENT_TEST" in os.environ:
            app.logger.warning("KLINK_DASHBOARD_PASSWORD ausente (painel sem senha).")
        else:
            raise RuntimeError(
                "KLINK_DASHBOARD_PASSWORD obrigatória em produção: sem ela o painel fica "
                "aberto. Configure a senha (ou ligue KLINK_DEV_MODE=1 em desenvolvimento)."
            )
    if settings.dev_mode:
        app.logger.warning(
            "KLINK_DEV_MODE ligado: rotas /admin/* sem token e /api/demo/message ativa. "
            "NUNCA use em produção."
        )
    if not settings.dev_mode and not settings.require_table_validation:
        # Sem a validação, qualquer pessoa que descobrir o número do bot (está
        # impresso em todas as mesas) abre mesa de casa, manda a cozinha
        # preparar e gera cobrança — trote vira prejuízo.
        app.logger.warning(
            "KLINK_REQUIRE_TABLE_VALIDATION desligada: qualquer um abre mesa sem o "
            "garçom confirmar. Em produção, configure =true."
        )
    db = Database(settings.database_path)
    db.init_schema()
    db.migrate_legacy_data()
    db.seed_demo()

    billing = BillingService(db)
    table_sessions = TableSessionService(
        db,
        billing=billing,
        idle_ttl_hours=settings.session_idle_ttl_hours,
        require_validation=settings.require_table_validation,
    )
    menu = MenuService(db)
    orders = OrderService(db)
    interpreter = OpenAIInterpreter(settings)
    agent = RestaurantAgent(
        table_sessions=table_sessions,
        menu=menu,
        orders=orders,
        interpreter=interpreter,
        billing=billing,
    )
    whatsapp = WhatsAppAdapter(settings)
    sdr_agent = SDRAgent(settings)
    audio = AudioService(settings)
    qr = QRService(settings, table_sessions)

    # /vendedores tem login PRÓPRIO (senha do vendedor, não a do painel): por isso
    # escapa do Basic Auth de admin aqui e se protege sozinho lá embaixo.
    PUBLIC_PATHS = (
        "/",
        "/termos",
        "/privacidade",
        "/health",
        "/webhook",
        "/qr/",
        "/static/",
        "/vendedores",
        "/webhook/sdr",
    )

    def whatsapp_status() -> dict:
        """Situação REAL do WhatsApp, três estados honestos:

        - configured: as variáveis da Evolution estão preenchidas;
        - state: último estado reportado pela Evolution (open/connecting/close)
          ou "desconhecido" se o evento CONNECTION_UPDATE nunca chegou;
        - connected: True só quando o estado reportado é "open".
        """
        estado = db.get_estado("whatsapp_connection_state")
        state = (estado or {}).get("valor") or "desconhecido"
        return {
            "configured": settings.has_evolution,
            "state": state,
            "state_at": (estado or {}).get("atualizado_em"),
            "connected": settings.has_evolution and state == "open",
        }

    @app.before_request
    def enforce_dashboard_auth():
        if not settings.dashboard_auth_enabled:
            return None
        path = request.path or ""
        if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PATHS if p != "/"):
            return None
        auth = request.authorization
        if auth and auth.type == "basic":
            user_ok = hmac.compare_digest(auth.username or "", settings.dashboard_user)
            pass_ok = hmac.compare_digest(auth.password or "", settings.dashboard_password)
            if user_ok and pass_ok:
                return None
        return Response(
            "Autenticacao necessaria.",
            status=401,
            headers={"WWW-Authenticate": 'Basic realm="Klink"'},
        )

    @app.get("/")
    def landing():
        return render_template("landing.html")

    @app.get("/termos")
    def termos():
        return render_template("termos.html")

    @app.get("/privacidade")
    def privacidade():
        return render_template("privacidade.html")

    # ----------------------------------------------------------------------
    # Área do Vendedor: o Kit de Vendas (apresentação + guia) atrás de uma
    # senha SÓ dos vendedores. Eles abrem klinkai.com.br/vendedores no celular,
    # digitam a senha uma vez e ganham acesso ao material — e a nada mais.
    # ----------------------------------------------------------------------
    def _vendedor_logado() -> bool:
        return bool(session.get("vendedor_ok"))

    @app.route("/vendedores", methods=["GET", "POST"])
    def vendedores_login():
        if not settings.vendedores_enabled:
            return Response(
                "Área do vendedor ainda não configurada.",
                status=503,
                mimetype="text/plain; charset=utf-8",
            )
        if request.method == "POST":
            senha = (request.form.get("senha") or "").strip()
            if hmac.compare_digest(senha, settings.vendedor_password):
                session.permanent = True
                session["vendedor_ok"] = True
                return redirect(url_for("vendedores_hub"))
            return render_template("vendedores_login.html", erro=True), 401
        if _vendedor_logado():
            return redirect(url_for("vendedores_hub"))
        return render_template("vendedores_login.html", erro=False)

    @app.get("/vendedores/sair")
    def vendedores_sair():
        session.pop("vendedor_ok", None)
        return redirect(url_for("vendedores_login"))

    @app.get("/vendedores/")
    def vendedores_hub():
        if not settings.vendedores_enabled or not _vendedor_logado():
            return redirect(url_for("vendedores_login"))
        return send_from_directory(material_vendas_dir, "index.html")

    @app.get("/vendedores/<path:arquivo>")
    def vendedores_arquivo(arquivo: str):
        if not settings.vendedores_enabled or not _vendedor_logado():
            return redirect(url_for("vendedores_login"))
        # send_from_directory bloqueia path traversal (../) por conta própria.
        return send_from_directory(material_vendas_dir, arquivo)

    @app.get("/dashboard")
    def dashboard():
        restaurant = table_sessions.restaurant()
        return render_template(
            "dashboard.html",
            restaurant=restaurant,
            is_demo=restaurant.get("slug") == DEMO_SLUG,
            tables=table_sessions.list_tables(),
            dashboard=orders.dashboard(),
            public_base_url=settings.public_base_url,
        )

    # ----------------------------------------------------------------------
    # Modo Painel (KDS): a mesma fila de pedidos do /dashboard, porém em tela
    # cheia, letras grandes e um setor por vez — pensada pra rodar num tablet
    # ou TV na cozinha/bar, como um totem. Reusa a API /api/dashboard.
    # ----------------------------------------------------------------------
    @app.get("/painel")
    def painel_redirect():
        # Canônico é /painel/ (o escopo do PWA e do service worker termina em /).
        return redirect("/painel/")

    @app.get("/painel/")
    def painel():
        restaurant = table_sessions.restaurant()
        return render_template(
            "painel.html",
            restaurant=restaurant,
            is_demo=restaurant.get("slug") == DEMO_SLUG,
        )

    @app.get("/painel/sw.js")
    def painel_service_worker():
        # O service worker precisa ser servido de dentro de /painel/ para poder
        # controlar essa área (o escopo de um SW é a pasta de onde ele vem).
        resp = send_from_directory(app.static_folder, "painel-sw.js")
        resp.headers["Content-Type"] = "application/javascript"
        resp.headers["Service-Worker-Allowed"] = "/painel/"
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.get("/config")
    def config_page():
        restaurant = table_sessions.restaurant()
        return render_template(
            "config.html",
            restaurant=restaurant,
            is_demo=restaurant.get("slug") == DEMO_SLUG,
            bot_phone=qr.bot_phone(),
            whatsapp=whatsapp_status(),
        )

    @app.post("/api/restaurant")
    def api_update_restaurant():
        restaurant = table_sessions.restaurant()
        payload = request.get_json(silent=True) or request.form
        nome = (payload.get("nome") or "").strip()
        telefone_raw = payload.get("telefone_whatsapp")
        equipe_raw = payload.get("whatsapp_equipe")
        if not nome:
            return jsonify({"ok": False, "reason": "nome_obrigatorio"}), 400
        telefone = None
        if telefone_raw is not None:
            telefone = "".join(ch for ch in str(telefone_raw) if ch.isdigit())
        equipe = None
        if equipe_raw is not None:
            equipe = str(equipe_raw).strip()
            # Grupo do WhatsApp tem id no formato 1234...@g.us — só esse formato
            # passa com "@"; número comum fica só com dígitos. Qualquer outra
            # coisa é rejeitada para não virar destino de envio inválido.
            if "@" in equipe:
                if not re.fullmatch(r"\d+@g\.us", equipe):
                    return jsonify(
                        {
                            "ok": False,
                            "reason": "whatsapp_equipe_invalido",
                            "message": "Use só números (5511...) ou o id de um grupo (...@g.us).",
                        }
                    ), 400
            else:
                equipe = "".join(ch for ch in equipe if ch.isdigit())
        was_demo = restaurant.get("slug") == DEMO_SLUG
        db.update_restaurant(
            restaurant["id"],
            nome=nome,
            telefone_whatsapp=telefone,
            whatsapp_equipe=equipe,
        )
        updated = table_sessions.restaurant()
        # Onboarding de cliente REAL (saiu do estado demo): a trava dos R$ 147
        # passa a valer — a conta volta para 'aguardando_setup' até o Pix cair
        # e o /admin/billing/setup-paid registrar o pagamento de verdade.
        if was_demo and updated.get("slug") != DEMO_SLUG:
            billing.require_setup_if_unpaid(restaurant["id"])
        return jsonify({"ok": True, "restaurant": updated, "bot_phone": qr.bot_phone()})

    @app.get("/cardapio")
    def cardapio_page():
        restaurant = table_sessions.restaurant()
        return render_template(
            "cardapio.html",
            restaurant=restaurant,
            is_demo=restaurant.get("slug") == DEMO_SLUG,
        )

    def _parse_product_payload():
        data = request.get_json(silent=True) or {}
        nome = (data.get("nome") or "").strip()
        if not nome:
            return None, ("nome_obrigatorio", "Informe o nome do produto.")
        try:
            preco = float(str(data.get("preco")).replace(",", "."))
        except (TypeError, ValueError):
            return None, ("preco_invalido", "Preço inválido.")
        if preco < 0:
            return None, ("preco_invalido", "O preço não pode ser negativo.")
        setor = data.get("setor")
        if setor not in ("bar", "cozinha"):
            setor = "bar"
        aliases_raw = data.get("aliases")
        if isinstance(aliases_raw, str):
            aliases = aliases_raw.split(",")
        else:
            aliases = list(aliases_raw or [])
        return {
            "nome": nome,
            "preco": preco,
            "setor": setor,
            "categoria": (data.get("categoria") or "").strip(),
            "descricao": (data.get("descricao") or "").strip(),
            "disponivel": bool(data.get("disponivel", True)),
            "aliases": aliases,
        }, None

    @app.post("/api/products")
    def api_create_product():
        restaurant = table_sessions.restaurant()
        parsed, err = _parse_product_payload()
        if err:
            return jsonify({"ok": False, "reason": err[0], "message": err[1]}), 400
        pid = db.create_product(restaurant["id"], **parsed)
        return jsonify({"ok": True, "id": pid})

    @app.post("/api/products/<produto_id>")
    def api_update_product(produto_id: str):
        restaurant = table_sessions.restaurant()
        if not db.product_belongs_to(restaurant["id"], produto_id):
            return jsonify({"ok": False, "reason": "nao_encontrado"}), 404
        parsed, err = _parse_product_payload()
        if err:
            return jsonify({"ok": False, "reason": err[0], "message": err[1]}), 400
        db.update_product(produto_id, **parsed)
        return jsonify({"ok": True})

    @app.post("/api/products/<produto_id>/delete")
    def api_delete_product(produto_id: str):
        restaurant = table_sessions.restaurant()
        if not db.product_belongs_to(restaurant["id"], produto_id):
            return jsonify({"ok": False, "reason": "nao_encontrado"}), 404
        db.deactivate_product(produto_id)
        return jsonify({"ok": True})

    @app.get("/qrcodes")
    def qrcodes_page():
        restaurant = table_sessions.restaurant()
        tables = []
        for table in table_sessions.list_tables():
            tables.append(
                {
                    "id": table["id"],
                    "numero": table["numero"],
                    "nome": table.get("nome"),
                    "sessoes_abertas": table.get("sessoes_abertas", 0),
                    # Usa o id PERMANENTE da mesa (não o token rotativo): o QR impresso
                    # precisa continuar valendo depois que a mesa fecha e reabre.
                    "qr_url": qr.public_qr_url(table["id"]),
                }
            )
        return render_template(
            "qrcodes.html",
            restaurant=restaurant,
            tables=tables,
            bot_phone=qr.bot_phone(),
        )

    @app.get("/health")
    def health():
        sends_today = db.count_whatsapp_sends_today()
        limit = settings.evolution_daily_limit or 0
        usage_pct = round((sends_today / limit) * 100, 1) if limit > 0 else None
        wa = whatsapp_status()
        # "alerts" é o gancho para monitor externo (UptimeRobot etc.): basta
        # vigiar a palavra-chave "whatsapp_desconectado" no corpo da resposta.
        alerts = []
        if wa["configured"] and wa["state"] in ("close", "connecting"):
            alerts.append("whatsapp_desconectado")
        if usage_pct is not None and usage_pct >= 70:
            alerts.append("limite_diario_de_envios_alto")
        return jsonify(
            {
                "ok": True,
                "service": "klink",
                "alerts": alerts,
                "whatsapp": {
                    "configured": wa["configured"],
                    "connection_state": wa["state"],
                    "connection_state_at": wa["state_at"],
                    "connected": wa["connected"],
                    "sends_today": sends_today,
                    "daily_limit": limit,
                    "usage_pct": usage_pct,
                    "warning": usage_pct is not None and usage_pct >= 70,
                },
                "sessions": {
                    "active": db.count_active_sessions(),
                    "pending_validation": db.count_pending_sessions(),
                },
                "last_inbound_at": db.last_inbound_message_at(),
                "require_table_validation": settings.require_table_validation,
            }
        )

    @app.get("/api/dashboard")
    def api_dashboard():
        data = orders.dashboard()
        data["whatsapp"] = whatsapp_status()
        return jsonify(data)

    @app.get("/api/sessions/pending")
    def api_pending_sessions():
        return jsonify({"sessions": table_sessions.list_pending_sessions()})

    @app.post("/api/sessions/<session_id>/validate")
    def api_validate_session(session_id: str):
        session = table_sessions.validate_session(session_id)
        if not session:
            return jsonify({"ok": False, "reason": "not_found"}), 404
        if settings.has_evolution and session.get("cliente_whatsapp"):
            text = (
                f"Mesa {session['mesa_numero']} liberada. "
                "Pode pedir por audio ou texto."
            )
            try:
                send_result = whatsapp.send_message(session["cliente_whatsapp"], text)
                if send_result.get("sent"):
                    db.record_whatsapp_send(
                        remote_jid=session["cliente_whatsapp"],
                        sucesso=True,
                        restaurante_id=session.get("restaurante_id"),
                    )
            except Exception as exc:  # pragma: no cover - rede
                db.record_whatsapp_send(
                    remote_jid=session["cliente_whatsapp"],
                    sucesso=False,
                    erro=str(exc),
                    restaurante_id=session.get("restaurante_id"),
                )
                app.logger.exception("Falha ao notificar mesa validada: %s", exc)
        return jsonify({"ok": True, "session": session})

    @app.post("/api/sessions/<session_id>/reject")
    def api_reject_session(session_id: str):
        table_sessions.reject_session(session_id)
        return jsonify({"ok": True})

    @app.post("/api/tables")
    def api_create_tables():
        # Cadastro de mesas: ou em lote ({"ate_numero": 40} cria as que faltam
        # de 1 a 40), ou avulsa ({"numero": 101, "nome": "Varanda 1"}).
        restaurant = table_sessions.restaurant()
        unidade = db.primary_unit_for(restaurant["id"])
        if not unidade:
            return jsonify({"ok": False, "reason": "sem_unidade"}), 400
        payload = request.get_json(silent=True) or {}

        def _parse_num(value):
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                return None

        ate = _parse_num(payload.get("ate_numero"))
        if ate is not None:
            if not 1 <= ate <= 300:
                return jsonify(
                    {
                        "ok": False,
                        "reason": "numero_invalido",
                        "message": "Informe um total entre 1 e 300 mesas.",
                    }
                ), 400
            criadas = []
            for numero in range(1, ate + 1):
                mesa_id = db.create_table(restaurant["id"], unidade["id"], numero=numero)
                if mesa_id:
                    criadas.append(numero)
            return jsonify({"ok": True, "criadas": criadas, "total": ate})

        numero = _parse_num(payload.get("numero"))
        # O chat só entende mesas de 1 a 999 (o parser lê até 3 dígitos).
        if numero is None or not 1 <= numero <= 999:
            return jsonify(
                {
                    "ok": False,
                    "reason": "numero_invalido",
                    "message": "O número da mesa deve ser de 1 a 999.",
                }
            ), 400
        mesa_id = db.create_table(
            restaurant["id"],
            unidade["id"],
            numero=numero,
            nome=str(payload.get("nome") or ""),
        )
        if not mesa_id:
            return jsonify(
                {
                    "ok": False,
                    "reason": "ja_existe",
                    "message": f"A mesa {numero} já existe no salão.",
                }
            ), 400
        return jsonify({"ok": True, "id": mesa_id, "numero": numero})

    @app.post("/api/tables/<mesa_id>/rename")
    def api_rename_table(mesa_id: str):
        table = table_sessions.table_by_id(mesa_id)
        if not table:
            return jsonify({"ok": False, "reason": "nao_encontrada"}), 404
        payload = request.get_json(silent=True) or {}
        nome = str(payload.get("nome") or "").strip()
        # Nome em branco = apagar o apelido e voltar ao padrão "Mesa N". Antes
        # isso era rejeitado (nome_obrigatorio), então um apelido digitado por
        # engano ("Varanda 3") ficava preso para sempre, sem como remover.
        if not nome:
            nome = f"Mesa {table['numero']}"
        db.rename_table(mesa_id, nome)
        return jsonify({"ok": True, "nome": nome})

    @app.post("/api/tables/<mesa_id>/deactivate")
    def api_deactivate_table(mesa_id: str):
        table = table_sessions.table_by_id(mesa_id)
        if not table:
            return jsonify({"ok": False, "reason": "nao_encontrada"}), 404
        if not table_sessions.deactivate_table(mesa_id):
            return jsonify(
                {
                    "ok": False,
                    "reason": "mesa_em_uso",
                    "message": "Essa mesa tem comanda aberta. Feche a mesa antes de removê-la.",
                }
            ), 409
        return jsonify({"ok": True})

    @app.post("/api/tables/<mesa_id>/close")
    def api_close_table(mesa_id: str):
        # Fecha a mesa manualmente pelo painel (todas as sessões ativas dela).
        table = table_sessions.table_by_id(mesa_id)
        if not table:
            return jsonify({"ok": False, "reason": "nao_encontrada"}), 404
        closed = table_sessions.close_table(mesa_id)
        return jsonify({"ok": True, "sessoes_fechadas": closed})

    @app.get("/api/tables")
    def api_tables():
        tables = []
        for table in table_sessions.list_tables():
            table["qr_url"] = qr.public_qr_url(table["id"])
            table["whatsapp_url"] = qr.whatsapp_link_for_table(table["numero"])
            tables.append(table)
        return jsonify({"tables": tables})

    @app.get("/api/products")
    def api_products():
        restaurant = table_sessions.restaurant()
        return jsonify({"products": menu.products_for_restaurant(restaurant["id"])})

    @app.post("/api/orders/<order_id>/confirm")
    def api_confirm_order(order_id: str):
        # Destrava o rascunho que o cliente esqueceu de confirmar com "1": o
        # garçom confere na mesa e envia pra cozinha pelo painel. Antes, esse
        # pedido morria em rascunho e a comida nunca saía.
        order = orders.get_order(order_id)
        if not order:
            return jsonify({"ok": False, "reason": "nao_encontrado"}), 404
        if order["status"] != "aguardando_confirmacao_cliente":
            # Clique duplo ou pedido já confirmado: idempotente, sem comanda dupla.
            return jsonify({"ok": True, "reason": "ja_confirmado"})
        confirmed = orders.confirm_order(order_id)
        mesa = db.fetchone("select numero from mesas where id = ?", (confirmed["mesa_id"],))
        notify_team(
            {
                "action": "order_confirmed",
                "session": {"mesa_numero": mesa["numero"] if mesa else None},
                "order": confirmed,
            }
        )
        return jsonify({"ok": True, "order": {"id": confirmed["id"], "status": confirmed["status"]}})

    @app.post("/api/items/<item_id>/status")
    def api_update_item(item_id: str):
        payload = request.get_json(silent=True) or request.form
        orders.update_item_status(item_id, payload.get("status", ""))
        return jsonify({"ok": True})

    @app.post("/api/requests/<request_id>/status")
    def api_update_request(request_id: str):
        payload = request.get_json(silent=True) or request.form
        new_status = payload.get("status", "")
        existing = orders.get_request(request_id)
        orders.update_request_status(request_id, new_status)
        if (
            existing
            and existing.get("tipo") == "fechar_conta"
            and new_status == "concluida"
            and existing.get("sessao_mesa_id")
        ):
            table_sessions.close_session(existing["sessao_mesa_id"])
        return jsonify({"ok": True})

    def require_admin() -> None:
        expected = settings.admin_token
        if not expected:
            # Sem token configurado: so liberamos em modo de desenvolvimento
            # explicito (KLINK_DEV_MODE=1). Em producao, falta de token =
            # acesso negado (seguro por padrao). Assim, um deploy que esqueca o
            # KLINK_ADMIN_TOKEN nao deixa as rotas /admin/* (cobranca) abertas.
            if settings.dev_mode:
                return
            abort(403)
        provided = request.headers.get("X-Admin-Token", "")
        # compare_digest evita timing attack na comparacao do token de admin.
        if not hmac.compare_digest(provided, expected):
            abort(401)

    @app.get("/admin/backup")
    def admin_backup():
        # Baixa uma cópia consistente do banco (snapshot via API de backup do
        # SQLite, segura mesmo com o app escrevendo em WAL). Dá ao fundador um
        # backup fora da VPS em 10 segundos: curl com o token > arquivo .db.
        # Restaurar = colocar o arquivo de volta em /data/klink.db.
        require_admin()
        import sqlite3 as sqlite3_module
        import tempfile
        from datetime import datetime, timezone
        from pathlib import Path

        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        tmp_path = Path(handle.name)
        try:
            source = sqlite3_module.connect(settings.database_path)
            target = sqlite3_module.connect(tmp_path)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            data = tmp_path.read_bytes()
        finally:
            # Mesmo se algo falhar, a cópia temporária do banco não fica pra trás.
            tmp_path.unlink(missing_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return Response(
            data,
            mimetype="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="klink-backup-{stamp}.db"'
            },
        )

    @app.get("/api/billing/usage")
    def api_billing_usage():
        restaurant = table_sessions.restaurant()
        return jsonify(billing.usage_summary(restaurant["id"]))

    @app.get("/api/billing/invoices")
    def api_billing_invoices():
        restaurant = table_sessions.restaurant()
        return jsonify({"invoices": billing.list_invoices(restaurant["id"])})

    @app.post("/admin/billing/setup-paid")
    def admin_billing_setup_paid():
        require_admin()
        payload = request.get_json(silent=True) or {}
        restaurante_id = payload.get("restaurante_id") or table_sessions.restaurant()["id"]
        return jsonify(billing.mark_setup_paid(restaurante_id))

    @app.post("/admin/billing/suspend")
    def admin_billing_suspend():
        require_admin()
        payload = request.get_json(silent=True) or {}
        restaurante_id = payload.get("restaurante_id") or table_sessions.restaurant()["id"]
        return jsonify(billing.suspend(restaurante_id))

    @app.post("/admin/billing/reactivate")
    def admin_billing_reactivate():
        require_admin()
        payload = request.get_json(silent=True) or {}
        restaurante_id = payload.get("restaurante_id") or table_sessions.restaurant()["id"]
        return jsonify(billing.reactivate(restaurante_id))

    @app.post("/admin/billing/generate-invoice")
    def admin_generate_invoice():
        require_admin()
        payload = request.get_json(silent=True) or {}
        restaurante_id = payload.get("restaurante_id") or table_sessions.restaurant()["id"]
        periodo = payload.get("periodo")
        try:
            return jsonify(billing.generate_invoice(restaurante_id, periodo))
        except ValueError as exc:
            return jsonify({"ok": False, "reason": "periodo_invalido", "message": str(exc)}), 400

    @app.post("/admin/billing/invoice/<fatura_id>/paid")
    def admin_invoice_paid(fatura_id: str):
        require_admin()
        return jsonify(billing.mark_invoice_paid(fatura_id))

    @app.get("/qr/<token>")
    def qr_redirect(token: str):
        target = qr.resolve_redirect(token)
        if not target:
            return "QR Code invalido ou expirado.", 404
        return redirect(target)

    @app.post("/api/demo/message")
    def demo_message():
        # Simulador de mensagens: tem os mesmos efeitos de negocio de uma mensagem
        # real (abre mesa, gera cobranca). So pode existir em desenvolvimento.
        if not settings.dev_mode:
            abort(403)
        payload = request.get_json(force=True)
        inbound = whatsapp.normalize_evolution_payload(payload)
        result = process_inbound(inbound)
        return jsonify(result)

    def _webhook_authorized(token_from_path: str | None) -> bool:
        # Se KLINK_WEBHOOK_SECRET estiver configurado, exige o segredo (no path, na
        # query ?token=, ou no header X-Webhook-Token) para aceitar o webhook. Isso
        # impede que terceiros forjem mensagens (pedidos/cobrancas falsas). Sem segredo
        # configurado, mantem o comportamento aberto (apenas para dev/testes).
        secret = settings.webhook_secret
        if not secret:
            return True
        provided = (
            token_from_path
            or request.args.get("token")
            or request.headers.get("X-Webhook-Token")
            or ""
        )
        return bool(provided) and hmac.compare_digest(provided, secret)

    @app.post("/webhook")
    @app.post("/webhook/evolution")
    @app.post("/webhook/<webhook_token>")
    @app.post("/webhook/evolution/<webhook_token>")
    def webhook_evolution(webhook_token: str | None = None):
        if not _webhook_authorized(webhook_token):
            abort(403)
        payload = request.get_json(force=True)
        inbound = whatsapp.normalize_evolution_payload(payload)
        result = process_inbound(inbound)
        # A comanda pra equipe sai SÓ do webhook real — o simulador do painel
        # (/api/demo/message) não deve disparar WhatsApp de verdade.
        notify_team(result)
        if result.get("reply") and inbound.remote_jid:
            try:
                send_result = whatsapp.send_message(inbound.remote_jid, result["reply"])
                result["whatsapp"] = send_result
                if send_result.get("sent"):
                    db.record_whatsapp_send(
                        remote_jid=inbound.remote_jid,
                        sucesso=True,
                        restaurante_id=(result.get("session") or {}).get("restaurante_id"),
                    )
                    sends = db.count_whatsapp_sends_today()
                    limit = settings.evolution_daily_limit or 0
                    if limit > 0 and sends >= int(limit * 0.7):
                        app.logger.warning(
                            "evolution_daily_usage_high sends=%s limit=%s pct=%s",
                            sends,
                            limit,
                            round((sends / limit) * 100, 1),
                        )
            except Exception as exc:
                db.record_whatsapp_send(
                    remote_jid=inbound.remote_jid,
                    sucesso=False,
                    erro=str(exc),
                    restaurante_id=(result.get("session") or {}).get("restaurante_id"),
                )
                app.logger.exception("Falha ao enviar resposta WhatsApp: %s", exc)
        return jsonify({"ok": True, "action": result.get("action")})

    # ----------------------------------------------------------------------
    # Agente SDR: webhook do Evolution Go (instância dos leads, ex.: klink-sdr).
    # É uma porta SEPARADA do garçom — mensagem que cai aqui é tratada como lead
    # do tráfego pago, nunca como cliente de mesa.
    # ----------------------------------------------------------------------
    def sdr_send_text(number: str, text: str) -> dict:
        """Envia uma mensagem pela Evolution Go (POST /send/text, apikey=token)."""
        if not settings.sdr_enabled:
            return {"sent": False, "dry_run": True, "number": number, "text": text}
        url = f"{settings.sdr_evolution_url}/send/text"
        body = json.dumps({"number": number, "text": text}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "apikey": settings.sdr_evolution_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return {"sent": True, "response": resp.read().decode("utf-8")}

    def _sdr_authorized(token_from_path: str | None) -> bool:
        secret = settings.sdr_webhook_secret
        if not secret:
            return True
        provided = (
            token_from_path
            or request.args.get("token")
            or request.headers.get("X-Webhook-Token")
            or ""
        )
        return bool(provided) and hmac.compare_digest(provided, secret)

    @app.post("/webhook/sdr")
    @app.post("/webhook/sdr/<sdr_token>")
    def webhook_sdr(sdr_token: str | None = None):
        if not _sdr_authorized(sdr_token):
            abort(403)
        if not settings.sdr_enabled:
            # Agente desligado: aceita o webhook (200) mas não faz nada.
            return jsonify({"ok": True, "action": "sdr_disabled"})
        payload = request.get_json(force=True, silent=True) or {}
        inbound = whatsapp.normalize_evolution_payload(payload)
        action = process_sdr_inbound(inbound)
        return jsonify({"ok": True, "action": action})

    def process_sdr_inbound(inbound) -> str:
        # Eco do próprio número (fromMe): ignora, senão o agente responde a si mesmo.
        if inbound.from_me:
            return "from_me_ignored"
        # Só mensagem recebida (event MESSAGE). Recibo de leitura, presença, status
        # de conexão e o eco dos próprios envios (SEND_MESSAGE) não são lead.
        if inbound.event and inbound.event != "message":
            return "event_ignored"
        jid = inbound.remote_jid or ""
        # Grupos/listas/status não são lead.
        if not jid or jid.endswith(("@g.us", "@broadcast", "@newsletter")) or jid.startswith("status@"):
            # Sem remetente quase sempre = formato de payload inesperado. Loga as
            # chaves (não o conteúdo, p/ não vazar conversa) p/ diagnosticar sem redeploy.
            if not jid:
                data_keys = list((inbound.payload.get("data") or {}).keys())
                app.logger.warning(
                    "SDR webhook sem remetente (event=%r). Chaves de data=%s",
                    inbound.event, data_keys,
                )
            return "ignored"
        # Anti-duplicata: o Evolution Go reenvia até 5x se não receber 200 na hora.
        # record_message é atômico (insert or ignore) e devolve False se já veio.
        if inbound.message_id and not db.record_message(
            message_id=inbound.message_id,
            remote_jid=jid,
            tipo=inbound.tipo,
            texto=inbound.text,
            audio_url=inbound.audio_url,
            payload=inbound.payload,
            processada=True,
        ):
            return "duplicate_ignored"

        # Tira "@servidor" e também o ":aparelho" (ex.: 554431011918:1) — o
        # /send/text quer só o número.
        numero = jid.split("@", 1)[0].split(":", 1)[0]
        nome = inbound.push_name or None
        texto = (inbound.text or "").strip()

        # Por enquanto o agente atende texto. Áudio/mídia: pede gentilmente o texto.
        if not texto:
            db.sdr_ensure_lead(jid, nome)
            reply = "Opa! Consegue me mandar por *texto* rapidinho? Assim te respondo certinho. 🙂"
            db.sdr_add_message(jid, "agente", reply)
            _sdr_try_send(numero, reply, jid)
            return "sdr_no_text"

        lead = db.sdr_ensure_lead(jid, nome)
        history = db.sdr_history(jid, limit=20)
        db.sdr_add_message(jid, "lead", texto)

        result = sdr_agent.responder(history=history, mensagem=texto, nome=lead.get("nome"))
        reply = result.get("resposta") or ""
        if result.get("nome_lead"):
            db.sdr_update_nome(jid, result["nome_lead"])
        if reply:
            db.sdr_add_message(jid, "agente", reply)
            _sdr_try_send(numero, reply, jid)

        # Lead aceitou o repasse e ainda não avisamos o João: dispara o alerta.
        ja_avisado = bool((db.sdr_get_lead(jid) or {}).get("notificado_em"))
        if result.get("lead_aceitou_contato") and not ja_avisado:
            _sdr_notify_owner(jid, numero, result.get("resumo_lead") or "", result.get("nome_lead") or "")
            db.sdr_mark_notified(jid, result.get("resumo_lead") or None)
            return "sdr_lead_qualificado"
        return "sdr_respondido"

    def _sdr_try_send(numero: str, texto: str, jid: str) -> None:
        try:
            send = sdr_send_text(numero, texto)
            db.record_whatsapp_send(remote_jid=jid, sucesso=bool(send.get("sent")))
        except Exception as exc:
            db.record_whatsapp_send(remote_jid=jid, sucesso=False, erro=str(exc))
            app.logger.exception("Falha ao enviar resposta SDR: %s", exc)

    def _sdr_notify_owner(jid: str, numero: str, resumo: str, nome: str) -> None:
        destino = settings.sdr_alert_number
        if not destino:
            app.logger.warning("Lead quente sem KLINK_SDR_ALERT_NUMBER configurado: %s", jid)
            return
        nome_txt = f" ({nome})" if nome else ""
        linhas = [
            "🔥 *Lead quente no Klink!*",
            f"O lead{nome_txt} topou que a equipe entre em contato.",
            "",
            f"📱 WhatsApp: +{numero}",
            f"💬 Falar agora: https://wa.me/{numero}",
        ]
        if resumo:
            linhas += ["", f"📝 Resumo: {resumo}"]
        try:
            sdr_send_text(destino, "\n".join(linhas))
        except Exception as exc:
            app.logger.exception("Falha ao avisar o João do lead quente: %s", exc)

    def process_inbound(inbound):
        # Mensagem enviada pelo próprio bot ecoada de volta pela Evolution: descartar
        # SEMPRE, senão o bot responde a si mesmo em loop infinito (= banimento).
        if inbound.from_me:
            return {"reply": "", "action": "from_me_ignored"}
        # A Evolution avisa quando a conexão do número muda (open/connecting/close).
        # Guardamos o estado REAL: é o que deixa o selo da config e o banner do
        # painel honestos — antes, número banido continuava com selo verde.
        if inbound.event == "connection.update":
            data = inbound.payload.get("data") or {}
            state = str(data.get("state") or data.get("status") or "").strip().lower()
            # Só estados conhecidos: payload forjado/estranho não polui o selo.
            if state in ("open", "connecting", "close"):
                db.set_estado("whatsapp_connection_state", state)
            return {"reply": "", "action": "connection_state_recorded"}
        # Evento que não é mensagem recebida (ex.: qrcode.updated): não há o que
        # responder. Payload sem campo "event" (simulador/testes) passa.
        if inbound.event and inbound.event != "messages.upsert":
            return {"reply": "", "action": "event_ignored"}
        if not inbound.remote_jid:
            return {"reply": "Mensagem sem numero de origem.", "action": "invalid_sender"}
        # Grupos, listas de transmissão e canais não são mesa de cliente. Sem este
        # filtro, qualquer conversa num grupo (ex.: o grupo da cozinha) viraria
        # "cliente" e o bot responderia no meio da equipe.
        if inbound.remote_jid.endswith(
            ("@g.us", "@broadcast", "@newsletter")
        ) or inbound.remote_jid.startswith("status@"):
            return {"reply": "", "action": "group_ignored"}

        text = inbound.text
        if inbound.tipo == "audio":
            # Atalho barato: reentrega de áudio já visto não paga transcrição
            # de novo. O portão anti-duplicata de verdade é o insert abaixo.
            if db.message_exists(inbound.message_id):
                return {"reply": "", "action": "duplicate_ignored"}
            app.logger.info(
                "audio inbound: id=%s url=%s mimetype=%s base64=%s data_keys=%s msg_keys=%s audio_keys=%s",
                inbound.message_id,
                bool(inbound.audio_url),
                inbound.audio_mimetype,
                bool(inbound.audio_base64),
                list((inbound.payload.get("data") or inbound.payload).keys()),
                list(((inbound.payload.get("data") or {}).get("message") or {}).keys()),
                list(
                    (
                        ((inbound.payload.get("data") or {}).get("message") or {}).get(
                            "audioMessage"
                        )
                        or {}
                    ).keys()
                ),
            )
            try:
                b64 = inbound.audio_base64
                mimetype = inbound.audio_mimetype
                if not b64 and settings.has_evolution and inbound.message_id:
                    b64, fetched_mimetype = whatsapp.fetch_media_base64(inbound.message_id)
                    mimetype = mimetype or fetched_mimetype
                if b64:
                    raw = base64.b64decode(b64, validate=False)
                    text = audio.transcribe_bytes(raw, mimetype, inbound.duration_seconds)
                elif inbound.audio_url:
                    text = audio.transcribe_url(inbound.audio_url, inbound.duration_seconds)
                else:
                    raise ValueError("Audio sem URL nem base64 no payload.")
            except Exception as exc:
                return {
                    "reply": f"Nao consegui ouvir esse audio. Pode mandar por texto? ({exc})",
                    "action": "audio_failed",
                }

        inserted = db.record_message(
            message_id=inbound.message_id,
            remote_jid=inbound.remote_jid,
            tipo=inbound.tipo,
            texto=text,
            audio_url=inbound.audio_url,
            payload=inbound.payload,
        )
        if not inserted:
            # A mesma mensagem já entrou por outra entrega do webhook.
            return {"reply": "", "action": "duplicate_ignored"}

        try:
            result = agent.handle_message(
                remote_jid=inbound.remote_jid, text=text, origem="whatsapp"
            )
        except Exception as exc:
            # Falar algo errado é melhor que falar nada: sem esta proteção, um
            # bug inesperado virava HTTP 500, o cliente ficava no vácuo e a
            # mensagem era descartada como "duplicada" em toda reentrega.
            app.logger.exception(
                "Erro inesperado ao processar mensagem %s: %s", inbound.message_id, exc
            )
            db.mark_message_processed(
                inbound.message_id,
                restaurante_id=None,
                mesa_id=None,
                sessao_mesa_id=None,
            )
            return {
                "reply": (
                    "Tive um problema aqui agora. Pode chamar um atendente, por favor? "
                    "(If you need help, please call the staff.)"
                ),
                "action": "internal_error",
            }

        session = result.get("session") or {}
        db.mark_message_processed(
            inbound.message_id,
            restaurante_id=session.get("restaurante_id"),
            mesa_id=session.get("mesa_id"),
            sessao_mesa_id=session.get("id"),
        )
        return result

    def notify_team(result: dict) -> None:
        # Envia a comanda para o WhatsApp da equipe (campo das Configurações).
        # Falha aqui NUNCA pode derrubar a resposta ao cliente: só registra o erro.
        text = team_message_for(result)
        if not text or not settings.has_evolution:
            return
        try:
            restaurant = table_sessions.restaurant()
        except Exception:
            return
        team_jid = (restaurant.get("whatsapp_equipe") or "").strip()
        if not team_jid:
            return
        try:
            send_result = whatsapp.send_message(team_jid, text)
            if send_result.get("sent"):
                db.record_whatsapp_send(
                    remote_jid=team_jid,
                    sucesso=True,
                    restaurante_id=restaurant["id"],
                )
        except Exception as exc:
            db.record_whatsapp_send(
                remote_jid=team_jid,
                sucesso=False,
                erro=str(exc),
                restaurante_id=restaurant["id"],
            )
            app.logger.exception("Falha ao enviar comanda para a equipe: %s", exc)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)


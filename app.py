from __future__ import annotations

import base64
import hmac
import os

from flask import Flask, Response, abort, jsonify, redirect, render_template, request

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
from klink.whatsapp_adapter import WhatsAppAdapter


def _format_brl(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
        return f"💰 MESA {mesa} pediu a conta."

    if action in ("service_requested", "human_called") and result.get("request"):
        descricao = (result["request"].get("descricao") or "").strip()
        return f"🙋 {descricao}" if descricao else f"🙋 MESA {mesa} chamou atendimento."

    return None


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
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
    audio = AudioService(settings)
    qr = QRService(settings, table_sessions)

    PUBLIC_PATHS = ("/", "/health", "/webhook", "/qr/", "/static/")

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

    @app.get("/config")
    def config_page():
        restaurant = table_sessions.restaurant()
        return render_template(
            "config.html",
            restaurant=restaurant,
            is_demo=restaurant.get("slug") == DEMO_SLUG,
            bot_phone=qr.bot_phone(),
            whatsapp_connected=settings.has_evolution,
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
            # Grupo do WhatsApp tem id no formato 1234...@g.us — preserva como
            # veio; número comum fica só com dígitos.
            if "@" not in equipe:
                equipe = "".join(ch for ch in equipe if ch.isdigit())
        db.update_restaurant(
            restaurant["id"],
            nome=nome,
            telefone_whatsapp=telefone,
            whatsapp_equipe=equipe,
        )
        updated = table_sessions.restaurant()
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
        return jsonify(
            {
                "ok": True,
                "service": "klink",
                "whatsapp": {
                    "configured": settings.has_evolution,
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
        return jsonify(orders.dashboard())

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
        if not nome:
            return jsonify(
                {"ok": False, "reason": "nome_obrigatorio", "message": "Informe o nome da mesa."}
            ), 400
        db.rename_table(mesa_id, nome)
        return jsonify({"ok": True})

    @app.post("/api/tables/<mesa_id>/deactivate")
    def api_deactivate_table(mesa_id: str):
        table = table_sessions.table_by_id(mesa_id)
        if not table:
            return jsonify({"ok": False, "reason": "nao_encontrada"}), 404
        if table_sessions.has_active_sessions(mesa_id):
            return jsonify(
                {
                    "ok": False,
                    "reason": "mesa_em_uso",
                    "message": "Essa mesa tem comanda aberta. Feche a mesa antes de removê-la.",
                }
            ), 409
        db.deactivate_table(mesa_id)
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
        return jsonify(billing.generate_invoice(restaurante_id, periodo))

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

    def process_inbound(inbound):
        # Mensagem enviada pelo próprio bot ecoada de volta pela Evolution: descartar
        # SEMPRE, senão o bot responde a si mesmo em loop infinito (= banimento).
        if inbound.from_me:
            return {"reply": "", "action": "from_me_ignored"}
        # Evento que não é mensagem recebida (ex.: connection.update, qrcode.updated):
        # não há o que responder. Payload sem campo "event" (simulador/testes) passa.
        if inbound.event and inbound.event != "messages.upsert":
            return {"reply": "", "action": "event_ignored"}
        if not inbound.remote_jid:
            return {"reply": "Mensagem sem numero de origem.", "action": "invalid_sender"}
        # Grupos e listas de transmissão não são mesa de cliente. Sem este filtro,
        # qualquer conversa num grupo (ex.: o grupo da cozinha) viraria "cliente"
        # e o bot responderia no meio da equipe.
        if inbound.remote_jid.endswith("@g.us") or inbound.remote_jid.startswith("status@"):
            return {"reply": "", "action": "group_ignored"}

        if db.message_exists(inbound.message_id):
            return {"reply": "", "action": "duplicate_ignored"}

        text = inbound.text
        if inbound.tipo == "audio":
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

        db.record_message(
            message_id=inbound.message_id,
            remote_jid=inbound.remote_jid,
            tipo=inbound.tipo,
            texto=text,
            audio_url=inbound.audio_url,
            payload=inbound.payload,
        )
        result = agent.handle_message(remote_jid=inbound.remote_jid, text=text, origem="whatsapp")
        session = result.get("session") or {}
        db.mark_message_processed(
            inbound.message_id,
            restaurante_id=session.get("restaurante_id"),
            mesa_id=session.get("mesa_id"),
            sessao_mesa_id=session.get("id"),
        )
        notify_team(result)
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


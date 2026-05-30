from __future__ import annotations

import base64
import hmac

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


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
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
        if not nome:
            return jsonify({"ok": False, "reason": "nome_obrigatorio"}), 400
        telefone = None
        if telefone_raw is not None:
            telefone = "".join(ch for ch in str(telefone_raw) if ch.isdigit())
        db.update_restaurant(restaurant["id"], nome=nome, telefone_whatsapp=telefone)
        updated = table_sessions.restaurant()
        return jsonify({"ok": True, "restaurant": updated, "bot_phone": qr.bot_phone()})

    @app.get("/qrcodes")
    def qrcodes_page():
        restaurant = table_sessions.restaurant()
        tables = []
        for table in table_sessions.list_tables():
            tables.append(
                {
                    "numero": table["numero"],
                    "nome": table.get("nome"),
                    "qr_url": qr.public_qr_url(table["qr_token_atual"]),
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

    @app.get("/api/tables")
    def api_tables():
        tables = []
        for table in table_sessions.list_tables():
            table["qr_url"] = qr.public_qr_url(table["qr_token_atual"])
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
        payload = request.get_json(force=True)
        inbound = whatsapp.normalize_evolution_payload(payload)
        result = process_inbound(inbound)
        return jsonify(result)

    @app.post("/webhook")
    @app.post("/webhook/evolution")
    def webhook_evolution():
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
        if not inbound.remote_jid:
            return {"reply": "Mensagem sem numero de origem.", "action": "invalid_sender"}

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
        return result

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


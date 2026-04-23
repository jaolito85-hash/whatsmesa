from __future__ import annotations

import hmac

from flask import Flask, Response, abort, jsonify, redirect, render_template, request

from mesazap.audio_service import AudioService
from mesazap.billing_service import BillingService
from mesazap.config import get_settings
from mesazap.menu_service import MenuService
from mesazap.openai_interpreter import OpenAIInterpreter
from mesazap.order_service import OrderService
from mesazap.qr_service import QRService
from mesazap.restaurant_agent import RestaurantAgent
from mesazap.storage import Database
from mesazap.table_session_service import TableSessionService
from mesazap.whatsapp_adapter import WhatsAppAdapter


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()
    db = Database(settings.database_path)
    db.init_schema()
    db.seed_demo()

    table_sessions = TableSessionService(db)
    menu = MenuService(db)
    orders = OrderService(db)
    billing = BillingService(db)
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

    PUBLIC_PREFIXES = ("/health", "/webhook", "/qr/", "/static/")

    @app.before_request
    def enforce_dashboard_auth():
        if not settings.dashboard_auth_enabled:
            return None
        path = request.path or ""
        if any(path == p or path.startswith(p) for p in PUBLIC_PREFIXES):
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
            headers={"WWW-Authenticate": 'Basic realm="MesaZap"'},
        )

    @app.get("/")
    def dashboard():
        restaurant = table_sessions.restaurant()
        return render_template(
            "dashboard.html",
            restaurant=restaurant,
            tables=table_sessions.list_tables(),
            dashboard=orders.dashboard(),
            public_base_url=settings.public_base_url,
        )

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "mesazap"})

    @app.get("/api/dashboard")
    def api_dashboard():
        return jsonify(orders.dashboard())

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
        orders.update_request_status(request_id, payload.get("status", ""))
        return jsonify({"ok": True})

    def require_admin() -> None:
        expected = settings.admin_token
        if not expected:
            return
        provided = request.headers.get("X-Admin-Token", "")
        if provided != expected:
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
            result["whatsapp"] = whatsapp.send_message(inbound.remote_jid, result["reply"])
        return jsonify({"ok": True, "action": result.get("action")})

    def process_inbound(inbound):
        if not inbound.remote_jid:
            return {"reply": "Mensagem sem numero de origem.", "action": "invalid_sender"}

        if db.message_exists(inbound.message_id):
            return {"reply": "", "action": "duplicate_ignored"}

        text = inbound.text
        if inbound.tipo == "audio" and inbound.audio_url:
            try:
                text = audio.transcribe_url(inbound.audio_url, inbound.duration_seconds)
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


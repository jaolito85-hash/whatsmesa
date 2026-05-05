from __future__ import annotations

import os
import tempfile
import unittest

from mesazap.storage import Database
from mesazap.table_session_service import TableSessionService


def fresh_db() -> tuple[Database, str]:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    return db, handle.name


class ValidationFlowTest(unittest.TestCase):
    def test_session_starts_pending_when_validation_required(self):
        db, _ = fresh_db()
        service = TableSessionService(db, require_validation=True)
        session = service.activate_from_message("5511900000020", "Mesa 4")
        self.assertEqual(session["status"], "sessao_pendente")
        self.assertIsNone(session["validada_em"])

    def test_session_starts_active_when_validation_off(self):
        db, _ = fresh_db()
        service = TableSessionService(db, require_validation=False)
        session = service.activate_from_message("5511900000021", "Mesa 4")
        self.assertEqual(session["status"], "sessao_ativa")
        self.assertIsNotNone(session["validada_em"])

    def test_validate_session_transitions_pending_to_active(self):
        db, _ = fresh_db()
        service = TableSessionService(db, require_validation=True)
        session = service.activate_from_message("5511900000022", "Mesa 5")
        self.assertEqual(session["status"], "sessao_pendente")

        validated = service.validate_session(session["id"])
        self.assertEqual(validated["status"], "sessao_ativa")
        self.assertIsNotNone(validated["validada_em"])

        mesa = db.fetchone("select status from mesas where id = ?", (session["mesa_id"],))
        self.assertEqual(mesa["status"], "sessao_ativa")

    def test_validate_session_idempotent_on_already_active(self):
        db, _ = fresh_db()
        service = TableSessionService(db, require_validation=False)
        session = service.activate_from_message("5511900000023", "Mesa 6")
        result = service.validate_session(session["id"])
        self.assertEqual(result["status"], "sessao_ativa")

    def test_reject_session_closes_and_rotates_qr(self):
        db, _ = fresh_db()
        service = TableSessionService(db, require_validation=True)
        session = service.activate_from_message("5511900000024", "Mesa 7")
        original = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )["qr_token_atual"]

        service.reject_session(session["id"])

        closed = db.fetchone("select status from sessoes_mesa where id = ?", (session["id"],))
        self.assertEqual(closed["status"], "sessao_recusada")
        after = db.fetchone(
            "select status, qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )
        self.assertEqual(after["status"], "mesa_livre")
        self.assertNotEqual(after["qr_token_atual"], original)

    def test_list_pending_sessions_returns_only_pending(self):
        db, _ = fresh_db()
        service = TableSessionService(db, require_validation=True)
        s1 = service.activate_from_message("5511900000025", "Mesa 1")
        service.activate_from_message("5511900000026", "Mesa 2")
        service.validate_session(s1["id"])

        pending = service.list_pending_sessions()
        numbers = [row["mesa_numero"] for row in pending]
        self.assertEqual(numbers, [2])


class AgentInteractsWithValidationTest(unittest.TestCase):
    def test_bot_blocks_orders_until_validated(self):
        from mesazap.billing_service import BillingService
        from mesazap.config import Settings
        from mesazap.menu_service import MenuService
        from mesazap.openai_interpreter import OpenAIInterpreter
        from mesazap.order_service import OrderService
        from mesazap.restaurant_agent import RestaurantAgent

        db, path = fresh_db()
        sessions = TableSessionService(db, require_validation=True)
        menu = MenuService(db)
        orders = OrderService(db)
        billing = BillingService(db)
        settings = Settings(
            database_path=path,
            public_base_url="http://localhost:5000",
            whatsapp_phone="",
            evolution_api_url="",
            evolution_api_key="",
            evolution_instance="",
            openai_api_key="",
            openai_model="gpt-4o-mini",
            openai_transcription_model="gpt-4o-mini-transcribe",
            supabase_url="",
            supabase_service_role_key="",
            admin_token="",
            dashboard_user="admin",
            dashboard_password="",
        )
        agent = RestaurantAgent(
            table_sessions=sessions,
            menu=menu,
            orders=orders,
            interpreter=OpenAIInterpreter(settings),
            billing=billing,
        )

        first = agent.handle_message(remote_jid="5511900000030", text="Mesa 8")
        self.assertEqual(first["action"], "awaiting_validation")
        self.assertIn("Aguarde", first["reply"])

        order_attempt = agent.handle_message(
            remote_jid="5511900000030",
            text="Me ve duas Coronas",
        )
        self.assertEqual(order_attempt["action"], "awaiting_validation")
        self.assertEqual(len(orders.dashboard()["columns"]["bar"]), 0)

        sessions.validate_session(first["session"]["id"])

        unlocked = agent.handle_message(
            remote_jid="5511900000030",
            text="Me ve duas Coronas",
        )
        self.assertEqual(unlocked["action"], "order_draft_created")


class HealthAndRateMetricsTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        os.environ["MESAZAP_DATABASE"] = handle.name
        os.environ["MESAZAP_DASHBOARD_PASSWORD"] = ""
        os.environ["MESAZAP_PUBLIC_BASE_URL"] = "http://localhost:5000"
        os.environ["EVOLUTION_DAILY_LIMIT"] = "10"
        os.environ.pop("MESAZAP_REQUIRE_TABLE_VALIDATION", None)

        import app as app_module
        self.flask_app = app_module.create_app()
        self.flask_app.testing = True
        self.client = self.flask_app.test_client()
        self.db = Database(handle.name)

    def tearDown(self):
        os.environ.pop("EVOLUTION_DAILY_LIMIT", None)

    def test_health_returns_metrics_block(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertIn("whatsapp", body)
        self.assertIn("sends_today", body["whatsapp"])
        self.assertIn("daily_limit", body["whatsapp"])
        self.assertIn("sessions", body)
        self.assertIn("active", body["sessions"])
        self.assertIn("pending_validation", body["sessions"])
        self.assertEqual(body["whatsapp"]["daily_limit"], 10)

    def test_rate_counter_increments_after_recorded_send(self):
        baseline = self.client.get("/health").get_json()
        self.assertEqual(baseline["whatsapp"]["sends_today"], 0)

        for i in range(3):
            self.db.record_whatsapp_send(
                remote_jid=f"5511900000{i:03d}",
                sucesso=True,
            )

        after = self.client.get("/health").get_json()
        self.assertEqual(after["whatsapp"]["sends_today"], 3)
        self.assertEqual(after["whatsapp"]["usage_pct"], 30.0)
        self.assertFalse(after["whatsapp"]["warning"])

    def test_rate_warning_flips_at_70_percent(self):
        for i in range(7):
            self.db.record_whatsapp_send(remote_jid=f"x{i}", sucesso=True)
        body = self.client.get("/health").get_json()
        self.assertEqual(body["whatsapp"]["sends_today"], 7)
        self.assertTrue(body["whatsapp"]["warning"])

    def test_pending_sessions_listed_in_health_count(self):
        os.environ["MESAZAP_REQUIRE_TABLE_VALIDATION"] = "true"
        try:
            handle = tempfile.NamedTemporaryFile(suffix=".db")
            handle.close()
            os.environ["MESAZAP_DATABASE"] = handle.name
            import app as app_module
            flask_app = app_module.create_app()
            client = flask_app.test_client()
            db = Database(handle.name)

            from mesazap.table_session_service import TableSessionService

            sessions = TableSessionService(db, require_validation=True)
            sessions.activate_from_message("5511900000099", "Mesa 11")

            body = client.get("/health").get_json()
            self.assertEqual(body["sessions"]["pending_validation"], 1)
            self.assertTrue(body["require_table_validation"])
        finally:
            os.environ.pop("MESAZAP_REQUIRE_TABLE_VALIDATION", None)


class SessionEndpointsTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        os.environ["MESAZAP_DATABASE"] = handle.name
        os.environ["MESAZAP_DASHBOARD_PASSWORD"] = ""
        os.environ["MESAZAP_REQUIRE_TABLE_VALIDATION"] = "true"

        import app as app_module
        self.flask_app = app_module.create_app()
        self.flask_app.testing = True
        self.client = self.flask_app.test_client()
        self.db = Database(handle.name)

    def tearDown(self):
        os.environ.pop("MESAZAP_REQUIRE_TABLE_VALIDATION", None)

    def test_pending_endpoint_lists_open_validations(self):
        from mesazap.table_session_service import TableSessionService

        sessions = TableSessionService(self.db, require_validation=True)
        sessions.activate_from_message("5511900000040", "Mesa 9")

        response = self.client.get("/api/sessions/pending")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(len(body["sessions"]), 1)
        self.assertEqual(body["sessions"][0]["mesa_numero"], 9)

    def test_validate_endpoint_activates_session(self):
        from mesazap.table_session_service import TableSessionService

        sessions = TableSessionService(self.db, require_validation=True)
        session = sessions.activate_from_message("5511900000041", "Mesa 10")

        response = self.client.post(f"/api/sessions/{session['id']}/validate")
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["session"]["status"], "sessao_ativa")

    def test_reject_endpoint_closes_session(self):
        from mesazap.table_session_service import TableSessionService

        sessions = TableSessionService(self.db, require_validation=True)
        session = sessions.activate_from_message("5511900000042", "Mesa 11")

        response = self.client.post(f"/api/sessions/{session['id']}/reject")
        self.assertEqual(response.status_code, 200)
        closed = self.db.fetchone(
            "select status from sessoes_mesa where id = ?",
            (session["id"],),
        )
        self.assertEqual(closed["status"], "sessao_recusada")

    def test_validate_unknown_session_returns_404(self):
        response = self.client.post("/api/sessions/does-not-exist/validate")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()

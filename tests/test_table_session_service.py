from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from mesazap.storage import Database
from mesazap.table_session_service import TableSessionService


def make_service(idle_ttl_hours: int = 6) -> tuple[TableSessionService, Database]:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    return TableSessionService(db, idle_ttl_hours=idle_ttl_hours), db


def hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


class CloseSessionRotatesQRTest(unittest.TestCase):
    def test_close_session_rotates_qr_token_and_frees_table(self):
        service, db = make_service()
        remote = "5511900000001"

        session = service.activate_from_message(remote, "Mesa 7")
        self.assertIsNotNone(session)
        original = db.fetchone("select qr_token_atual, status from mesas where id = ?", (session["mesa_id"],))
        self.assertEqual(original["status"], "sessao_ativa")
        original_token = original["qr_token_atual"]

        service.close_session(session["id"])

        after = db.fetchone("select qr_token_atual, status from mesas where id = ?", (session["mesa_id"],))
        self.assertNotEqual(after["qr_token_atual"], original_token)
        self.assertEqual(after["status"], "mesa_livre")

        closed = db.fetchone("select status, fechada_em from sessoes_mesa where id = ?", (session["id"],))
        self.assertEqual(closed["status"], "sessao_fechada")
        self.assertIsNotNone(closed["fechada_em"])

    def test_old_qr_token_no_longer_resolves_after_close(self):
        service, db = make_service()
        remote = "5511900000002"
        session = service.activate_from_message(remote, "Mesa 9")
        original_token = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )["qr_token_atual"]

        service.close_session(session["id"])

        self.assertIsNone(service.table_by_token(original_token))
        new_token = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )["qr_token_atual"]
        self.assertIsNotNone(service.table_by_token(new_token))

    def test_close_session_is_idempotent(self):
        service, db = make_service()
        remote = "5511900000003"
        session = service.activate_from_message(remote, "Mesa 4")

        service.close_session(session["id"])
        token_after_first_close = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )["qr_token_atual"]

        service.close_session(session["id"])
        token_after_second_close = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )["qr_token_atual"]

        self.assertEqual(token_after_first_close, token_after_second_close)


class AutoCloseOtherSessionsTest(unittest.TestCase):
    def test_activating_new_table_closes_previous_session_for_same_jid(self):
        service, db = make_service()
        remote = "5511911111111"

        first = service.activate_from_message(remote, "Mesa 2")
        first_qr = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (first["mesa_id"],),
        )["qr_token_atual"]

        second = service.activate_from_message(remote, "Mesa 8")
        self.assertNotEqual(first["mesa_id"], second["mesa_id"])

        first_status = db.fetchone(
            "select status, fechada_em from sessoes_mesa where id = ?",
            (first["id"],),
        )
        self.assertEqual(first_status["status"], "sessao_fechada")
        self.assertIsNotNone(first_status["fechada_em"])

        first_qr_after = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (first["mesa_id"],),
        )["qr_token_atual"]
        self.assertNotEqual(first_qr_after, first_qr)

        active = service.active_session_for_whatsapp(remote)
        self.assertEqual(active["id"], second["id"])
        self.assertEqual(active["mesa_numero"], 8)

    def test_reactivating_same_table_does_not_close_existing_session(self):
        service, db = make_service()
        remote = "5511922222222"

        session = service.activate_from_message(remote, "Mesa 6")
        again = service.activate_from_message(remote, "Mesa 6")

        self.assertEqual(session["id"], again["id"])
        status = db.fetchone("select status from sessoes_mesa where id = ?", (session["id"],))
        self.assertEqual(status["status"], "sessao_ativa")

    def test_other_clients_sessions_are_untouched(self):
        service, db = make_service()
        client_a = "5511933333333"
        client_b = "5511944444444"

        session_a = service.activate_from_message(client_a, "Mesa 1")
        session_b = service.activate_from_message(client_b, "Mesa 2")

        new_a = service.activate_from_message(client_a, "Mesa 5")

        b_after = db.fetchone("select status from sessoes_mesa where id = ?", (session_b["id"],))
        self.assertEqual(b_after["status"], "sessao_ativa")

        a_old = db.fetchone("select status from sessoes_mesa where id = ?", (session_a["id"],))
        self.assertEqual(a_old["status"], "sessao_fechada")
        self.assertEqual(new_a["mesa_numero"], 5)


class IdleTTLTest(unittest.TestCase):
    def test_idle_session_is_closed_when_active_lookup_runs(self):
        service, db = make_service(idle_ttl_hours=6)
        remote = "5511955555555"

        session = service.activate_from_message(remote, "Mesa 11")
        db.execute(
            "update sessoes_mesa set ultima_atividade_em = ? where id = ?",
            (hours_ago(7), session["id"]),
        )

        result = service.active_session_for_whatsapp(remote)
        self.assertIsNone(result)

        closed = db.fetchone("select status from sessoes_mesa where id = ?", (session["id"],))
        self.assertEqual(closed["status"], "sessao_fechada")

    def test_recent_session_survives_lookup(self):
        service, db = make_service(idle_ttl_hours=6)
        remote = "5511966666666"

        session = service.activate_from_message(remote, "Mesa 10")
        db.execute(
            "update sessoes_mesa set ultima_atividade_em = ? where id = ?",
            (hours_ago(2), session["id"]),
        )

        result = service.active_session_for_whatsapp(remote)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], session["id"])

    def test_idle_session_rotates_qr_when_expired(self):
        service, db = make_service(idle_ttl_hours=6)
        remote = "5511977777777"

        session = service.activate_from_message(remote, "Mesa 3")
        original_token = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )["qr_token_atual"]

        db.execute(
            "update sessoes_mesa set ultima_atividade_em = ? where id = ?",
            (hours_ago(8), session["id"]),
        )
        service.active_session_for_whatsapp(remote)

        after = db.fetchone(
            "select qr_token_atual, status from mesas where id = ?",
            (session["mesa_id"],),
        )
        self.assertNotEqual(after["qr_token_atual"], original_token)
        self.assertEqual(after["status"], "mesa_livre")

    def test_activate_after_idle_creates_fresh_session(self):
        service, db = make_service(idle_ttl_hours=6)
        remote = "5511988888888"

        first = service.activate_from_message(remote, "Mesa 12")
        db.execute(
            "update sessoes_mesa set ultima_atividade_em = ? where id = ?",
            (hours_ago(10), first["id"]),
        )

        second = service.activate_from_message(remote, "Mesa 12")
        self.assertNotEqual(second["id"], first["id"])
        self.assertEqual(second["mesa_numero"], 12)

        old = db.fetchone("select status from sessoes_mesa where id = ?", (first["id"],))
        self.assertEqual(old["status"], "sessao_fechada")

    def test_touch_keeps_active_session_alive(self):
        service, db = make_service(idle_ttl_hours=6)
        remote = "5511999999991"

        session = service.activate_from_message(remote, "Mesa 1")
        db.execute(
            "update sessoes_mesa set ultima_atividade_em = ? where id = ?",
            (hours_ago(5.5), session["id"]),
        )

        kept = service.active_session_for_whatsapp(remote)
        self.assertIsNotNone(kept)

        db.execute(
            "update sessoes_mesa set ultima_atividade_em = ? where id = ?",
            (hours_ago(5.5), session["id"]),
        )
        still = service.active_session_for_whatsapp(remote)
        self.assertIsNotNone(still)
        self.assertEqual(still["id"], session["id"])


class CloseAccountFlowTest(unittest.TestCase):
    def test_get_request_returns_full_row(self):
        from mesazap.order_service import OrderService

        service, db = make_service()
        orders = OrderService(db)
        remote = "5511900000010"

        session = service.activate_from_message(remote, "Mesa 6")
        request = orders.create_service_request(
            session=session,
            tipo="fechar_conta",
            descricao="Fechar conta da Mesa 6",
            setor="caixa",
        )

        loaded = orders.get_request(request["id"])
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["tipo"], "fechar_conta")
        self.assertEqual(loaded["sessao_mesa_id"], session["id"])

    def test_concluding_close_account_request_via_app_closes_session(self):
        import tempfile
        import os
        from mesazap.config import Settings
        from mesazap.storage import Database
        import app as app_module

        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        os.environ["MESAZAP_DATABASE"] = handle.name
        os.environ["MESAZAP_DASHBOARD_PASSWORD"] = ""
        os.environ["MESAZAP_PUBLIC_BASE_URL"] = "http://localhost:5000"

        flask_app = app_module.create_app()
        flask_app.testing = True
        client = flask_app.test_client()

        from mesazap.table_session_service import TableSessionService
        from mesazap.order_service import OrderService

        db = Database(handle.name)
        sessions = TableSessionService(db)
        orders = OrderService(db)

        session = sessions.activate_from_message("5511900000011", "Mesa 7")
        original_token = db.fetchone(
            "select qr_token_atual from mesas where id = ?",
            (session["mesa_id"],),
        )["qr_token_atual"]

        request = orders.create_service_request(
            session=session,
            tipo="fechar_conta",
            descricao="Fechar conta da Mesa 7",
            setor="caixa",
        )

        response = client.post(
            f"/api/requests/{request['id']}/status",
            json={"status": "concluida"},
        )
        self.assertEqual(response.status_code, 200)

        closed = db.fetchone("select status from sessoes_mesa where id = ?", (session["id"],))
        self.assertEqual(closed["status"], "sessao_fechada")

        mesa_after = db.fetchone(
            "select qr_token_atual, status from mesas where id = ?",
            (session["mesa_id"],),
        )
        self.assertNotEqual(mesa_after["qr_token_atual"], original_token)
        self.assertEqual(mesa_after["status"], "mesa_livre")


if __name__ == "__main__":
    unittest.main()

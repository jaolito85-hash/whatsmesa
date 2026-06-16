from __future__ import annotations

import importlib
import os
import tempfile
import unittest


class CadastroMesasTest(unittest.TestCase):
    """Cadastro de mesas pelo painel: sem isso o restaurante ficava preso às
    12 mesas da demonstração — um salão de 40 mesas não cabia no produto."""

    _KEYS = ("KLINK_DATABASE", "KLINK_DASHBOARD_PASSWORD", "KLINK_WEBHOOK_SECRET", "KLINK_DEV_MODE")

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db")
        handle.close()
        self._db_path = handle.name
        self._prev_env = {k: os.environ.get(k) for k in self._KEYS}
        for key, value in {
            "KLINK_DATABASE": self._db_path,
            "KLINK_DASHBOARD_PASSWORD": "",
            "KLINK_WEBHOOK_SECRET": None,
            "KLINK_DEV_MODE": None,
        }.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        from klink import config as config_module

        importlib.reload(config_module)
        import app as app_module

        importlib.reload(app_module)
        self.client = app_module.app.test_client()

    def tearDown(self):
        for key, value in self._prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _tables(self) -> list[dict]:
        return self.client.get("/api/tables").get_json()["tables"]

    # ---- criação em lote ----
    def test_lote_cria_apenas_as_que_faltam(self):
        # A demo já tem 12 mesas; pedir 15 cria a 13, 14 e 15.
        r = self.client.post("/api/tables", json={"ate_numero": 15})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["criadas"], [13, 14, 15])
        self.assertEqual(len(self._tables()), 15)

    def test_lote_repetido_nao_duplica(self):
        self.client.post("/api/tables", json={"ate_numero": 15})
        r = self.client.post("/api/tables", json={"ate_numero": 15})
        self.assertEqual(r.get_json()["criadas"], [])
        self.assertEqual(len(self._tables()), 15)

    def test_lote_acima_do_limite_rejeita(self):
        r = self.client.post("/api/tables", json={"ate_numero": 301})
        self.assertEqual(r.status_code, 400)

    # ---- mesa avulsa ----
    def test_mesa_avulsa_com_nome(self):
        r = self.client.post("/api/tables", json={"numero": 101, "nome": "Varanda 1"})
        self.assertEqual(r.status_code, 200)
        mesa = next(t for t in self._tables() if t["numero"] == 101)
        self.assertEqual(mesa["nome"], "Varanda 1")

    def test_mesa_duplicada_rejeita(self):
        r = self.client.post("/api/tables", json={"numero": 5})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["reason"], "ja_existe")

    def test_numero_fora_da_faixa_rejeita(self):
        # O chat só entende mesas de 1 a 999 (parser lê até 3 dígitos).
        for numero in (0, 1000, "abc", None):
            r = self.client.post("/api/tables", json={"numero": numero})
            self.assertEqual(r.status_code, 400, f"numero={numero!r} deveria ser rejeitado")

    # ---- renomear ----
    def test_renomear_mesa(self):
        mesa = self._tables()[0]
        r = self.client.post(f"/api/tables/{mesa['id']}/rename", json={"nome": "Varanda 3"})
        self.assertEqual(r.status_code, 200)
        renamed = next(t for t in self._tables() if t["id"] == mesa["id"])
        self.assertEqual(renamed["nome"], "Varanda 3")

    def test_renomear_sem_nome_volta_ao_padrao(self):
        # Apelido em branco apaga o nome customizado e volta ao padrão "Mesa N".
        # É como o dono remove um apelido digitado por engano.
        mesa = next(t for t in self._tables() if t["numero"] == 12)
        self.client.post(f"/api/tables/{mesa['id']}/rename", json={"nome": "Varanda 3"})
        r = self.client.post(f"/api/tables/{mesa['id']}/rename", json={"nome": "  "})
        self.assertEqual(r.status_code, 200)
        renamed = next(t for t in self._tables() if t["id"] == mesa["id"])
        self.assertEqual(renamed["nome"], "Mesa 12")

    # ---- remover (desativar) ----
    def test_remover_mesa_some_da_lista_e_do_qr(self):
        mesa = next(t for t in self._tables() if t["numero"] == 12)
        r = self.client.post(f"/api/tables/{mesa['id']}/deactivate")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(12, [t["numero"] for t in self._tables()])
        # O QR impresso da mesa removida deixa de resolver.
        qr = self.client.get(f"/qr/{mesa['id']}")
        self.assertEqual(qr.status_code, 404)

    def test_remover_mesa_com_comanda_aberta_rejeita(self):
        self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {"remoteJid": "5511900000020@s.whatsapp.net", "id": "msg-cm-1"},
                    "message": {"conversation": "Mesa 7"},
                }
            },
        )
        mesa = next(t for t in self._tables() if t["numero"] == 7)
        r = self.client.post(f"/api/tables/{mesa['id']}/deactivate")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.get_json()["reason"], "mesa_em_uso")

    def test_recriar_mesa_removida_reativa_com_mesmo_id(self):
        # Reativar mantém o id antigo: o QR impresso volta a funcionar.
        mesa = next(t for t in self._tables() if t["numero"] == 11)
        self.client.post(f"/api/tables/{mesa['id']}/deactivate")
        r = self.client.post("/api/tables", json={"numero": 11})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["id"], mesa["id"])
        qr = self.client.get(f"/qr/{mesa['id']}")
        self.assertEqual(qr.status_code, 302)

    def test_reativar_em_lote_preserva_nome_customizado(self):
        # Dono renomeou a mesa, removeu temporariamente e recriou em lote:
        # o nome ("Varanda") não pode voltar como "Mesa 9".
        mesa = next(t for t in self._tables() if t["numero"] == 9)
        self.client.post(f"/api/tables/{mesa['id']}/rename", json={"nome": "Varanda"})
        self.client.post(f"/api/tables/{mesa['id']}/deactivate")
        self.client.post("/api/tables", json={"ate_numero": 12})
        reativada = next(t for t in self._tables() if t["numero"] == 9)
        self.assertEqual(reativada["nome"], "Varanda")

    def test_mesa_removida_nao_abre_pelo_chat(self):
        mesa = next(t for t in self._tables() if t["numero"] == 10)
        self.client.post(f"/api/tables/{mesa['id']}/deactivate")
        r = self.client.post(
            "/webhook",
            json={
                "data": {
                    "key": {"remoteJid": "5511900000021@s.whatsapp.net", "id": "msg-cm-2"},
                    "message": {"conversation": "Mesa 10"},
                }
            },
        )
        self.assertEqual(r.get_json()["action"], "need_table")


if __name__ == "__main__":
    unittest.main()

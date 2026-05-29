from __future__ import annotations

import tempfile
import unittest

from klink.menu_service import MenuMatch, MenuService, NUMBER_WORDS
from klink.storage import Database


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def make_service() -> tuple[MenuService, Database]:
    handle = tempfile.NamedTemporaryFile(suffix=".db")
    handle.close()
    db = Database(handle.name)
    db.init_schema()
    db.seed_demo()
    return MenuService(db), db


def restaurante_id(db: Database) -> str:
    row = db.fetchone("select id from restaurantes limit 1")
    assert row is not None
    return row["id"]


# ---------------------------------------------------------------------------
# products_for_restaurant
# ---------------------------------------------------------------------------

class ProductsForRestaurantTest(unittest.TestCase):
    def test_retorna_lista_nao_vazia_para_restaurante_demo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        products = menu.products_for_restaurant(rid)
        self.assertGreater(len(products), 0)

    def test_retorna_lista_vazia_para_restaurante_inexistente(self):
        menu, db = make_service()
        products = menu.products_for_restaurant("restaurante-que-nao-existe")
        self.assertEqual(products, [])

    def test_cada_produto_tem_campo_aliases(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        products = menu.products_for_restaurant(rid)
        for product in products:
            self.assertIn("aliases", product)
            self.assertIsInstance(product["aliases"], list)

    def test_aliases_nao_estao_vazios_para_produto_demo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        products = menu.products_for_restaurant(rid)
        corona = next(p for p in products if p["nome"] == "Corona long neck")
        self.assertGreater(len(corona["aliases"]), 0)

    def test_nao_retorna_produto_inativo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        # Desativa a Corona
        db.execute("update produtos set ativo = 0 where nome = 'Corona long neck'")
        products = menu.products_for_restaurant(rid)
        nomes = [p["nome"] for p in products]
        self.assertNotIn("Corona long neck", nomes)

    def test_produto_inativo_ausente_mas_ativo_presente(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        db.execute("update produtos set ativo = 0 where nome = 'Corona long neck'")
        products = menu.products_for_restaurant(rid)
        nomes = [p["nome"] for p in products]
        self.assertIn("Brahma 600ml", nomes)

    def test_ordenacao_por_setor_depois_nome(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        products = menu.products_for_restaurant(rid)
        setores = [p["setor"] for p in products]
        # Todos os produtos de 'bar' devem vir antes de 'cozinha'
        self.assertEqual(setores, sorted(setores))

    def test_campos_obrigatorios_presentes(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        products = menu.products_for_restaurant(rid)
        required = {"id", "nome", "descricao", "preco", "categoria", "setor", "ativo", "disponivel", "aliases"}
        for product in products:
            for field in required:
                self.assertIn(field, product, f"Campo '{field}' ausente no produto {product.get('nome')}")


# ---------------------------------------------------------------------------
# find_items — caminho feliz
# ---------------------------------------------------------------------------

class FindItemsCaminhoFelizTest(unittest.TestCase):
    def test_encontra_corona_por_alias(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero uma corona")
        nomes = [i["nome"] for i in result["items"]]
        self.assertIn("Corona long neck", nomes)

    def test_resultado_nao_tem_ambiguous_nem_unavailable(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero uma corona")
        self.assertEqual(result["ambiguous"], [])
        self.assertEqual(result["unavailable"], [])

    def test_encontra_batata_frita_por_alias(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "me ve uma batata frita")
        nomes = [i["nome"] for i in result["items"]]
        self.assertIn("Porcao de batata frita", nomes)

    def test_encontra_multiplos_itens_na_mesma_mensagem(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero uma corona e batata frita")
        nomes = [i["nome"] for i in result["items"]]
        self.assertIn("Corona long neck", nomes)
        self.assertIn("Porcao de batata frita", nomes)

    def test_texto_vazio_retorna_lista_vazia(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "")
        self.assertEqual(result["items"], [])

    def test_texto_sem_produto_retorna_items_vazio(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "bom dia tudo bem")
        self.assertEqual(result["items"], [])

    def test_item_tem_campos_obrigatorios(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "uma corona")
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        for field in ("product_id", "nome", "quantidade", "preco", "setor", "observacoes"):
            self.assertIn(field, item)

    def test_preco_e_float(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "uma corona")
        item = result["items"][0]
        self.assertIsInstance(item["preco"], float)

    def test_setor_correto_para_item_de_bar(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "uma corona")
        item = result["items"][0]
        self.assertEqual(item["setor"], "bar")

    def test_setor_correto_para_item_de_cozinha(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "porcao de batata frita")
        item = result["items"][0]
        self.assertEqual(item["setor"], "cozinha")

    def test_alias_em_ingles_encontra_produto(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "i want french fries")
        nomes = [i["nome"] for i in result["items"]]
        self.assertIn("Porcao de batata frita", nomes)

    def test_alias_em_espanhol_encontra_produto(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quiero papas fritas")
        nomes = [i["nome"] for i in result["items"]]
        self.assertIn("Porcao de batata frita", nomes)


# ---------------------------------------------------------------------------
# find_items — quantidade extraida do texto
# ---------------------------------------------------------------------------

class FindItemsQuantidadeTest(unittest.TestCase):
    def test_quantidade_padrao_1_sem_numero(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "corona")
        item = result["items"][0]
        self.assertEqual(item["quantidade"], 1)

    def test_quantidade_numerica_antes_do_alias(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "3 corona")
        item = result["items"][0]
        self.assertEqual(item["quantidade"], 3)

    def test_quantidade_dois_por_extenso(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "dois corona")
        item = result["items"][0]
        self.assertEqual(item["quantidade"], 2)

    def test_quantidade_tres_por_extenso(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "tres corona")
        item = result["items"][0]
        self.assertEqual(item["quantidade"], 3)

    def test_quantidade_uma_por_extenso(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "uma corona")
        item = result["items"][0]
        self.assertEqual(item["quantidade"], 1)

    def test_quantidade_two_ingles(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "two corona")
        item = result["items"][0]
        self.assertEqual(item["quantidade"], 2)

    def test_quantidade_nao_negativa(self):
        # Quantidade nunca deve ser menor que 1 mesmo sem numero explícito
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "corona por favor")
        item = result["items"][0]
        self.assertGreaterEqual(item["quantidade"], 1)

    def test_conector_e_faz_quantidade_independente(self):
        # "3 coronas e batata" — batata deve ter quantidade 1, nao 3
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "3 coronas e batata")
        itens_por_nome = {i["nome"]: i for i in result["items"]}
        self.assertIn("Corona long neck", itens_por_nome)
        self.assertIn("Porcao de batata frita", itens_por_nome)
        self.assertEqual(itens_por_nome["Corona long neck"]["quantidade"], 3)
        self.assertEqual(itens_por_nome["Porcao de batata frita"]["quantidade"], 1)


# ---------------------------------------------------------------------------
# find_items — produto indisponivel
# ---------------------------------------------------------------------------

class FindItemsIndisponivelTest(unittest.TestCase):
    def test_produto_indisponivel_vai_para_unavailable(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        db.execute("update produtos set disponivel = 0 where nome = 'Corona long neck'")
        result = menu.find_items(rid, "uma corona")
        nomes_items = [i["nome"] for i in result["items"]]
        nomes_unavail = [u["nome"] for u in result["unavailable"]]
        self.assertNotIn("Corona long neck", nomes_items)
        self.assertIn("Corona long neck", nomes_unavail)

    def test_produto_indisponivel_tem_motivo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        db.execute("update produtos set disponivel = 0 where nome = 'Corona long neck'")
        result = menu.find_items(rid, "uma corona")
        unavail = result["unavailable"][0]
        self.assertIn("motivo", unavail)
        self.assertEqual(unavail["motivo"], "indisponivel")

    def test_produto_disponivel_nao_aparece_em_unavailable(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "uma corona")
        self.assertEqual(result["unavailable"], [])


# ---------------------------------------------------------------------------
# find_items — ambiguidade brahma
# ---------------------------------------------------------------------------

class FindItemsAmbiguoBrahmaTest(unittest.TestCase):
    def test_brahma_sozinho_retorna_ambiguous(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero uma brahma")
        self.assertGreater(len(result["ambiguous"]), 1)
        self.assertEqual(result["items"], [])

    def test_brahma_600_nao_e_ambiguo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero brahma 600")
        self.assertEqual(result["ambiguous"], [])

    def test_brahma_600ml_nao_e_ambiguo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "me ve brahma 600ml")
        self.assertEqual(result["ambiguous"], [])

    def test_brahma_lata_nao_e_ambiguo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero brahma lata")
        self.assertEqual(result["ambiguous"], [])

    def test_brahma_garrafa_nao_e_ambiguo(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "brahma garrafa")
        self.assertEqual(result["ambiguous"], [])

    def test_ambiguous_contem_id_e_nome(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero brahma")
        for option in result["ambiguous"]:
            self.assertIn("id", option)
            self.assertIn("nome", option)

    def test_ambiguous_so_ocorre_com_multiplas_opcoes_brahma(self):
        # Se houver apenas uma Brahma no cardapio, nao deve retornar ambiguous
        menu, db = make_service()
        rid = restaurante_id(db)
        # Desativa todas exceto uma
        db.execute("update produtos set ativo = 0 where nome = 'Brahma lata'")
        result = menu.find_items(rid, "quero brahma")
        # Com apenas Brahma 600ml ativa, nao ha ambiguidade
        self.assertEqual(result["ambiguous"], [])

    def test_brahma_ambiguo_items_e_unavailable_vazios(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        result = menu.find_items(rid, "quero brahma")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["unavailable"], [])


# ---------------------------------------------------------------------------
# product_by_name_or_alias
# ---------------------------------------------------------------------------

class ProductByNameOrAliasTest(unittest.TestCase):
    def test_encontra_por_nome_exato(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        produto = menu.product_by_name_or_alias(rid, "Corona long neck")
        self.assertIsNotNone(produto)
        self.assertEqual(produto["nome"], "Corona long neck")

    def test_encontra_por_alias(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        produto = menu.product_by_name_or_alias(rid, "corona")
        self.assertIsNotNone(produto)
        self.assertEqual(produto["nome"], "Corona long neck")

    def test_encontra_por_alias_em_ingles(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        produto = menu.product_by_name_or_alias(rid, "french fries")
        self.assertIsNotNone(produto)
        self.assertEqual(produto["nome"], "Porcao de batata frita")

    def test_nome_vazio_retorna_none(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        produto = menu.product_by_name_or_alias(rid, "")
        self.assertIsNone(produto)

    def test_nome_inexistente_retorna_none(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        produto = menu.product_by_name_or_alias(rid, "produto que nao existe xyz")
        self.assertIsNone(produto)

    def test_restaurante_errado_retorna_none(self):
        menu, db = make_service()
        produto = menu.product_by_name_or_alias("restaurante-invalido", "Corona long neck")
        self.assertIsNone(produto)

    def test_encontra_por_nome_normalizado_sem_acentos(self):
        # "Porcao de batata frita" é armazenado sem acento; busca com "Porção" deve encontrar via normalize
        menu, db = make_service()
        rid = restaurante_id(db)
        produto = menu.product_by_name_or_alias(rid, "Porcao de batata frita")
        self.assertIsNotNone(produto)

    def test_encontra_por_nome_case_insensitive(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        produto = menu.product_by_name_or_alias(rid, "corona long neck")
        self.assertIsNotNone(produto)
        self.assertEqual(produto["nome"], "Corona long neck")

    def test_produto_inativo_nao_e_encontrado(self):
        menu, db = make_service()
        rid = restaurante_id(db)
        db.execute("update produtos set ativo = 0 where nome = 'Corona long neck'")
        produto = menu.product_by_name_or_alias(rid, "Corona long neck")
        self.assertIsNone(produto)


# ---------------------------------------------------------------------------
# _quantity_before (testado indiretamente via find_items, mas também direto)
# ---------------------------------------------------------------------------

class QuantityBeforeTest(unittest.TestCase):
    def setUp(self):
        self.menu, db = make_service()

    def test_sem_texto_antes_retorna_1(self):
        result = self.menu._quantity_before("", 0)
        self.assertEqual(result, 1)

    def test_digito_antes_retorna_quantidade_correta(self):
        text = "5 corona"
        start = text.index("corona")
        result = self.menu._quantity_before(text, start)
        self.assertEqual(result, 5)

    def test_palavra_por_extenso_dois(self):
        text = "dois corona"
        start = text.index("corona")
        result = self.menu._quantity_before(text, start)
        self.assertEqual(result, 2)

    def test_palavra_por_extenso_tres(self):
        text = "tres corona"
        start = text.index("corona")
        result = self.menu._quantity_before(text, start)
        self.assertEqual(result, 3)

    def test_token_nao_numerico_retorna_1(self):
        text = "quero corona"
        start = text.index("corona")
        result = self.menu._quantity_before(text, start)
        self.assertEqual(result, 1)

    def test_conector_e_reseta_janela(self):
        # "3 coronas e batata": ao buscar quantidade antes de "batata",
        # o "e" zera a janela, entao so tokens apos "e" sao considerados
        text = "3 coronas e batata"
        start = text.index("batata")
        result = self.menu._quantity_before(text, start)
        # Apos o "e" nao ha digito nem palavra numerica — retorna 1
        self.assertEqual(result, 1)

    def test_quantidade_minima_e_1_mesmo_com_zero(self):
        # "0 corona" — max(1, int("0")) = 1
        text = "0 corona"
        start = text.index("corona")
        result = self.menu._quantity_before(text, start)
        self.assertEqual(result, 1)


# ---------------------------------------------------------------------------
# MenuMatch.as_dict
# ---------------------------------------------------------------------------

class MenuMatchAsDictTest(unittest.TestCase):
    def test_as_dict_contem_todas_as_chaves(self):
        match = MenuMatch(
            product_id="abc123",
            nome="Produto Teste",
            quantidade=2,
            preco=14.0,
            setor="bar",
            observacoes="sem gelo",
        )
        d = match.as_dict()
        for key in ("product_id", "nome", "quantidade", "preco", "setor", "observacoes"):
            self.assertIn(key, d)

    def test_as_dict_valores_corretos(self):
        match = MenuMatch(
            product_id="x1",
            nome="Corona long neck",
            quantidade=3,
            preco=14.0,
            setor="bar",
        )
        d = match.as_dict()
        self.assertEqual(d["product_id"], "x1")
        self.assertEqual(d["nome"], "Corona long neck")
        self.assertEqual(d["quantidade"], 3)
        self.assertAlmostEqual(d["preco"], 14.0)
        self.assertEqual(d["setor"], "bar")
        self.assertEqual(d["observacoes"], "")

    def test_as_dict_observacoes_padrao_vazio(self):
        match = MenuMatch(product_id="y", nome="Agua", quantidade=1, preco=5.0, setor="bar")
        self.assertEqual(match.as_dict()["observacoes"], "")

    def test_menu_match_e_frozen(self):
        match = MenuMatch(product_id="z", nome="Pudim", quantidade=1, preco=12.0, setor="cozinha")
        with self.assertRaises((AttributeError, TypeError)):
            match.nome = "outro"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NUMBER_WORDS — entradas criticas
# ---------------------------------------------------------------------------

class NumberWordsTest(unittest.TestCase):
    def test_portugues_um(self):
        self.assertEqual(NUMBER_WORDS["um"], 1)

    def test_portugues_uma(self):
        self.assertEqual(NUMBER_WORDS["uma"], 1)

    def test_portugues_dois(self):
        self.assertEqual(NUMBER_WORDS["dois"], 2)

    def test_portugues_duas(self):
        self.assertEqual(NUMBER_WORDS["duas"], 2)

    def test_portugues_tres(self):
        self.assertEqual(NUMBER_WORDS["tres"], 3)

    def test_portugues_dez(self):
        self.assertEqual(NUMBER_WORDS["dez"], 10)

    def test_ingles_one(self):
        self.assertEqual(NUMBER_WORDS["one"], 1)

    def test_ingles_two(self):
        self.assertEqual(NUMBER_WORDS["two"], 2)

    def test_ingles_ten(self):
        self.assertEqual(NUMBER_WORDS["ten"], 10)

    def test_espanhol_uno(self):
        self.assertEqual(NUMBER_WORDS["uno"], 1)

    def test_espanhol_dos(self):
        self.assertEqual(NUMBER_WORDS["dos"], 2)

    def test_espanhol_diez(self):
        self.assertEqual(NUMBER_WORDS["diez"], 10)

    def test_artigo_a_vale_1(self):
        self.assertEqual(NUMBER_WORDS["a"], 1)


if __name__ == "__main__":
    unittest.main()

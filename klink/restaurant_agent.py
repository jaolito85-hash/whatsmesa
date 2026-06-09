from __future__ import annotations

from typing import Any

from .billing_service import BillingService
from .language_service import detect_language
from .menu_service import MenuService
from .openai_interpreter import OpenAIInterpreter
from .order_service import OrderService
from .table_session_service import TableSessionService
from .text_utils import format_brl, normalize_text


# Teto por item: acima disso o bot não manda direto pra cozinha — chama um
# atendente para confirmar na mesa (pode ser festa grande... ou trote).
MAX_ITEM_QUANTITY = 30

MENU_WORDS = {"cardapio", "menu", "carta", "menus"}

CONFIRM_WORDS = {
    "1",
    "sim",
    "s",
    "confirma",
    "confirmar",
    "pode mandar",
    "manda",
    "fechado",
    "yes",
    "y",
    "confirm",
    "confirmed",
    "send it",
    "go ahead",
    "si",
    "confirmo",
    "mandalo",
}
ALTER_WORDS = {"2", "alterar", "mudar", "corrigir", "trocar", "change", "edit", "alter", "cambiar"}
REPEAT_MARKERS = (
    "outra rodada",
    "mais uma igual",
    "repete",
    "manda outra",
    "igual",
    "another round",
    "same again",
    "repeat",
    "otra ronda",
    "lo mismo",
    "repite",
)
ACCOUNT_MARKERS = (
    "fecha a conta",
    "fechar a conta",
    "conta por favor",
    "pagar",
    "pagamento",
    "close the bill",
    "bill please",
    "check please",
    "pay",
    "payment",
    "cerrar la cuenta",
    "la cuenta",
    "cuenta por favor",
    "pago",
)
SERVICE_MARKERS = {
    "limpar": "limpeza",
    "limpa": "limpeza",
    "limpe": "limpeza",
    "limpem": "limpeza",
    "limpeza": "limpeza",
    "limpada": "limpeza",
    "limpado": "limpeza",
    "molhou": "limpeza",
    "molhei": "limpeza",
    "derramei": "limpeza",
    "derramou": "limpeza",
    "derrubei": "limpeza",
    "derrubou": "limpeza",
    "sujou": "limpeza",
    "sujei": "limpeza",
    "sujeira": "limpeza",
    "clean": "limpeza",
    "cleaning": "limpeza",
    "spilled": "limpeza",
    "limpiar": "limpeza",
    "limpieza": "limpeza",
    "guardanapo": "guardanapo",
    "guardanapos": "guardanapo",
    "napkin": "guardanapo",
    "napkins": "guardanapo",
    "servilleta": "guardanapo",
    "servilletas": "guardanapo",
    "talher": "talher",
    "talheres": "talher",
    "garfo": "talher",
    "garfos": "talher",
    "faca": "talher",
    "facas": "talher",
    "colher": "talher",
    "colheres": "talher",
    "fork": "talher",
    "forks": "talher",
    "knife": "talher",
    "knives": "talher",
    "cutlery": "talher",
    "cubiertos": "talher",
    "tenedor": "talher",
    "tenedores": "talher",
    "cuchillo": "talher",
    "cuchillos": "talher",
    "limao": "limao",
    "limoes": "limao",
    "lemon": "limao",
    "lemons": "limao",
    "lime": "limao",
    "limes": "limao",
    "limon": "limao",
    "limones": "limao",
    "molho": "molho",
    "molhos": "molho",
    "sauce": "molho",
    "sauces": "molho",
    "salsa": "molho",
    "salsas": "molho",
    "garcom": "chamar_garcom",
    "garcons": "chamar_garcom",
    "atendente": "chamar_garcom",
    "atendentes": "chamar_garcom",
    "waiter": "chamar_garcom",
    "waitress": "chamar_garcom",
    "staff": "chamar_garcom",
    "camarero": "chamar_garcom",
    "camareros": "chamar_garcom",
    "mesero": "chamar_garcom",
    "meseros": "chamar_garcom",
    "mozo": "chamar_garcom",
    "mozos": "chamar_garcom",
}

MESSAGES = {
    "session_activated": {
        "pt": "Mesa {table} liberada. Pode pedir por áudio ou texto.",
        "en": "Table {table} is ready. You can order by audio or text.",
        "es": "Mesa {table} liberada. Puedes pedir por audio o texto.",
    },
    "need_table": {
        "pt": "Me diga o número da mesa para começar. Exemplo: Mesa 12.",
        "en": "Tell me your table number to start. Example: Table 12.",
        "es": "Dime el numero de la mesa para empezar. Ejemplo: Mesa 12.",
    },
    "nothing_to_confirm": {
        "pt": "Não encontrei pedido pendente. Pode me mandar o que deseja pedir.",
        "en": "I do not see a pending order. Send me what you would like.",
        "es": "No encontre un pedido pendiente. Dime que quieres pedir.",
    },
    "order_confirmed": {
        "pt": "Pedido confirmado e enviado para {sectors}. Se demorar, é só chamar um atendente.",
        "en": "Order confirmed and sent to {sectors}. If it takes long, please call the staff.",
        "es": "Pedido confirmado y enviado a {sectors}. Si tarda, llama al personal.",
    },
    "alter_order": {
        "pt": "Claro. Me diga como quer alterar o pedido.",
        "en": "Sure. Tell me what you want to change.",
        "es": "Claro. Dime que quieres cambiar.",
    },
    "account_requested": {
        "pt": "Já pedi o fechamento da Mesa {table}. Um atendente vai levar a conta.",
        "en": "I asked to close Table {table}. A staff member will bring the bill.",
        "es": "Ya pedi cerrar la cuenta de la Mesa {table}. Un atendente llevara la cuenta.",
    },
    "menu_header": {
        "pt": "📋 Nosso cardápio:",
        "en": "📋 Our menu:",
        "es": "📋 Nuestra carta:",
    },
    "menu_footer": {
        "pt": "É só me dizer o que você quer, por texto ou áudio. 😉",
        "en": "Just tell me what you'd like, by text or audio. 😉",
        "es": "Solo dime lo que quieres, por texto o audio. 😉",
    },
    "menu_empty": {
        "pt": "O cardápio ainda está sendo cadastrado. Chamei um atendente para te ajudar.",
        "en": "The menu is still being set up. I called staff to help you.",
        "es": "La carta aun se esta cargando. Llame al personal para ayudarte.",
    },
    "quantity_too_big": {
        "pt": "Pedido grande assim (mais de {max} de um item) eu prefiro confirmar pessoalmente. Chamei um atendente na sua mesa. 👍",
        "en": "For big orders (more than {max} of one item) I prefer a personal check. I called staff to your table. 👍",
        "es": "Para pedidos grandes (mas de {max} de un item) prefiero confirmar en persona. Llame al personal a tu mesa. 👍",
    },
    "account_header": {
        "pt": "Conta da Mesa {table}:",
        "en": "Bill for Table {table}:",
        "es": "Cuenta de la Mesa {table}:",
    },
    "account_total": {
        "pt": "Total: R$ {total}",
        "en": "Total: R$ {total}",
        "es": "Total: R$ {total}",
    },
    "service_requested": {
        "pt": "Combinado. Chamei o atendimento da Mesa {table}.",
        "en": "Got it. I called staff for Table {table}.",
        "es": "Listo. Llame al personal de la Mesa {table}.",
    },
    "repeat_not_found": {
        "pt": "Ainda não tenho uma rodada anterior para repetir. Me diga os itens que você quer.",
        "en": "I do not have a previous round to repeat yet. Tell me what you would like.",
        "es": "Todavia no tengo una ronda anterior para repetir. Dime que quieres.",
    },
    "ambiguous_brahma": {
        "pt": "Brahma {options}?",
        "en": "Brahma {options}?",
        "es": "Brahma {options}?",
    },
    "unavailable": {
        "pt": "{names} não está disponível agora. Posso chamar um atendente para ajudar?",
        "en": "{names} is not available right now. Should I call staff to help?",
        "es": "{names} no esta disponible ahora. Puedo llamar a un atendente para ayudar?",
    },
    "order_partial": {
        "pt": "Só um aviso: não temos {names} no momento.",
        "en": "Just so you know: we don't have {names} right now.",
        "es": "Solo un aviso: no tenemos {names} en este momento.",
    },
    "human_called": {
        "pt": "Não encontrei esse item no cardápio da casa. Chamei um atendente para ajudar.",
        "en": "I could not find that item on the menu. I called staff to help.",
        "es": "No encontre ese item en el menu. Llame a un atendente para ayudar.",
    },
    "confirmation": {
        "pt": "Mesa {table}: {items}. Confirma?\n1 - Confirmar\n2 - Alterar",
        "en": "Table {table}: {items}. Confirm?\n1 - Confirm\n2 - Change",
        "es": "Mesa {table}: {items}. Confirmas?\n1 - Confirmar\n2 - Cambiar",
    },
    "account_inactive": {
        "pt": "Estamos ajustando algo aqui. Chame um atendente para fazer seu pedido.",
        "en": "We are setting something up. Please call staff to place your order.",
        "es": "Estamos ajustando algo. Llame al personal para hacer su pedido.",
    },
    "awaiting_validation": {
        "pt": "Mesa {table} registrada. Aguarde o atendente confirmar visualmente que voce esta na mesa para liberar o pedido.",
        "en": "Table {table} registered. Please wait for staff to visually confirm you are seated before ordering.",
        "es": "Mesa {table} registrada. Espera al personal confirmar visualmente que estas en la mesa antes de pedir.",
    },
}

SECTOR_NAMES = {
    "pt": {"bar": "o balcão", "cozinha": "a cozinha", "salao": "o salão", "caixa": "o caixa"},
    "en": {"bar": "the bar", "cozinha": "the kitchen", "salao": "the floor team", "caixa": "cashier"},
    "es": {"bar": "el bar", "cozinha": "la cocina", "salao": "el salon", "caixa": "la caja"},
}

DISPLAY_NAMES = {
    "porcao de batata frita": {"en": "fries", "es": "papas fritas"},
    "agua sem gas": {"en": "still water", "es": "agua sin gas"},
    "refrigerante lata": {"en": "soda can", "es": "refresco lata"},
    "isca de frango": {"en": "chicken strips", "es": "tiras de pollo"},
    "picanha acebolada": {"en": "picanha with onions", "es": "picanha encebollada"},
    "pudim": {"en": "flan", "es": "pudin"},
}


class RestaurantAgent:
    def __init__(
        self,
        *,
        table_sessions: TableSessionService,
        menu: MenuService,
        orders: OrderService,
        interpreter: OpenAIInterpreter,
        billing: BillingService,
    ):
        self.table_sessions = table_sessions
        self.menu = menu
        self.orders = orders
        self.interpreter = interpreter
        self.billing = billing

    def handle_message(
        self,
        *,
        remote_jid: str,
        text: str,
        origem: str = "whatsapp",
    ) -> dict[str, Any]:
        text = (text or "").strip()
        language = detect_language(text)

        restaurant = self.table_sessions.restaurant()
        if not self.billing.is_active(restaurant["id"]):
            return {
                "reply": self._message("account_inactive", language),
                "session": None,
                "action": "account_inactive",
                "language": language,
            }

        # Troca de mesa só com mensagem EXPLÍCITA de abertura ("Mesa 7", como o
        # QR manda) ou no primeiro contato. Antes, citar "mesa 8" no meio de uma
        # frase ("a mesa 8 tá livre pros meus amigos?") fechava a conta atual em
        # silêncio, liberava a mesa no painel e gerava nova cobrança.
        existing = self.table_sessions.active_session_for_whatsapp(remote_jid)
        activated = None
        if self._is_table_intro(text) or not existing:
            activated = self.table_sessions.activate_from_message(remote_jid, text)
        if activated and self._is_table_intro(text):
            if activated.get("status") == "sessao_pendente":
                return {
                    "reply": self._message(
                        "awaiting_validation",
                        language,
                        table=activated["mesa_numero"],
                    ),
                    "session": activated,
                    "action": "awaiting_validation",
                    "language": language,
                }
            return {
                "reply": self._message(
                    "session_activated",
                    language,
                    table=activated["mesa_numero"],
                ),
                "session": activated,
                "action": "session_activated",
                "language": language,
            }

        session = self.table_sessions.active_session_for_whatsapp(remote_jid)
        if not session:
            return {
                "reply": self._message("need_table", language),
                "session": None,
                "action": "need_table",
                "language": language,
            }

        if session.get("status") == "sessao_pendente":
            return {
                "reply": self._message(
                    "awaiting_validation",
                    language,
                    table=session["mesa_numero"],
                ),
                "session": session,
                "action": "awaiting_validation",
                "language": language,
            }

        normalized = normalize_text(text)
        pending = self.orders.pending_order(session["id"])
        if pending and normalized in {"1", "2"}:
            language = detect_language(pending["texto_original"])

        if self._is_confirm(normalized):
            if not pending:
                return {
                    "reply": self._message("nothing_to_confirm", language),
                    "session": session,
                    "action": "nothing_to_confirm",
                    "language": language,
                }
            confirmed = self.orders.confirm_order(pending["id"])
            sectors = self._human_sectors(confirmed["setores"], language)
            return {
                "reply": self._message("order_confirmed", language, sectors=sectors),
                "session": session,
                "order": confirmed,
                "action": "order_confirmed",
                "language": language,
            }

        if self._is_alter(normalized):
            return {
                "reply": self._message("alter_order", language),
                "session": session,
                "order": pending,
                "action": "alter_order",
                "language": language,
            }

        if self._is_account_request(normalized):
            return self._request_account(session, language)

        if self._is_menu_request(normalized):
            return {
                "reply": self._menu_reply(language),
                "session": session,
                "action": "menu_sent",
                "language": language,
            }

        service_type = self._service_type(normalized)
        if service_type:
            description = self._service_description(text, session["mesa_numero"])
            request = self.orders.create_service_request(
                session=session,
                tipo=service_type,
                descricao=description,
                setor="salao",
            )
            return {
                "reply": self._message(
                    "service_requested",
                    language,
                    table=session["mesa_numero"],
                ),
                "session": session,
                "request": request,
                "action": "service_requested",
                "language": language,
            }

        if self._is_repeat(normalized):
            draft = self.orders.create_repeat_draft(session)
            if not draft:
                return {
                    "reply": self._message("repeat_not_found", language),
                    "session": session,
                    "action": "repeat_not_found",
                    "language": language,
                }
            return {
                "reply": self._confirmation_message(session["mesa_numero"], draft["items"], language),
                "session": session,
                "order": draft,
                "action": "order_draft_created",
                "language": language,
            }

        restaurant = self.table_sessions.restaurant()
        menu_items = self.menu.products_for_restaurant(restaurant["id"])
        openai_result = self.interpreter.interpret(
            message=text,
            table_number=session["mesa_numero"],
            menu_items=menu_items,
        )
        if openai_result:
            handled = self._handle_openai_result(openai_result, session, text, origem, language)
            if handled:
                return handled

        match = self.menu.find_items(restaurant["id"], text)
        if match["ambiguous"]:
            options = self._join_items(
                [item["nome"].replace("Brahma ", "") for item in match["ambiguous"]],
                language,
            )
            return {
                "reply": self._message("ambiguous_brahma", language, options=options),
                "session": session,
                "action": "clarification_needed",
                "language": language,
            }
        if match["unavailable"]:
            names = ", ".join(item["nome"] for item in match["unavailable"])
            return {
                "reply": self._message("unavailable", language, names=names),
                "session": session,
                "action": "unavailable",
                "language": language,
            }
        if match["items"]:
            guarded = self._quantity_guard(match["items"], session, text, language)
            if guarded:
                return guarded
            draft = self.orders.create_draft_order(
                session=session,
                items=match["items"],
                texto_original=text,
                origem=origem,
            )
            return {
                "reply": self._confirmation_message(session["mesa_numero"], draft["items"], language),
                "session": session,
                "order": draft,
                "action": "order_draft_created",
                "language": language,
            }

        request = self.orders.create_service_request(
            session=session,
            tipo="chamar_garcom",
            descricao=f"Atendente chamado para a Mesa {session['mesa_numero']}: {text}",
            setor="salao",
        )
        return {
            "reply": self._message("human_called", language),
            "session": session,
            "request": request,
            "action": "human_called",
            "language": language,
        }

    def _handle_openai_result(
        self,
        result: dict[str, Any],
        session: dict[str, Any],
        text: str,
        origem: str,
        language: str,
    ) -> dict[str, Any] | None:
        intent = result.get("intent")
        if result.get("clarification_question"):
            return {
                "reply": result["clarification_question"],
                "session": session,
                "action": "clarification_needed",
                "language": language,
            }
        if intent == "repeat":
            draft = self.orders.create_repeat_draft(session)
            if draft:
                return {
                    "reply": self._confirmation_message(session["mesa_numero"], draft["items"], language),
                    "session": session,
                    "order": draft,
                    "action": "order_draft_created",
                    "language": language,
                }
            return None
        if intent == "close_account":
            return self._request_account(session, language)
        if intent == "service":
            description = result.get("service_description") or text
            request = self.orders.create_service_request(
                session=session,
                tipo="outro",
                descricao=description,
                setor="salao",
            )
            return {
                "reply": self._message(
                    "service_requested",
                    language,
                    table=session["mesa_numero"],
                ),
                "session": session,
                "request": request,
                "action": "service_requested",
                "language": language,
            }
        if intent != "order":
            return None

        restaurant = self.table_sessions.restaurant()
        items = []
        missing = []
        for item in result.get("items", []):
            product = self.menu.product_by_name_or_alias(restaurant["id"], item.get("name", ""))
            if not product or not product.get("disponivel"):
                # Em vez de descartar o pedido inteiro, registramos o item que
                # faltou e seguimos com os demais. Assim o cliente recebe o que
                # temos e um aviso claro do que nao foi possivel atender.
                name = (item.get("name") or "").strip()
                if name:
                    missing.append(name)
                continue
            items.append(
                {
                    "product_id": product["id"],
                    "nome": product["nome"],
                    "quantidade": max(1, int(item.get("quantity") or 1)),
                    "preco": float(product["preco"]),
                    "setor": product["setor"],
                    "observacoes": item.get("notes", ""),
                }
            )
        if not items:
            # Nenhum item valido. Se algum nome foi pedido mas nao existe/esta
            # indisponivel, avisamos em vez de sumir silenciosamente.
            if missing:
                names = ", ".join(missing)
                return {
                    "reply": self._message("unavailable", language, names=names),
                    "session": session,
                    "action": "unavailable",
                    "language": language,
                }
            return None
        guarded = self._quantity_guard(items, session, text, language)
        if guarded:
            return guarded
        draft = self.orders.create_draft_order(
            session=session,
            items=items,
            texto_original=text,
            origem=origem,
        )
        reply = self._confirmation_message(session["mesa_numero"], draft["items"], language)
        if missing:
            names = ", ".join(missing)
            reply = self._message("order_partial", language, names=names) + "\n" + reply
        return {
            "reply": reply,
            "session": session,
            "order": draft,
            "action": "order_draft_created",
            "language": language,
        }

    def _quantity_guard(
        self,
        items: list[dict[str, Any]],
        session: dict[str, Any],
        text: str,
        language: str,
    ) -> dict[str, Any] | None:
        """Trava anti-trote: '100 picanhas' não entra direto na fila da cozinha.

        Acima do teto, em vez de mandar pro setor, o bot chama um atendente para
        confirmar pessoalmente — pode ser uma festa de verdade (o atendente
        lança) ou um engraçadinho (o atendente ignora)."""
        biggest = max((int(item.get("quantidade") or 1) for item in items), default=0)
        if biggest <= MAX_ITEM_QUANTITY:
            return None
        request = self.orders.create_service_request(
            session=session,
            tipo="outro",
            descricao=(
                f"Mesa {session['mesa_numero']}: pedido com quantidade alta "
                f"({text.strip()[:120]}) — confirmar pessoalmente antes de lançar"
            ),
            setor="salao",
        )
        return {
            "reply": self._message("quantity_too_big", language, max=MAX_ITEM_QUANTITY),
            "session": session,
            "request": request,
            "action": "quantity_too_big",
            "language": language,
        }

    def _is_menu_request(self, normalized: str) -> bool:
        return bool(set(normalized.split()) & MENU_WORDS)

    def _menu_reply(self, language: str) -> str:
        """Responde o cardápio com preços — antes, perguntar 'qual o cardápio?'
        chamava um atendente (o cliente não tinha preço em lugar nenhum)."""
        restaurant = self.table_sessions.restaurant()
        items = [
            p
            for p in self.menu.products_for_restaurant(restaurant["id"])
            if p.get("disponivel")
        ]
        if not items:
            return self._message("menu_empty", language)
        lines = [self._message("menu_header", language)]
        by_category: dict[str, list[dict[str, Any]]] = {}
        for product in items:
            by_category.setdefault(product.get("categoria") or "geral", []).append(product)
        for categoria, products in by_category.items():
            lines.append("")
            lines.append(f"*{categoria.capitalize()}*")
            for product in products:
                nome = self._display_name(str(product["nome"]), language)
                lines.append(f"• {nome} — R$ {format_brl(float(product['preco']))}")
        lines.append("")
        lines.append(self._message("menu_footer", language))
        return "\n".join(lines)

    def _request_account(self, session: dict[str, Any], language: str) -> dict[str, Any]:
        """Fecha a conta com extrato: o cliente recebe os itens + total no
        WhatsApp e o caixa recebe o ticket já com o valor — antes o caixa tinha
        que somar a comanda de cabeça."""
        self.table_sessions.request_account_close(session["id"])
        mesa = session["mesa_numero"]
        summary = self.orders.session_summary(session["id"])
        descricao = f"Fechar conta da Mesa {mesa}"
        if summary["items"]:
            descricao += f" — Total R$ {format_brl(summary['total'])}"
        request = self.orders.create_service_request(
            session=session,
            tipo="fechar_conta",
            descricao=descricao,
            setor="caixa",
        )
        reply = self._message("account_requested", language, table=mesa)
        if summary["items"]:
            lines = [self._message("account_header", language, table=mesa)]
            for item in summary["items"]:
                nome = self._display_name(str(item["nome"]), language)
                lines.append(
                    f"{item['quantidade']}x {nome} — R$ {format_brl(item['subtotal'])}"
                )
            lines.append(self._message("account_total", language, total=format_brl(summary["total"])))
            reply = "\n".join(lines) + "\n" + reply
        return {
            "reply": reply,
            "session": session,
            "request": request,
            "action": "account_requested",
            "language": language,
        }

    def _is_table_intro(self, text: str) -> bool:
        normalized = normalize_text(text)
        return normalized.startswith(("mesa", "table")) and len(normalized.split()) <= 3

    def _is_confirm(self, normalized: str) -> bool:
        return normalized in CONFIRM_WORDS or normalized.startswith("confirm")

    def _is_alter(self, normalized: str) -> bool:
        return normalized in ALTER_WORDS

    def _is_repeat(self, normalized: str) -> bool:
        return any(marker in normalized for marker in REPEAT_MARKERS)

    def _is_account_request(self, normalized: str) -> bool:
        return any(marker in normalized for marker in ACCOUNT_MARKERS)

    def _service_type(self, normalized: str) -> str | None:
        tokens = set(normalized.split())
        for marker, service_type in SERVICE_MARKERS.items():
            if marker in tokens:
                return service_type
        return None

    def _service_description(self, text: str, table_number: int) -> str:
        return f"Mesa {table_number}: {text.strip()}"

    def _confirmation_message(
        self,
        table_number: int,
        items: list[dict[str, Any]],
        language: str,
    ) -> str:
        summary = self._items_summary(items, language)
        return self._message("confirmation", language, table=table_number, items=summary)

    def _items_summary(self, items: list[dict[str, Any]], language: str) -> str:
        parts = []
        for item in items:
            quantity = item.get("quantidade", 1)
            name = item.get("nome") or item.get("nome_snapshot")
            parts.append(f"{quantity} {self._display_name(str(name), language)}")
        return self._join_items(parts, language)

    def _human_sectors(self, sectors: list[str], language: str) -> str:
        names = SECTOR_NAMES.get(language, SECTOR_NAMES["pt"])
        readable = [names.get(sector, sector) for sector in sectors]
        fallback = {"pt": "a equipe", "en": "the team", "es": "el equipo"}.get(language, "a equipe")
        return self._join_items(readable, language) if readable else fallback

    def _message(self, key: str, language: str, **kwargs: Any) -> str:
        variants = MESSAGES.get(key, {})
        template = variants.get(language) or variants.get("pt") or ""
        return template.format(**kwargs)

    def _display_name(self, name: str, language: str) -> str:
        if language == "pt":
            return name
        normalized = normalize_text(name)
        return DISPLAY_NAMES.get(normalized, {}).get(language, name)

    def _join_items(self, items: list[str], language: str) -> str:
        if len(items) <= 1:
            return items[0] if items else ""
        connector = {"pt": " e ", "en": " and ", "es": " y "}.get(language, " e ")
        return ", ".join(items[:-1]) + connector + items[-1]

"""HR Chat service — AI extracts data, docxtpl renders document."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from biotact.modules.hr.documents.renderer import render_template
from biotact.modules.hr.library.service import (
    get_template_by_category,
    list_templates,
)
from biotact.modules.hr.num_to_text import (
    format_salary,
    num_to_text_ru,
    num_to_text_uz,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from biotact.core.config import Settings

logger = logging.getLogger(__name__)

# Directory for rendered files (temporary)
RENDER_DIR = Path("data/hr_rendered")

SYSTEM_PROMPT = """\
Ты — HR-ассистент компании BIOTACT. Твоя задача — извлечь данные из запроса пользователя и создать документ по шаблону.

Алгоритм:
1. Определи тип документа → вызови find_template с категорией
2. Получишь template_id и список полей (fields) шаблона
3. Извлеки значение для КАЖДОГО поля из текста пользователя
4. Если обязательных данных не хватает — спроси пользователя
5. Когда ВСЕ поля заполнены → вызови generate_document, передав template_id и data с КАЖДЫМ полем

Общие правила полей:
- FIO_LATIN: ФИО латиницей, ЗАГЛАВНЫМИ (IVANOVA MARIYA PETROVNA)
- FIO_SHORT_LATIN: краткое латиницей (IVANOVA M. P.)
- PASSPORT: серия и номер (AD 1234567)
- PASSPORT_SERIES / PASSPORT_NUMBER: серия и номер раздельно (AD / 1234567)
- PASSPORT_ISSUED_BY: кем выдан (IIV 12345)
- PASSPORT_DATE: дата выдачи (ДД.ММ.ГГГГ)
- ADDRESS: полный адрес
- PHONE: телефон (+998...)
- PINFL: 14-значный номер
- DIRECTOR_SHORT_LATIN: "ISHMATOV SH.R." (по умолчанию)
- HR_DIRECTOR_SHORT_LATIN: "KOROTUN O.A." (по умолчанию)
- Все даты в формате ДД.ММ.ГГГГ

Правила по типам документов:

ТРУДОВОЙ ДОГОВОР (td_osnovnoy, td_sovmestitelstvo):
- POSITION / POSITION_UZ: должность на рус / узб
- CONTRACT_TYPE: "неопределённый срок" или "определённый срок"
- CONTRACT_TYPE_UZ: "муддатсиз" или "муайян муддатга"
- WORK_TYPE: "основной работы" или "работы по совместительству"
- WORK_TYPE_UZ: "асосий иш жойи" или "ўриндошлик бўйича иш жойи"
- PROBATION: ТОЛЬКО число месяцев ("3")
- SALARY: ТОЛЬКО число (5000000). SALARY_TEXT генерируется автоматически.
- VACATION_DAYS: число дней (по умолчанию 21). Текст генерируется автоматически.
- HOURS_WEEK / HOURS_DAY: автоматически (40/8 основной, 20/4 совместительство)

ГПД (gpd_uslugi):
- CONTRACT_NUMBER, CONTRACT_DATE: номер и дата договора
- INN: ИНН исполнителя
- BANK_ACCOUNT, BANK_NAME, BANK_MFO, CARD_NUMBER: банковские реквизиты

ПРИКАЗ О ПРИЁМЕ (prikaz_priem):
- POSITION_GENITIVE: должность в родительном падеже ("специалиста по маркетингу")
- START_DATE: ПОЛНАЯ дата прописью ("15 апреля 2026 года", НЕ "15.04.2026")
- START_DATE_SHORT: краткая дата цифрами ("15.04.2026")
- WORK_TYPE: ПОЛНАЯ фраза: "по основному месту работы" или "по совместительству"
- ORDER_NUMBER: номер приказа
- TD_NUMBER: номер трудового договора

ПРИКАЗ ЗАКРЕПЛЕНИЯ АВТО (prikaz_avto):
- POSITION / POSITION_INSTRUMENTAL: должность ("Специалист" / "специалистом")
- CAR_BRAND, CAR_NUMBER: марка и госномер авто
- CONTROLLER_FIO_LATIN, CONTROLLER_SHORT_LATIN: ФИО контролирующего лица
- CONTROLLER_POSITION / CONTROLLER_POSITION_GENITIVE: должность контролирующего
- SIGNER_TITLE, SIGNER_SHORT_LATIN: подписант ("Директор AI трансформации", "SUVOROVA T. A.")

МАТ. ОТВЕТСТВЕННОСТЬ (mat_otvetstvennost):
- PASSPORT_SERIES / PASSPORT_NUMBER: серия и номер раздельно

ДОП. СОГЛАШЕНИЕ — смена паспорта (dop_soglashenie_pasport):
- TD_NUMBER, TD_DATE: номер и дата трудового договора
- AGREEMENT_NUMBER, AGREEMENT_DATE: номер и дата доп. соглашения
- NEW_PASSPORT, NEW_PASSPORT_ISSUED_BY, NEW_PASSPORT_DATE: новые паспортные данные
- DIRECTOR_FIO_LATIN, DIRECTOR_SHORT_LATIN: ФИО директора

NDA ДЛЯ РАБОТНИКА (nda_rabotnik):
- SIGNER_TITLE: должность подписанта ("Генеральный директор" или "Директор продаж")
- SIGNER_TITLE_GENITIVE: в родит. падеже ("Генерального директора")
- SIGNER_TITLE_UZ: на узбекском ("Бош директор" или "Савдо директори")
- CITIZEN_GENDER: "гражданин" или "гражданка"
- DIRECTOR_FIO_LATIN: ФИО подписанта ("ISHMATOV SHERZOD RUSTAMOVICH")

NDA ДЛЯ ГПД (nda_gpd):
- CITIZEN_GENDER: "гражданин" или "гражданка"
- DIRECTOR_FIO / DIRECTOR_FIO_NOMINATIVE / DIRECTOR_SHORT: ФИО директора в разных падежах
- GPD_NUMBER, GPD_DATE: номер и дата ГПД, к которому относится NDA (из фраз вида "ГПД №4 от 27.04.2026", "гражданско-правовой договор № X от Y")

ВОЗМЕЩЕНИЕ РАСХОДОВ (soglashenie_vozmeshenie):
- AGREEMENT_DATE: дата соглашения

ОБРАБОТКА ПЕРС. ДАННЫХ (soglashenie_pd):
- AGREEMENT_NUMBER, AGREEMENT_DATE: номер и дата соглашения
- GPD_NUMBER, GPD_DATE: номер и дата ГПД на который ссылается

Категории шаблонов:
- td_osnovnoy — трудовой договор (основное место)
- td_sovmestitelstvo — трудовой договор (совместительство)
- gpd_uslugi — ГПД на оказание услуг
- prikaz_priem — приказ о приёме на работу
- prikaz_avto — приказ закрепления авто
- mat_otvetstvennost — договор мат. ответственности
- dop_soglashenie_pasport — доп. соглашение (смена паспорта)
- nda_rabotnik — NDA для работника
- nda_gpd — NDA для исполнителя по ГПД
- soglashenie_vozmeshenie — соглашение о возмещении расходов
- soglashenie_pd — соглашение об обработке перс. данных

КРИТИЧНО: в data должны быть ВСЕ поля из fields. Пустые поля = пустые места в документе.
Отвечай коротко, по делу, на русском.
НЕ выдумывай данные — если не указаны, спроси.
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_template",
            "description": (
                "Найти шаблон документа по категории. "
                "Категории: td_osnovnoy, td_sovmestitelstvo, "
                "gpd_uslugi, prikaz_priem, prikaz_avto, "
                "mat_otvetstvennost, dop_soglashenie_pasport, "
                "nda_rabotnik, nda_gpd, "
                "soglashenie_vozmeshenie, soglashenie_pd."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Категория документа",
                    },
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_document",
            "description": (
                "Сгенерировать документ по шаблону с заполненными данными. "
                "Вызывай когда все обязательные поля заполнены."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "ID шаблона из find_template",
                    },
                    "data": {
                        "type": "object",
                        "description": (
                            "Данные для подстановки. Используй ТОЧНЫЙ список полей "
                            "из find_template (fields). Передай ВСЕ поля."
                        ),
                    },
                },
                "required": ["template_id", "data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_templates",
            "description": "Показать список всех загруженных шаблонов документов.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _parse_int(value: str) -> int | None:
    """Extract integer from string like '5000000' or '5 000 000'."""
    digits = "".join(c for c in value if c.isdigit())
    return int(digits) if digits else None


_MONTHS_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def _is_short_date(value: str) -> bool:
    """Check if value looks like DD.MM.YYYY."""
    import re

    return bool(re.match(r"^\d{1,2}\.\d{2}\.\d{4}$", value.strip()))


def _date_to_full_russian(short_date: str) -> str:
    """Convert '15.04.2026' to '15 апреля 2026'.

    Note: no 'года' suffix — templates add 'г.' or 'й.' themselves.
    """
    parts = short_date.strip().split(".")
    if len(parts) != 3:
        return short_date
    day, month, year = parts
    month_int = int(month)
    if 1 <= month_int <= 12:
        return f"{int(day)} {_MONTHS_RU[month_int]} {year}"
    return short_date


def _postprocess_fields(data: dict[str, str], category: str = "") -> dict[str, str]:  # noqa: PLR0912, PLR0915
    """Generate computed fields programmatically after LLM extraction.

    Handles auto-generation for all document types:
    - TD: SALARY_TEXT, VACATION_DAYS_TEXT, HOURS, POSITION_UZ, CONTRACT_DATE
    - All: DIRECTOR_SHORT_LATIN, HR_DIRECTOR_SHORT_LATIN defaults
    - PROBATION: extract just the number
    """
    # Company defaults — fill if missing or empty
    if not data.get("DIRECTOR_SHORT_LATIN"):
        data["DIRECTOR_SHORT_LATIN"] = "ISHMATOV SH.R."
    if not data.get("HR_DIRECTOR_SHORT_LATIN"):
        data["HR_DIRECTOR_SHORT_LATIN"] = "KOROTUN O.A."

    # SIGNER_TITLE defaults for NDA
    if category == "nda_rabotnik":
        if not data.get("SIGNER_TITLE"):
            data["SIGNER_TITLE"] = "Генеральный директор"
        if not data.get("SIGNER_TITLE_GENITIVE"):
            # Derive from SIGNER_TITLE
            title = data.get("SIGNER_TITLE", "")
            if "Генеральный директор" in title:
                data["SIGNER_TITLE_GENITIVE"] = "Генерального директора"
            elif "Директор продаж" in title:
                data["SIGNER_TITLE_GENITIVE"] = "Директора продаж"
            else:
                data["SIGNER_TITLE_GENITIVE"] = title
        if not data.get("SIGNER_TITLE_UZ"):
            title = data.get("SIGNER_TITLE", "")
            if "Генеральный директор" in title:
                data["SIGNER_TITLE_UZ"] = "Бош директор"
            elif "Директор продаж" in title:
                data["SIGNER_TITLE_UZ"] = "Савдо директори"
            else:
                data["SIGNER_TITLE_UZ"] = title

    # CITIZEN_GENDER: normalize LLM output
    cg = data.get("CITIZEN_GENDER", "")
    if cg and cg not in ("гражданин", "гражданка"):
        # LLM may return "женский"/"мужской" or other variants
        if any(w in cg.lower() for w in ("жен", "female", "ка")):
            data["CITIZEN_GENDER"] = "гражданка"
        else:
            data["CITIZEN_GENDER"] = "гражданин"

    # PROBATION: strip to digits only ("3 месяца" → "3")
    prob = data.get("PROBATION", "")
    if prob:
        prob_int = _parse_int(prob)
        if prob_int:
            data["PROBATION"] = str(prob_int)

    # HOURS defaults based on contract type (TD only)
    if category.startswith("td_"):
        if not data.get("HOURS_WEEK"):
            data["HOURS_WEEK"] = "20" if category == "td_sovmestitelstvo" else "40"
        if not data.get("HOURS_DAY"):
            data["HOURS_DAY"] = "4" if category == "td_sovmestitelstvo" else "8"

    # SALARY → formatted + text
    salary_raw = data.get("SALARY", "")
    salary_int = _parse_int(salary_raw) if salary_raw else None
    if salary_int:
        data["SALARY"] = format_salary(salary_raw)
        # Always regenerate text — LLM often puts numbers instead of words
        data["SALARY_TEXT"] = num_to_text_ru(salary_int) + " сум 00 тийин"
        data["SALARY_TEXT_UZ"] = num_to_text_uz(salary_int) + " сўм 00 тийин"

    # VACATION_DAYS → text (TD only)
    if category.startswith("td_"):
        vac = data.get("VACATION_DAYS", "")
        if not vac:
            data["VACATION_DAYS"] = "21"
            vac = "21"
        vac_int = _parse_int(vac)
        if vac_int:
            if not data.get("VACATION_DAYS_TEXT"):
                data["VACATION_DAYS_TEXT"] = num_to_text_ru(vac_int)
            if not data.get("VACATION_DAYS_TEXT_UZ"):
                data["VACATION_DAYS_TEXT_UZ"] = num_to_text_uz(vac_int)

    # POSITION: normalize case — LLM often returns ALL CAPS
    for pos_field in ("POSITION", "POSITION_UZ", "POSITION_GENITIVE", "POSITION_INSTRUMENTAL"):
        val = data.get(pos_field, "")
        if val and val == val.upper() and len(val) > 3:
            data[pos_field] = val.capitalize()

    # POSITION_UZ fallback
    if not data.get("POSITION_UZ") and data.get("POSITION"):
        data["POSITION_UZ"] = data["POSITION"]

    # WORK_CHARACTER_UZ: translate from Russian
    wc = data.get("WORK_CHARACTER", "")
    if wc and not data.get("WORK_CHARACTER_UZ"):
        wc_map = {
            "офисный": "офис",
            "офис": "офис",
            "разъездной": "саёҳат",
            "в пути": "йўлда",
            "на производстве": "ишлаб чиқариш",
            "производство": "ишлаб чиқариш",
            "производственный": "ишлаб чиқариш",
        }
        data["WORK_CHARACTER_UZ"] = wc_map.get(wc.lower(), wc)

    # START_DATE: convert short date to full Russian format if needed
    # "15.04.2026" → "15 апреля 2026"
    start_date = data.get("START_DATE", "")
    if start_date and _is_short_date(start_date):
        data["START_DATE"] = _date_to_full_russian(start_date)

    # WORK_TYPE: ensure full phrase for prikaz_priem
    if category == "prikaz_priem":
        wt = data.get("WORK_TYPE", "")
        if wt and "по " not in wt:
            if "совместител" in wt:
                data["WORK_TYPE"] = "по совместительству"
            else:
                data["WORK_TYPE"] = "по основному месту работы"

    # CONTRACT_DATE / AGREEMENT_DATE / ORDER_DATE — default to today
    from datetime import datetime

    today = datetime.now(tz=UTC).strftime("%d.%m.%Y")
    for date_field in ("CONTRACT_DATE", "AGREEMENT_DATE", "ORDER_DATE"):
        if date_field in data and not data[date_field]:
            data[date_field] = today

    return data


class HRChatService:
    """HR Chat — AI extracts data from user text, docxtpl renders DOCX."""

    def __init__(
        self, settings: Settings, db: AsyncSession, *, user_id: int = 0
    ) -> None:
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "gpt-5.4-mini"
        self.db = db
        self._user_id = user_id

    async def _get_template_context(self) -> str:
        """Pre-fetch available templates to inject into system prompt."""
        try:
            templates_result = await list_templates(self.db)
            if not templates_result.items:
                return ""
            lines = []
            for t in templates_result.items:
                fields = t.template_fields or []
                lines.append(
                    f"- id={t.id} name={t.name} category={t.category} fields={fields}"
                )
            return (
                "\n\nДоступные шаблоны (уже загружены, find_template не нужен):\n"
                + "\n".join(lines)
                + "\n\nЕсли пользователь просит создать документ и все данные собраны, "
                "сразу вызывай generate_document с нужным template_id и ВСЕМИ полями."
            )
        except Exception:
            logger.exception("Failed to pre-fetch templates")
            return ""

    async def _extract_data_from_context(
        self,
        context: str,
        fields: list[str],
    ) -> dict[str, str]:
        """Use a focused LLM call to extract structured data from conversation."""
        extraction_prompt = (
            "Извлеки данные из текста переписки и верни JSON.\n"
            f"Поля: {json.dumps(fields)}\n\n"
            "Правила:\n"
            "- FIO: ЗАГЛАВНЫМИ кириллицей (ПЕТРОВ АЛЕКСЕЙ СЕРГЕЕВИЧ)\n"
            "- FIO_LATIN: ЗАГЛАВНЫМИ латиницей (PETROV ALEKSEY SERGEEVICH)\n"
            "- FIO_SHORT_LATIN: PETROV A. S.\n"
            "- CONTRACT_TYPE: 'неопределённый срок' или 'определённый срок'\n"
            "- CONTRACT_TYPE_UZ: 'муддатсиз' или 'муайян муддатга'\n"
            "- WORK_TYPE: 'основной работы' или 'работы по совместительству'\n"
            "- WORK_TYPE_UZ: 'асосий иш жойи' или 'ўриндошлик бўйича иш жойи'\n"
            "- Даты: ДД.ММ.ГГГГ\n"
            "- Если поле нельзя извлечь — пустая строка\n\n"
            "Верни ТОЛЬКО JSON, без пояснений.\n\n"
            f"Переписка:\n{context}"
        )

        try:
            response = await self.openai.chat.completions.create(
                model=self.model,
                max_completion_tokens=2048,
                messages=[{"role": "user", "content": extraction_prompt}],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            data = json.loads(raw)
            logger.info("Extracted %d fields from context", len(data))
            return {k: str(v) for k, v in data.items() if v}
        except Exception:
            logger.exception("Failed to extract data from context")
            return {}

    async def process_message(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Process user message.

        Returns: {"message": str, "document_url": str | None}
        """
        # Pre-fetch template context so AI always knows template_id + fields
        template_ctx = await self._get_template_context()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT + template_ctx},
        ]

        if history:
            for msg in history[-10:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": message})

        # Save conversation text for fallback extraction
        self._messages_context = "\n".join(
            f"{m['role']}: {m['content']}"
            for m in messages
            if m["role"] in ("user", "assistant") and m.get("content")
        )

        document_url: str | None = None

        # Function calling loop (up to 5 rounds)
        for round_num in range(5):
            try:
                response = await self.openai.chat.completions.create(  # type: ignore[call-overload]
                    model=self.model,
                    max_completion_tokens=4096,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    tool_choice="auto",
                )
            except Exception as e:
                logger.exception("HR chat OpenAI error round=%d", round_num)
                return {"message": f"Ошибка LLM: {e}", "document_url": None}

            choice = response.choices[0]
            logger.info(
                "HR chat round=%d finish=%s tools=%s",
                round_num,
                choice.finish_reason,
                bool(choice.message.tool_calls),
            )

            if choice.message.tool_calls:
                tool_call = choice.message.tool_calls[0]
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)
                logger.info(
                    "HR tool: %s args=%s",
                    func_name,
                    json.dumps(func_args, ensure_ascii=False)[:2000],
                )

                tool_result = await self._execute_tool(func_name, func_args)

                # If generate_document returned a URL, capture it
                if func_name == "generate_document" and tool_result.startswith("/api/"):
                    document_url = tool_result
                    # Let the model generate a final message
                    tool_result_for_model = (
                        "Документ успешно создан и готов к скачиванию."
                    )
                else:
                    tool_result_for_model = tool_result

                messages.append(
                    {
                        "role": "assistant",
                        "content": choice.message.content or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": func_name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result_for_model,
                    }
                )
                continue

            # Model finished
            final_text = choice.message.content or ""
            return {"message": final_text, "document_url": document_url}

        return {
            "message": "Не удалось обработать запрос. Попробуйте ещё раз.",
            "document_url": None,
        }

    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:  # noqa: PLR0911
        """Execute a tool call."""
        if name == "find_template":
            category = args.get("category", "")
            template = await get_template_by_category(self.db, category)
            if not template:
                return f"Шаблон для категории '{category}' не найден. Попросите загрузить шаблон."
            return json.dumps(
                {
                    "template_id": template.id,
                    "name": template.name,
                    "fields": template.template_fields or [],
                },
                ensure_ascii=False,
            )

        if name == "generate_document":
            template_id = args.get("template_id")
            data = args.get("data", {})

            if not template_id:
                return "Ошибка: не указан template_id"

            from sqlalchemy import select

            from biotact.modules.hr.library.models import HRTemplate

            result = await self.db.execute(
                select(HRTemplate).where(HRTemplate.id == template_id)
            )
            db_template = result.scalar_one_or_none()
            if not db_template:
                return "Ошибка: шаблон не найден"

            # If AI sent incomplete data, extract from conversation
            fields = db_template.template_fields or []
            missing = [f for f in fields if f not in data or not data[f]]
            if missing and hasattr(self, "_messages_context"):
                logger.info(
                    "generate_document: %d/%d fields missing, extracting via LLM",
                    len(missing),
                    len(fields),
                )
                extracted = await self._extract_data_from_context(
                    self._messages_context, fields
                )
                # Merge: AI-provided data takes priority
                for k, v in extracted.items():
                    if k not in data or not data.get(k):
                        data[k] = v

            # Post-process: generate computed fields programmatically
            data = _postprocess_fields(data, category=db_template.category)

            # Render DOCX
            try:
                RENDER_DIR.mkdir(parents=True, exist_ok=True)
                file_id = uuid.uuid4().hex[:12]
                out_path = RENDER_DIR / f"{file_id}.docx"

                buffer = render_template(db_template.file_path, data)
                rendered_bytes = buffer.read()
                out_path.write_bytes(rendered_bytes)

                # Save to hr_documents for history
                from biotact.modules.hr.library.models import HRDocument

                employee = data.get("FIO") or data.get("FIO_LATIN") or "—"
                hr_doc = HRDocument(
                    file_id=file_id,
                    template_id=db_template.id,
                    template_name=db_template.name,
                    employee_name=employee,
                    file_path=str(out_path),
                    file_size=len(rendered_bytes),
                    created_by=self._user_id,
                )
                self.db.add(hr_doc)
                await self.db.flush()

                logger.info(
                    "Document rendered: %s employee=%s fields=%d",
                    out_path,
                    employee,
                    len(data),
                )
                return f"/api/v1/hr/documents/download/{file_id}"
            except Exception as e:
                logger.exception("Render failed for template %d", template_id)
                return f"Ошибка рендеринга: {e}"

        if name == "list_available_templates":
            templates_result = await list_templates(self.db)
            if not templates_result.items:
                return "Библиотека пуста. Загрузите шаблоны документов."
            lines = [
                f"- {t.name} (категория: {t.category}, полей: {len(t.template_fields or [])})"
                for t in templates_result.items
            ]
            return "Доступные шаблоны:\n" + "\n".join(lines)

        return f"Неизвестный инструмент: {name}"

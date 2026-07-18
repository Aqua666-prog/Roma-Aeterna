#!/usr/bin/env python3
"""Нормализация библиографических ссылок Roma Aeterna для озвучки.

Модуль не меняет поле ``source`` в интерфейсе игры. Он превращает разнородные
ссылки в единый устный формат, например::

    Дион Кассий. Римская история. Книга шестьдесят восемь. Три. Четыре.

в::

    Дион Кассий. Римская история. Книга шестьдесят восьмая.
    Глава третья. Параграф четвёртый.

Поддерживаются античные сочинения, библейские ссылки, CIL, Дигесты,
папирусы, стихотворные строки, стефановская и беккеровская пагинация.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

STRESS_MARK = "+"

# ---------------------------------------------------------------------------
# ЧИСЛА И ПОРЯДКОВЫЕ ЧИСЛИТЕЛЬНЫЕ
# ---------------------------------------------------------------------------
CARDINAL_ONES = {
    0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре",
    5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
}
CARDINAL_TEENS = {
    10: "десять", 11: "одиннадцать", 12: "двенадцать",
    13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
    16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
    19: "девятнадцать",
}
CARDINAL_TENS = {
    20: "двадцать", 30: "тридцать", 40: "сорок", 50: "пятьдесят",
    60: "шестьдесят", 70: "семьдесят", 80: "восемьдесят",
    90: "девяносто",
}
CARDINAL_HUNDREDS = {
    100: "сто", 200: "двести", 300: "триста", 400: "четыреста",
    500: "пятьсот", 600: "шестьсот", 700: "семьсот",
    800: "восемьсот", 900: "девятьсот",
}

CARDINAL_WORD_VALUES = {
    "ноль": 0,
    "один": 1, "одна": 1, "одно": 1,
    "два": 2, "две": 2,
    "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7,
    "восемь": 8, "девять": 9,
    **{v: k for k, v in CARDINAL_TEENS.items()},
    **{v: k for k, v in CARDINAL_TENS.items()},
    **{v: k for k, v in CARDINAL_HUNDREDS.items()},
}

ORDINAL_MASC = {
    0: "нулевой", 1: "первый", 2: "второй", 3: "третий", 4: "четвёртый",
    5: "пятый", 6: "шестой", 7: "седьмой", 8: "восьмой", 9: "девятый",
    10: "десятый", 11: "одиннадцатый", 12: "двенадцатый",
    13: "тринадцатый", 14: "четырнадцатый", 15: "пятнадцатый",
    16: "шестнадцатый", 17: "семнадцатый", 18: "восемнадцатый",
    19: "девятнадцатый", 20: "двадцатый", 30: "тридцатый",
    40: "сороковой", 50: "пятидесятый", 60: "шестидесятый",
    70: "семидесятый", 80: "восьмидесятый", 90: "девяностый",
    100: "сотый", 200: "двухсотый", 300: "трёхсотый",
    400: "четырёхсотый", 500: "пятисотый", 600: "шестисотый",
    700: "семисотый", 800: "восьмисотый", 900: "девятисотый",
    1000: "тысячный",
}

FEMININE_EXCEPTIONS = {
    "первый": "первая", "второй": "вторая", "третий": "третья",
    "четвёртый": "четвёртая", "седьмой": "седьмая", "восьмой": "восьмая",
    "сороковой": "сороковая",
}


def strip_stress(text: str) -> str:
    return text.replace(STRESS_MARK, "")


def int_to_cardinal(number: int) -> str:
    if number < 0:
        return "минус " + int_to_cardinal(-number)
    if number < 10:
        return CARDINAL_ONES[number]
    if number < 20:
        return CARDINAL_TEENS[number]
    if number < 100:
        tens, rest = divmod(number, 10)
        return CARDINAL_TENS[tens * 10] + (" " + CARDINAL_ONES[rest] if rest else "")
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        return CARDINAL_HUNDREDS[hundreds * 100] + (" " + int_to_cardinal(rest) if rest else "")
    if number < 1_000_000:
        thousands, rest = divmod(number, 1000)
        if thousands == 1:
            prefix = "одна тысяча"
        elif thousands == 2:
            prefix = "две тысячи"
        else:
            last_two = thousands % 100
            last = thousands % 10
            if 11 <= last_two <= 14:
                form = "тысяч"
            elif last == 1:
                form = "тысяча"
            elif last in (2, 3, 4):
                form = "тысячи"
            else:
                form = "тысяч"
            prefix = f"{int_to_cardinal(thousands)} {form}"
        return prefix + (" " + int_to_cardinal(rest) if rest else "")
    return str(number)


def _masculine_to_feminine(word: str) -> str:
    if word in FEMININE_EXCEPTIONS:
        return FEMININE_EXCEPTIONS[word]
    if word.endswith("ый") or word.endswith("ий"):
        return word[:-2] + "ая"
    if word.endswith("ой"):
        return word[:-2] + "ая"
    return word


def _masculine_to_neuter(word: str) -> str:
    exceptions = {
        "первый": "первое", "второй": "второе", "третий": "третье",
        "четвёртый": "четвёртое", "седьмой": "седьмое",
        "восьмой": "восьмое", "сороковой": "сороковое",
    }
    if word in exceptions:
        return exceptions[word]
    if word.endswith("ый") or word.endswith("ой"):
        return word[:-2] + "ое"
    if word.endswith("ий"):
        return word[:-2] + "ее"
    return word


def int_to_ordinal(number: int, gender: str = "m") -> str:
    """Порядковое числительное в именительном падеже.

    Для составных чисел порядковым становится только последний компонент:
    68 -> «шестьдесят восьмой», 1314 -> «одна тысяча триста четырнадцатый».
    """
    if number < 0:
        return "минус " + int_to_ordinal(-number, gender)

    if number in ORDINAL_MASC:
        result = ORDINAL_MASC[number]
    elif number < 100:
        tens, rest = divmod(number, 10)
        result = f"{CARDINAL_TENS[tens * 10]} {ORDINAL_MASC[rest]}"
    elif number < 1000:
        hundreds, rest = divmod(number, 100)
        if rest:
            result = f"{CARDINAL_HUNDREDS[hundreds * 100]} {int_to_ordinal(rest, 'm')}"
        else:
            result = ORDINAL_MASC[number]
    elif number < 1_000_000:
        thousands, rest = divmod(number, 1000)
        if rest:
            result = f"{_thousands_phrase(thousands)} {int_to_ordinal(rest, 'm')}"
        else:
            # В ссылках точные круглые тысячи редки. Эта форма остаётся
            # грамматически естественной и предсказуемой для TTS.
            if thousands == 1:
                result = "тысячный"
            else:
                result = f"{int_to_cardinal(thousands)} тысячный"
    else:
        result = str(number)

    if gender in {"f", "n"}:
        words = result.split()
        if gender == "f":
            words[-1] = _masculine_to_feminine(words[-1])
        else:
            words[-1] = _masculine_to_neuter(words[-1])
        result = " ".join(words)
    return result


def _thousands_phrase(number: int) -> str:
    if number == 1:
        return "одна тысяча"
    if number == 2:
        return "две тысячи"
    return f"{int_to_cardinal(number)} {_thousand_form(number)}"


def _thousand_form(number: int) -> str:
    last_two = number % 100
    last = number % 10
    if 11 <= last_two <= 14:
        return "тысяч"
    if last == 1:
        return "тысяча"
    if last in (2, 3, 4):
        return "тысячи"
    return "тысяч"


def parse_cardinal(text: str) -> int | None:
    """Разбирает русскую количественную запись или арабское/римское число."""
    value = strip_stress(text).strip().lower().replace("ё", "ё")
    value = re.sub(r"[.,;:]$", "", value).strip()
    if value.isdigit():
        return int(value)
    roman = roman_to_int(value.upper())
    if roman is not None:
        return roman

    tokens = re.findall(r"[а-яё]+", value)
    if not tokens:
        return None
    total = 0
    current = 0
    saw = False
    for token in tokens:
        if token in ("тысяча", "тысячи", "тысяч"):
            current = max(current, 1)
            total += current * 1000
            current = 0
            saw = True
            continue
        number = CARDINAL_WORD_VALUES.get(token)
        if number is None:
            return None
        current += number
        saw = True
    return total + current if saw else None


ROMAN_RE = re.compile(r"^[IVXLCM]+$", re.I)
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(value: str) -> int | None:
    value = value.upper().strip()
    if not value or not ROMAN_RE.fullmatch(value):
        return None
    total = 0
    previous = 0
    for char in reversed(value):
        number = ROMAN_VALUES[char]
        if number < previous:
            total -= number
        else:
            total += number
            previous = number
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# ТИПЫ ССЫЛОК
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Level:
    key: str
    singular: str
    gender: str = "m"
    plural: str | None = None


LEVELS = {
    "book": Level("book", "Книга", "f", "Книги"),
    "volume": Level("volume", "Том", "m", "Тома"),
    "part": Level("part", "Часть", "f", "Части"),
    "chapter": Level("chapter", "Глава", "f", "Главы"),
    "section": Level("section", "Раздел", "m", "Разделы"),
    "paragraph": Level("paragraph", "Параграф", "m", "Параграфы"),
    "title": Level("title", "Титул", "m", "Титулы"),
    "fragment": Level("fragment", "Фрагмент", "m", "Фрагменты"),
    "article": Level("article", "Статья", "f", "Статьи"),
    "verse": Level("verse", "Стих", "m", "Стихи"),
    "line": Level("line", "Строка", "f", "Строки"),
    "ode": Level("ode", "Ода", "f", "Оды"),
    "epigram": Level("epigram", "Эпиграмма", "f", "Эпиграммы"),
    "poem": Level("poem", "Стихотворение", "n", "Стихотворения"),
    "letter": Level("letter", "Письмо", "n", "Письма"),
    "codex": Level("codex", "Кодекс", "m", "Кодексы"),
    "region": Level("region", "Район", "m", "Районы"),
    "inscription": Level("inscription", "Надпись", "f", "Надписи"),
    "document": Level("document", "Документ", "m", "Документы"),
    "page": Level("page", "Страница", "f", "Страницы"),
    "column": Level("column", "Колонка", "f", "Колонки"),
    "ennead": Level("ennead", "Эннеада", "f", "Эннеады"),
    "treatise": Level("treatise", "Трактат", "m", "Трактаты"),
}

EXPLICIT_LABEL_ALIASES = {
    "книга": "book", "книги": "book",
    "том": "volume", "тома": "volume",
    "часть": "part", "части": "part",
    "глава": "chapter", "главы": "chapter",
    "раздел": "section", "разделы": "section",
    "пункт": "paragraph", "пункты": "paragraph",
    "параграф": "paragraph", "параграфы": "paragraph",
    "подпункт": "paragraph", "подпункты": "paragraph",
    "титул": "title", "титулы": "title",
    "фрагмент": "fragment", "фрагменты": "fragment",
    "статья": "article", "статьи": "article",
    "стих": "verse", "стихи": "verse",
    "строка": "line", "строки": "line",
    "ода": "ode", "оды": "ode",
    "эпиграмма": "epigram", "эпиграммы": "epigram",
    "письмо": "letter", "письма": "letter",
    "кодекс": "codex", "кодексы": "codex",
    "район": "region", "районы": "region",
    "номер": "document", "номера": "document",
    "надпись": "inscription", "надписи": "inscription",
    "страница": "page", "страницы": "page",
    "колонка": "column", "колонки": "column",
    "эннеада": "ennead", "эннеады": "ennead",
    "трактат": "treatise", "трактаты": "treatise",
}

# Произведения, где голые числовые уровни имеют устойчивое значение.
# Сопоставление идёт по подстроке в нормализованном источнике.
PROFILE_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    # Эпиграфика и специальные корпуса.
    (("цэ и эль", "corpus inscriptionum latinarum", "корпус латинских надписей"),
     ("volume", "inscription")),
    (("папирус пи кэйр зенон",), ("document",)),
    (("нотиция города рима",), ("region",)),
    (("дэ ка буква бэ", "дильс — кранц"), ("fragment",)),

    # Библия.
    (("евангелие от", "книга пророка", "книга самуила", "книга царств",
      "книга царей", "исход", "бытие", "псал", "притч", "екклесиаст",
      "даниил", "иеремии", "исаии"), ("chapter", "verse")),

    # Юридические корпуса.
    (("дигесты",), ("book", "title", "fragment", "paragraph")),
    (("гай. институции",), ("book", "paragraph")),

    # Пагинация античных философских текстов.
    (("платон. апология", "платон. государство", "платон. кратил"),
     ("page", "column")),
    (("аристотель. политика", "аристотель. метафизика"),
     ("book", "chapter", "page", "column")),
    (("плотин. эннеады",), ("ennead", "treatise", "chapter")),

    # Поэзия.
    (("гораций. оды",), ("book", "ode", "line")),
    (("гораций. послания",), ("book", "letter", "line")),
    (("марциал. книга зрелищ",), ("epigram", "line")),
    (("марциал. эпиграммы",), ("book", "epigram", "line")),
    (("стаций. сильвы",), ("book", "poem", "line")),
    (("вергилий. георгики", "вергилий. энеида", "гомер. илиада",
      "лукреций. о природе вещей", "овидий. фасты", "овидий. метаморфозы",
      "ювенал. сатиры"), ("book", "line")),
    (("гесиод. труды и дни", "катулл"), ("line",)),

    # Письма.
    (("сенека. нравственные письма",), ("letter", "paragraph")),
    (("плиний младший. письма",), ("book", "letter", "paragraph")),

    # Ссылки «книга — параграф», а не «книга — глава».
    (("плиний старший. естественная история",), ("book", "paragraph")),
    (("аппиан. гражданские войны",), ("book", "paragraph")),
    (("диоген лаэртский", "диоген лаертский"), ("book", "paragraph")),
    (("цицерон. о дивинации",), ("book", "paragraph")),
    (("варрон. о латинском языке",), ("book", "paragraph")),

    # Авторы с книгой, главой и параграфом.
    (("дион кассий", "тит ливий", "полибий",
      "прокопий кесарийский", "витрувий", "страбон",
      "диодор сицилийский", "аммиан марцеллин", "квинтилиан",
      "дионисий галикарнасский", "ксенофонт. греческая история",
      "феофраст", "палладий", "тацит. анналы"),
     ("book", "chapter", "paragraph")),

    # Книга и глава.
    (("геродот", "фукидид", "цезарь. записки",
      "варрон. о сельском хозяйстве", "колумелла", "ксенофонт. домострой",
      "вегеций", "герон александрийский. пневматика",
      "евсевий кесарийский", "марк аврелий. размышления"),
     ("book", "chapter", "paragraph")),

    # Главы и параграфы без уровня книги.
    (("фронтин. о водопроводах", "август. деяния божественного августа",
      "плутарх", "светоний", "история августов",
      "властелины августейшего дома", "саллюстий", "корнелий непот",
      "николай дамасский", "филострат", "аврелий виктор",
      "тацит. агрикола", "тацит. германия", "петроний", "эпиктет",
      "катон старший. о земледелии", "филон александрийский",
      "филон византийский", "ганнон. перипл", "арриан. поход александра",
      "письмо аристея"), ("chapter", "paragraph")),

    # Речи и тексты с последовательной параграфной нумерацией.
    (("цицерон. в защиту", "цицерон. брут", "элий аристид",
      "саллюстий. о заговоре катилины"), ("paragraph",)),

    # Сочинения Цицерона с трёхступенчатой ссылкой.
    (("цицерон. о законах",), ("book", "chapter", "paragraph")),
    (("цицерон. об ораторе",), ("book", "paragraph")),
]

DEFAULT_PROFILE = ("chapter", "paragraph")


def _detect_profile(text: str, reference_count: int = 0) -> tuple[str, ...]:
    lowered = text.lower().replace("ё", "е")
    # Иосиф Флавий часто цитируется либо как книга-глава-параграф, либо
    # как книга и сквозной параграф (например, «Иудейская война 2.383»).
    if "иосиф флавий" in lowered:
        return ("book", "chapter", "paragraph") if reference_count >= 3 else ("book", "paragraph")
    for needles, profile in PROFILE_RULES:
        for needle in needles:
            if needle.replace("ё", "е") in lowered:
                return profile
    return DEFAULT_PROFILE


def _capitalize_sentence(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def _ordinal_for_value(value_text: str, gender: str) -> str:
    number = parse_cardinal(value_text)
    if number is None:
        return value_text.strip()
    return int_to_ordinal(number, gender)


def _format_range(raw: str, level: Level) -> str | None:
    """Форматирует «семь — восемь» и уже словесные диапазоны."""
    value = raw.strip().rstrip(".")
    # Уже грамматически оформленные диапазоны оставляем, но убираем «номер».
    if re.search(r"\b(с|со)\s+", value, re.I) and re.search(r"\bпо\s+", value, re.I):
        cleaned = re.sub(r"\bномер(?:а|ов)?\s+", "", value, flags=re.I)
        match = re.match(r"^(?:с|со)\s+(.+?)\s+по\s+(.+)$", cleaned, flags=re.I)
        if match:
            first = parse_cardinal(match.group(1))
            second = parse_cardinal(match.group(2))
            if first is not None and second is not None:
                plural = level.plural or level.singular
                return (
                    f"{plural} {int_to_ordinal(first, level.gender)} — "
                    f"{int_to_ordinal(second, level.gender)}"
                )
        plural = level.plural or level.singular
        return f"{plural} {cleaned}"

    parts = re.split(r"\s*[—–-]\s*", value, maxsplit=1)
    if len(parts) != 2:
        return None
    first = parse_cardinal(parts[0])
    second = parse_cardinal(parts[1])
    if first is None or second is None:
        return None
    plural = level.plural or level.singular
    return (
        f"{plural} {int_to_ordinal(first, level.gender)} — "
        f"{int_to_ordinal(second, level.gender)}"
    )


def _format_level_value(level_key: str, raw_value: str) -> str:
    level = LEVELS[level_key]
    raw_value, suffix = _split_reference_suffix(raw_value)
    ranged = _format_range(raw_value, level)
    if ranged:
        return ranged + "."
    if _number_list_segment(raw_value):
        first, second = re.split(r"\s+и\s+", raw_value, maxsplit=1, flags=re.I)
        first_number = parse_cardinal(first)
        second_number = parse_cardinal(second)
        assert first_number is not None and second_number is not None
        plural = level.plural or level.singular
        return (
            f"{plural} {int_to_ordinal(first_number, level.gender)} и "
            f"{int_to_ordinal(second_number, level.gender)}."
        )
    result = f"{level.singular} {_ordinal_for_value(raw_value, level.gender)}."
    if suffix:
        result += f" {suffix}."
    return result


def _replace_inline_bible_chapter(text: str) -> str:
    # «Исход глава номер четырнадцать» -> «Исход. Глава четырнадцатая».
    pattern = re.compile(
        r"^(?P<title>.+?)\s+глава\s+(?:номер\s+)?(?P<num>[а-яё\s\dIVXLCM]+)$",
        re.I,
    )
    match = pattern.match(text.strip())
    if not match:
        return text
    title = match.group("title").strip(" ,")
    number = match.group("num").strip()
    return f"{title}. {_format_level_value('chapter', number).rstrip()}"


def _normalize_special_names(text: str) -> str:
    text = re.sub(r"\bЦэ\s+и\s+эль\b", "Корпус латинских надписей", text, flags=re.I)
    text = re.sub(r"\bCIL\b", "Корпус латинских надписей", text, flags=re.I)
    text = re.sub(
        r"\bФрагмент\s+дэ\s+ка\s+буква\s+бэ\b",
        "Дильс — Кранц. Серия Б",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\bфрагмент\s+([А-Яа-яЁё]+)\s+дэ\s+ка\s+буква\s+бэ\b",
        r"Дильс — Кранц. \1. Серия Б",
        text,
        flags=re.I,
    )
    text = re.sub(r"\bср\.\s*", "для сравнения ", text, flags=re.I)
    text = re.sub(r"\b1\s+Kings\b", "Третья книга Царств, или Первая книга Царей", text, flags=re.I)
    text = re.sub(r"\b2\s+Kings\b", "Четвёртая книга Царств, или Вторая книга Царей", text, flags=re.I)
    text = re.sub(r"\s*/\s*", ". или ", text)
    return text


def _split_segments(text: str) -> list[str]:
    # Точка — основной разделитель. Точку внутри сокращений у нас предварительно
    # не ожидается: исходные JSON уже используют проговариваемые названия.
    return [
        segment.strip(" \t\n;")
        for segment in re.split(r"\s*[.;]\s*", text)
        if segment.strip(" \t\n;")
    ]


def _explicit_segment(segment: str, profile: Sequence[str]) -> tuple[str, str] | None:
    """Возвращает (заявленный уровень, сырое значение)."""
    original = segment.strip()
    lowered = original.lower()

    letter = re.match(r"^буква\s+(.+)$", original, flags=re.I)
    if letter:
        value = re.sub(r"\s+по\s+букву\s+", " — ", letter.group(1).strip(), flags=re.I)
        return "column", value

    if lowered in {"предисловие", "введение"}:
        return "special", _capitalize_sentence(original)

    match = re.match(
        r"^(?P<label>[А-Яа-яЁё]+)\s+(?:номер(?:а|ов)?\s+)?(?P<value>.+)$",
        original,
    )
    if not match:
        return None
    alias = match.group("label").lower()
    level_key = EXPLICIT_LABEL_ALIASES.get(alias)
    if not level_key:
        return None

    if alias.startswith("номер"):
        if "inscription" in profile:
            level_key = "inscription"
        elif "document" in profile:
            level_key = "document"

    value = match.group("value").strip()
    if not _numeric_segment(value) and not _number_list_segment(value) and not (
        re.search(r"\b(с|со)\s+", value, re.I) and re.search(r"\bпо\s+", value, re.I)
    ):
        return None
    return level_key, value


def _split_reference_suffix(value: str) -> tuple[str, str]:
    cleaned = value.strip().rstrip(".")
    match = re.match(r"^(?P<number>.+?)\s+(?P<suffix>пэ\s+эр|pr)$", cleaned, flags=re.I)
    if match and parse_cardinal(match.group("number")) is not None:
        return match.group("number").strip(), "Принципиум"
    return cleaned, ""


def _number_list_segment(segment: str) -> bool:
    value = segment.strip().rstrip(".")
    parts = re.split(r"\s+и\s+", value, maxsplit=1, flags=re.I)
    return len(parts) == 2 and all(parse_cardinal(part) is not None for part in parts)


def _numeric_segment(segment: str) -> bool:
    value, _suffix = _split_reference_suffix(segment)
    if parse_cardinal(value) is not None:
        return True
    parts = re.split(r"\s*[—–-]\s*", value, maxsplit=1)
    return len(parts) == 2 and all(parse_cardinal(part) is not None for part in parts)


def _next_level_index(profile: Sequence[str], explicit_key: str, current: int) -> int:
    # Ищем совпадение не раньше текущего уровня, затем двигаемся дальше.
    for index in range(current, len(profile)):
        if profile[index] == explicit_key:
            return index + 1
    # Некоторые источники используют «раздел» вместо главы и «пункт» вместо
    # параграфа. Считаем их эквивалентными для продвижения по профилю.
    equivalents = {
        "section": {"chapter", "section"},
        "chapter": {"chapter", "section"},
        "paragraph": {"paragraph", "section"},
        "document": {"document", "inscription"},
        "inscription": {"inscription", "document"},
    }
    possible = equivalents.get(explicit_key, {explicit_key})
    for index in range(current, len(profile)):
        if profile[index] in possible:
            return index + 1
    return current


def _cleanup_sentences(sentences: Iterable[str]) -> str:
    text = " ".join(sentence.strip() for sentence in sentences if sentence.strip())
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+([,;:.])", r"\1", text)
    return text.strip()


def format_source_reference(source: str) -> str:
    """Возвращает единообразный текст источника для TTS.

    Функция идемпотентна: повторная обработка уже нормализованного текста не
    добавляет второй набор меток.
    """
    text = strip_stress(str(source)).strip()
    if not text:
        return ""
    text = text.replace("“", "«").replace("”", "»")
    text = text.replace("«", "").replace("»", "")
    text = re.sub(r"^[—–-]\s*", "", text)

    # В одной записи сопоставлены две разные системы пагинации. Обрабатываем
    # их раздельно, чтобы стефановская страница Платона не превратилась во
    # «фрагмент», а номер Дильса — Кранца не стал «документом».
    if (
        "Платон. Кратил" in text
        and "Гераклита" in text
        and re.search(r"дэ\s+ка\s+буква\s+бэ", text, flags=re.I)
    ):
        match = re.search(
            r"Платон\.\s*Кратил\.\s*(?P<page>.+?)\.\s*"
            r"Буква\s+(?P<column>[^;]+);\s*"
            r"для\s+сравнения\s+фрагмент\s+Гераклита\s+"
            r"дэ\s+ка\s+буква\s+бэ\.\s*"
            r"Номер\s+(?P<fragment>.+?)\.?$",
            text,
            flags=re.I,
        )
        if match:
            page = parse_cardinal(match.group("page"))
            fragment = parse_cardinal(match.group("fragment"))
            if page is not None and fragment is not None:
                column = match.group("column").strip()
                return (
                    "Платон. Кратил. "
                    f"Страница {int_to_ordinal(page, 'f')}. "
                    f"Колонка {column}. Для сравнения. "
                    "Дильс — Кранц. Гераклит. Серия Б. "
                    f"Фрагмент {int_to_ordinal(fragment, 'm')}."
                )

    text = _normalize_special_names(text)
    text = re.sub(
        r"\b(Предисловие|Введение),\s*(?=(?:пункт|параграф|раздел|глава|номер)\b)",
        r"\1. ",
        text,
        flags=re.I,
    )

    # Библейская глава иногда приклеена к названию книги без точки.
    raw_segments = _split_segments(text)
    expanded: list[str] = []
    for segment in raw_segments:
        inline = _replace_inline_bible_chapter(segment)
        expanded.extend(_split_segments(inline))
    segments = expanded

    reference_count = sum(
        1 for segment in segments
        if _numeric_segment(segment) or _number_list_segment(segment) or _explicit_segment(segment, DEFAULT_PROFILE)
    )
    profile = _detect_profile(text, reference_count)
    level_index = 0
    result: list[str] = []

    for segment in segments:
        explicit = _explicit_segment(segment, profile)
        if explicit:
            declared_key, raw_value = explicit
            if declared_key == "special":
                result.append(raw_value.rstrip(".") + ".")
                # После предисловия следующая цифра обычно обозначает параграф,
                # а не книгу или главу.
                if "paragraph" in profile:
                    level_index = profile.index("paragraph")
                continue

            # Для обычных меток используем иерархию конкретного произведения.
            # Так «Раздел 1. Пункт 1. Подпункт 10» в Дигестах становится
            # «Книга первая. Титул первый. Фрагмент десятый».
            generic_declared = declared_key in {"section", "chapter", "paragraph", "title", "fragment"}
            follows_profile = declared_key in profile
            if declared_key == "book" and profile and profile[0] in {"letter", "ennead"}:
                generic_declared = True
            if declared_key == "document" and profile and profile[0] == "fragment":
                generic_declared = True
            force_profile = (
                declared_key == "document" and profile and profile[0] == "fragment"
            )
            if (
                level_index < len(profile)
                and (
                    declared_key not in {
                        "volume", "part", "verse", "line", "ode", "epigram",
                        "letter", "codex", "region", "inscription", "document",
                        "page", "column", "ennead", "treatise",
                    }
                    or force_profile
                )
                and (follows_profile or generic_declared)
            ):
                effective_key = profile[level_index]
                level_index += 1
            else:
                effective_key = declared_key
                if declared_key in profile:
                    level_index = _next_level_index(profile, declared_key, level_index)
            result.append(_format_level_value(effective_key, raw_value))
            continue

        if _numeric_segment(segment) or _number_list_segment(segment):
            level_key = profile[level_index] if level_index < len(profile) else "paragraph"
            result.append(_format_level_value(level_key, segment))
            level_index += 1
            continue

        # Особые конструкции внутри одного сегмента.
        segment = re.sub(r"\bКнига\s+номер\s+", "Книга ", segment, flags=re.I)
        segment = re.sub(r"\bГлава\s+номер\s+", "Глава ", segment, flags=re.I)
        segment = re.sub(r"\bРаздел\s+номер\s+", "Раздел ", segment, flags=re.I)
        segment = re.sub(r"\bПункт\s+номер\s+", "Параграф ", segment, flags=re.I)
        result.append(_capitalize_sentence(segment).rstrip(".") + ".")

    return _cleanup_sentences(result)


def find_unlabelled_reference_segments(source: str) -> list[str]:
    """Находит оставшиеся самостоятельные числовые сегменты после форматирования."""
    formatted = format_source_reference(source)
    return [segment for segment in _split_segments(formatted) if _numeric_segment(segment)]


def run_self_test() -> None:
    examples = {
        "Дион Кассий. Римская история. Книга шестьдесят восемь. Три. Четыре.":
            "Дион Кассий. Римская история. Книга шестьдесят восьмая. Глава третья. Параграф четвёртый.",
        "Плутарх. Александр. Пятьдесят восемь. Два.":
            "Плутарх. Александр. Глава пятьдесят восьмая. Параграф второй.",
        "Страбон. География. Книга семнадцать. Один. Шесть.":
            "Страбон. География. Книга семнадцатая. Глава первая. Параграф шестой.",
        "Надпись на фронтоне Пантеона. Цэ и эль. Шесть. Восемьсот девяносто шесть.":
            "Надпись на фронтоне Пантеона. Корпус латинских надписей. Том шестой. Надпись восемьсот девяносто шестая.",
        "Евангелие от Матфея. Глава номер двадцать два. Стих номер двадцать один.":
            "Евангелие от Матфея. Глава двадцать вторая. Стих двадцать первый.",
    }
    failures = []
    for raw, expected in examples.items():
        actual = format_source_reference(raw)
        if actual != expected:
            failures.append((raw, expected, actual))
    if failures:
        lines = ["Ошибки самопроверки reference_formatter.py:"]
        for raw, expected, actual in failures:
            lines.extend([f"RAW: {raw}", f"EXP: {expected}", f"ACT: {actual}"])
        raise AssertionError("\n".join(lines))


if __name__ == "__main__":
    run_self_test()
    print("reference_formatter.py: самопроверка пройдена.")

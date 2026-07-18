#!/usr/bin/env python3
"""
Озвучка цитат Roma Aeterna через Silero TTS.

Что улучшено:
1. Автоматические ударения: silero-stress -> StressRNN -> встроенный акцентор TTS.
2. Ручные ударения вынесены в stress_dictionary.json.
3. Латинские слова и выражения перед озвучкой заменяются кириллическим
   произношением из stress_dictionary.json.
4. Источники читаются отдельно и естественнее: «Источник...», римские и
   арабские ссылки превращаются в устную форму.
5. Паузы на тире, двоеточиях и точках с запятой сделаны более дикторскими.
6. Для отдельного текста озвучки поддерживаются поля tts_quote/voice_quote;
   обычное поле quote может оставаться чистым и красивым для интерфейса.
7. WAV сохраняются в корневой каталог игры audio/, а не рядом с JSON.

Обязательная установка (Termux):
    pip install torch omegaconf --break-system-packages

Необязательный внешний акцентор:
    # На x86-64 / обычном ПК — предпочтительный вариант:
    pip install silero-stress

    # Резервный вариант, если он устанавливается в вашей среде:
    pip install git+https://github.com/Desklop/StressRNN

Если внешнего акцентора нет, скрипт не падает: остаются ручной словарь и
встроенные ударения Silero TTS.

Запуск:
    python generate_voiceover_silero_fixed.py

Перегенерировать уже существующие WAV:
    python generate_voiceover_silero_fixed.py --overwrite

Посмотреть подготовленный текст без генерации звука:
    python generate_voiceover_silero_fixed.py --preview 3
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

# ---------------------------------------------------------------------------
# НАСТРОЙКИ
# ---------------------------------------------------------------------------
SPEAKER = "eugene"
SAMPLE_RATE = 48000
DEEPEN = 0.92

# Новая русская модель лучше различает омографы. Если она не загрузится,
# скрипт автоматически вернётся к вашей прежней v4_ru.
DEFAULT_MODEL_ID = "v5_5_ru"
FALLBACK_MODEL_IDS = ("v5_3_ru", "v4_ru")

DICTIONARY_FILE = "stress_dictionary.json"

# Паузы создаются только пунктуацией: это надёжнее SSML на разных версиях
# Silero и не ломает Termux.
PAUSE_SHORT = ", ... "
PAUSE_MEDIUM = ". ... "
PAUSE_LONG = ". ... ... "

SOURCES = [
    ("world_wonder_quotes.json", "world_wonders"),
    ("great_people_quotes.json", "great_people"),
    ("tech_quotes.json", "tech"),
]

QUOTE_RE = re.compile(r'^[«"]?(.*?)[»"]?$', re.DOTALL)
ROMAN_TOKEN_RE = re.compile(r"\b[IVXLCM]{1,8}\b")
CYRILLIC_VOWELS = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"

ROMAN_VALUES = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]

ONES = {
    0: "ноль", 1: "один", 2: "два", 3: "три", 4: "четыре",
    5: "пять", 6: "шесть", 7: "семь", 8: "восемь", 9: "девять",
}
TEENS = {
    10: "десять", 11: "одиннадцать", 12: "двенадцать",
    13: "тринадцать", 14: "четырнадцать", 15: "пятнадцать",
    16: "шестнадцать", 17: "семнадцать", 18: "восемнадцать",
    19: "девятнадцать",
}
TENS = {
    20: "двадцать", 30: "тридцать", 40: "сорок", 50: "пятьдесят",
    60: "шестьдесят", 70: "семьдесят", 80: "восемьдесят",
    90: "девяносто",
}
HUNDREDS = {
    100: "сто", 200: "двести", 300: "триста", 400: "четыреста",
    500: "пятьсот", 600: "шестьсот", 700: "семьсот",
    800: "восемьсот", 900: "девятьсот",
}


@dataclass
class PronunciationDictionary:
    stress_overrides: dict[str, str]
    latin_pronunciation: dict[str, str]


@dataclass
class AutoAccentor:
    name: str
    apply: Callable[[str], str]


def roman_to_int(value: str) -> int:
    value = value.upper().strip()
    if not value:
        return 0
    result = 0
    index = 0
    for number, symbol in ROMAN_VALUES:
        while value[index:index + len(symbol)] == symbol:
            result += number
            index += len(symbol)
            if index >= len(value):
                return result
    return result if index == len(value) else 0


def int_to_words(number: int) -> str:
    """Русская запись целого числа от 0 до 999999 без внешних библиотек."""
    if number < 0:
        return "минус " + int_to_words(-number)
    if number < 10:
        return ONES[number]
    if number < 20:
        return TEENS[number]
    if number < 100:
        tens, rest = divmod(number, 10)
        return TENS[tens * 10] + (" " + ONES[rest] if rest else "")
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        return HUNDREDS[hundreds * 100] + (" " + int_to_words(rest) if rest else "")
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
            prefix = f"{int_to_words(thousands)} {form}"
        return prefix + (" " + int_to_words(rest) if rest else "")
    return str(number)


def load_pronunciation_dictionary(base_dir: Path) -> PronunciationDictionary:
    path = base_dir / DICTIONARY_FILE
    if not path.exists():
        print(f"ВНИМАНИЕ: {DICTIONARY_FILE} не найден. Ручные и латинские замены отключены.")
        return PronunciationDictionary({}, {})

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ВНИМАНИЕ: не удалось прочитать {path.name}: {exc}")
        return PronunciationDictionary({}, {})

    stress = payload.get("stress_overrides", {})
    latin = payload.get("latin_pronunciation", {})
    if not isinstance(stress, dict) or not isinstance(latin, dict):
        print(f"ВНИМАНИЕ: неверный формат {path.name}; ожидались два словаря.")
        return PronunciationDictionary({}, {})

    return PronunciationDictionary(
        {str(k): str(v) for k, v in stress.items()},
        {str(k): str(v) for k, v in latin.items()},
    )


def stress_after_to_before(text: str) -> str:
    """StressRNN: `а+`; Silero: `+а`. Переводит первый формат во второй."""
    return re.sub(rf"([{CYRILLIC_VOWELS}])\+", r"+\1", text)


def combining_acute_to_silero(text: str) -> str:
    """Переводит Unicode-ударение `а́` в формат Silero `+а`."""
    return re.sub(rf"([{CYRILLIC_VOWELS}])\u0301", r"+\1", text)


def load_auto_accentor(disabled: bool = False) -> AutoAccentor | None:
    if disabled:
        print("Внешний акцентор отключён параметром командной строки.")
        return None

    # Новый официальный акцентор Silero. Пакет рассчитан прежде всего на x86-64;
    # поэтому ошибка импорта/инициализации здесь не является фатальной.
    try:
        from silero_stress import load_accentor  # type: ignore

        accentor = load_accentor()

        def apply_silero_stress(text: str) -> str:
            return combining_acute_to_silero(accentor(text))

        print("Автоматические ударения: silero-stress.")
        return AutoAccentor("silero-stress", apply_silero_stress)
    except Exception as exc:
        print(f"silero-stress недоступен ({platform.machine()}): {exc}")

    # Совместимость с предложенным ранее StressRNN.
    try:
        from stressrnn import StressRNN  # type: ignore

        stress_rnn = StressRNN()

        def apply_stress_rnn(text: str) -> str:
            result = stress_rnn.put_stress(
                text,
                stress_symbol="+",
                accuracy_threshold=0.75,
                replace_similar_symbols=False,
            )
            return stress_after_to_before(result)

        print("Автоматические ударения: StressRNN.")
        return AutoAccentor("StressRNN", apply_stress_rnn)
    except Exception as exc:
        print(f"StressRNN недоступен: {exc}")

    print("Внешний акцентор не найден; используются словарь и автоударения Silero TTS.")
    return None


def _replacement_pattern(key: str) -> re.Pattern[str]:
    """Границы не дают замене `Август` портить слово `Августейший`."""
    left = r"(?<![0-9A-Za-zА-Яа-яЁё_])" if key and key[0].isalnum() else ""
    right = r"(?![0-9A-Za-zА-Яа-яЁё_])" if key and key[-1].isalnum() else ""
    return re.compile(left + re.escape(key) + right)


def protect_replacements(
    text: str,
    replacements: dict[str, str],
    protected: dict[str, str],
    prefix: str,
) -> str:
    """Заменяет словарные фрагменты маркерами, чтобы автоакцентор их не испортил."""
    for key in sorted(replacements, key=len, reverse=True):
        replacement = replacements[key]
        pattern = _replacement_pattern(key)

        def repl(_: re.Match[str], value: str = replacement) -> str:
            marker = f"ZXQ{prefix}{len(protected):05d}QXZ"
            protected[marker] = value
            return marker

        text = pattern.sub(repl, text)
    return text


def restore_protected(text: str, protected: dict[str, str]) -> str:
    for marker, value in protected.items():
        text = text.replace(marker, value)
    return text


def normalize_reference_numbers(text: str) -> str:
    """Превращает библиографические, эпиграфические и библейские ссылки в речь."""
    superscripts = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

    def spoken_number(value: str) -> str:
        return int_to_words(int(value))

    def join_levels(values: list[int], labels: list[str]) -> str:
        parts = []
        for index, value in enumerate(values):
            label = labels[index] if index < len(labels) else "подпункт номер"
            parts.append(f"{label} {int_to_words(value)}")
        return ", ".join(parts)

    # CIL I² 25 и сходные эпиграфические обозначения.
    def superscript_reference(match: re.Match[str]) -> str:
        volume = roman_to_int(match.group(1))
        part = int(match.group(2).translate(superscripts))
        record = int(match.group(3))
        return (
            f"том номер {int_to_words(volume)}, часть номер {int_to_words(part)}, "
            f"запись номер {int_to_words(record)}"
        )

    text = re.sub(
        r"\b([IVXLCM]+)([⁰¹²³⁴⁵⁶⁷⁸⁹]+)\s+(\d+)\b",
        superscript_reference,
        text,
    )

    # Библия: 14:13, 27:3–4.
    def biblical_reference(match: re.Match[str]) -> str:
        chapter = int(match.group(1))
        first_verse = int(match.group(2))
        last_verse = match.group(3)
        result = (
            f"глава номер {int_to_words(chapter)}, "
            f"стих номер {int_to_words(first_verse)}"
        )
        if last_verse:
            result = (
                f"глава номер {int_to_words(chapter)}, стихи с номера "
                f"{int_to_words(first_verse)} по номер {int_to_words(int(last_verse))}"
            )
        return result

    text = re.sub(
        r"\b(\d+):(\d+)(?:\s*[–—-]\s*(\d+))?\b",
        biblical_reference,
        text,
    )

    # Римская книга и диапазон: I, 146–148.
    def roman_comma_range(match: re.Match[str]) -> str:
        book = roman_to_int(match.group(1))
        first = int(match.group(2))
        last = int(match.group(3))
        return (
            f"книга номер {int_to_words(book)}, разделы с номера "
            f"{int_to_words(first)} по номер {int_to_words(last)}"
        )

    text = re.sub(
        r"\b([IVXLCM]+),\s*(\d+)\s*[–—-]\s*(\d+)\b",
        roman_comma_range,
        text,
    )

    # Ссылки с точками: II.9.36, XVII.1.8, I.3.2.
    def roman_dotted(match: re.Match[str]) -> str:
        values = [roman_to_int(match.group(1))]
        values.extend(int(value) for value in match.group(2).split(".") if value)
        return join_levels(
            values,
            ["книга номер", "раздел номер", "пункт номер", "подпункт номер"],
        )

    text = re.sub(
        r"\b([IVXLCM]+)((?:\.\d+){1,4})\b",
        roman_dotted,
        text,
    )

    # Полностью цифровые ссылки Дигест: 1.2.2.47, 50.17.202, 11.2.
    def arabic_dotted(match: re.Match[str]) -> str:
        values = [int(match.group(1))]
        values.extend(int(value) for value in match.group(2).split(".") if value)
        return join_levels(
            values,
            ["раздел номер", "пункт номер", "подпункт номер", "часть номер"],
        )

    text = re.sub(r"\b(\d+)((?:\.\d+){1,4})\b", arabic_dotted, text)

    # III, 3, 8 или III, 3.
    def roman_comma(match: re.Match[str]) -> str:
        values = [roman_to_int(match.group(1)), int(match.group(2))]
        if match.group(3):
            values.append(int(match.group(3)))
        return join_levels(values, ["книга номер", "раздел номер", "пункт номер"])

    text = re.sub(
        r"\b([IVXLCM]+),\s*(\d+)(?:,\s*(\d+))?\b",
        roman_comma,
        text,
    )

    # 53, 146 — две ступени цифровой ссылки.
    def arabic_comma(match: re.Match[str]) -> str:
        values = [int(match.group(1)), int(match.group(2))]
        if match.group(3):
            values.append(int(match.group(3)))
        return join_levels(values, ["раздел номер", "пункт номер", "подпункт номер"])

    text = re.sub(
        r"\b(\d+),\s*(\d+)(?:,\s*(\d+))?\b",
        arabic_comma,
        text,
    )

    # Обычный цифровой диапазон, ещё не поглощённый предыдущими правилами.
    text = re.sub(
        r"\b(\d+)\s*[–—-]\s*(\d+)\b",
        lambda m: (
            f"с номера {spoken_number(m.group(1))} "
            f"по номер {spoken_number(m.group(2))}"
        ),
        text,
    )

    def latin_letter_name(letter: str) -> str:
        return {
            "a": "а", "b": "бэ", "c": "цэ", "d": "дэ",
            "e": "е", "f": "эф",
        }.get(letter.lower(), letter.lower())

    # 38a, 473c-d.
    def alphanumeric_section(match: re.Match[str]) -> str:
        number = int(match.group(1))
        first_letter = latin_letter_name(match.group(2))
        last_letter = match.group(3)
        result = f"{int_to_words(number)}, буква {first_letter}"
        if last_letter:
            result += f" по букву {latin_letter_name(last_letter)}"
        return result

    text = re.sub(
        r"\b(\d+)([A-Za-z])(?:[–—-]([A-Za-z]))?\b",
        alphanumeric_section,
        text,
    )

    # B91 и аналогичные каталожные индексы.
    text = re.sub(
        r"\b([A-Za-z])(\d+)\b",
        lambda m: (
            f"буква {latin_letter_name(m.group(1))}, "
            f"номер {int_to_words(int(m.group(2)))}"
        ),
        text,
    )

    # Сокращения библиографического аппарата.
    text = re.sub(
        r"\bкн\.\s*(\d+)\b",
        lambda m: f"книга номер {spoken_number(m.group(1))}",
        text,
        flags=re.IGNORECASE,
    )

    # Оставшиеся римские цифры обычно обозначают книгу, том или район.
    text = ROMAN_TOKEN_RE.sub(
        lambda m: (
            f"книга номер {int_to_words(roman_to_int(m.group(0)))}"
            if roman_to_int(m.group(0)) > 0 else m.group(0)
        ),
        text,
    )

    # Наконец, проговариваем все одиночные арабские числа, чтобы TTS не
    # импровизировал с чтением 51, 66 и подобных обозначений.
    text = re.sub(r"\b\d+\b", lambda m: spoken_number(m.group(0)), text)
    return text


def add_natural_pauses(text: str) -> str:
    """Паузы без SSML: одинаково работают на v4/v5 и в Termux."""
    text = text.replace("…", "...")
    text = re.sub(r"\s*[—–]\s*", PAUSE_SHORT, text)
    text = re.sub(r"\s*;\s*", PAUSE_MEDIUM, text)
    text = re.sub(r"\s*:\s*", PAUSE_SHORT, text)
    text = re.sub(r"\.{4,}", "...", text)
    text = re.sub(r"\s*\.\.\.\s*", " ... ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def has_complete_explicit_stress(text: str) -> bool:
    """True, если в каждом произносимом кириллическом слове уже задано ударение."""
    word_re = re.compile(r"[А-Яа-яЁё+]+(?:-[А-Яа-яЁё+]+)*")
    for token in word_re.findall(text):
        for part in token.split("-"):
            bare = part.replace("+", "")
            if not any(ch in CYRILLIC_VOWELS for ch in bare):
                continue
            if part.count("+") != 1:
                return False
            stress_index = part.index("+")
            if (
                stress_index + 1 >= len(part)
                or part[stress_index + 1] not in CYRILLIC_VOWELS
            ):
                return False
    return True


def prepare_pronunciation(
    text: str,
    dictionary: PronunciationDictionary,
    accentor: AutoAccentor | None,
) -> str:
    text = combining_acute_to_silero(text)

    # Новые исходные JSON уже полностью размечены. Повторный прогон через
    # словарь мог поставить второе ударение внутри имён вроде
    # «Александр+ийский» -> «Алекс+андр+ийский». В полностью размеченной
    # строке ничего переакцентировать не нужно.
    if has_complete_explicit_stress(text):
        return re.sub(r"\+{2,}", "+", text)

    protected: dict[str, str] = {}

    # Сначала длинные латинские фразы, затем ручные русские ударения.
    text = protect_replacements(
        text, dictionary.latin_pronunciation, protected, "LAT"
    )
    text = protect_replacements(
        text, dictionary.stress_overrides, protected, "STR"
    )

    if accentor is not None:
        try:
            text = accentor.apply(text)
        except Exception as exc:
            print(f"ВНИМАНИЕ: {accentor.name} не обработал строку: {exc}")

    text = restore_protected(text, protected)
    # Если исходный JSON уже содержит ручное ударение перед первой буквой
    # (например, +Август), словарная замена могла оставить два плюса.
    # Для Silero это одно и то же ударение, поэтому безопасно схлопываем его.
    text = re.sub(r"\+{2,}", "+", text)
    return combining_acute_to_silero(text)


def process_text(
    text: str,
    dictionary: PronunciationDictionary,
    accentor: AutoAccentor | None,
    *,
    is_source: bool = False,
) -> str:
    text = text.strip()
    if not text:
        return ""

    text = text.replace("“", "«").replace("”", "»")
    if not is_source:
        # В самих цитатах встречаются обозначения вроде «XIII района» и
        # годы вроде «212 года» — проговариваем их словами.
        text = ROMAN_TOKEN_RE.sub(
            lambda m: (
                int_to_words(roman_to_int(m.group(0)))
                if roman_to_int(m.group(0)) > 0 else m.group(0)
            ),
            text,
        )
        text = re.sub(r"\b\d+\b", lambda m: int_to_words(int(m.group(0))), text)

    if is_source:
        text = re.sub(r"^[—–-]\s*", "", text)
        text = text.replace("«", "").replace("»", "")
        text = re.sub(r"\bср\.\s*", "для сравнения ", text, flags=re.IGNORECASE)
        text = re.sub(r"\b1\s+Kings\b", "Первая книга Царств", text, flags=re.IGNORECASE)
        text = re.sub(r"\b2\s+Kings\b", "Вторая книга Царств", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*/\s*", ". или ", text)
        text = normalize_reference_numbers(text)
        # Автор, название и ссылка должны звучать как отдельные такты.
        text = re.sub(r",\s*", ". ", text)
        text = "Ист+очник. " + text

    text = add_natural_pauses(text)
    text = prepare_pronunciation(text, dictionary, accentor)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def split_embedded_source(quote_text: str, source_text: str) -> tuple[str, str]:
    """
    В world_wonder_quotes.json атрибуция часто хранится прямо в quote.
    Источник отделён последним тире с пробелами; именно последнее тире важно,
    потому что внутри самой цитаты тире тоже встречаются.
    """
    if source_text.strip():
        return quote_text, source_text

    parts = re.split(r"\s+[—–]\s+", quote_text.strip())
    if len(parts) >= 2:
        return " — ".join(parts[:-1]).strip(), parts[-1].strip()

    match = re.match(
        r"^\s*[«\"](?P<quote>.*?)[»\"]\s*-\s*(?P<source>.+?)\s*$",
        quote_text,
        flags=re.DOTALL,
    )
    if match:
        return match.group("quote").strip(), match.group("source").strip()
    return quote_text, source_text


def clean_quote(
    text: str,
    dictionary: PronunciationDictionary,
    accentor: AutoAccentor | None,
) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in '«"' and text[-1] in '»"':
        text = text[1:-1].strip()
    else:
        match = QUOTE_RE.match(text)
        text = match.group(1).strip() if match else text
    # Кавычки не произносятся и могут мешать границам словарных замен.
    text = (
        text.replace("«", "").replace("»", "")
        .replace("„", "").replace("“", "").replace('"', "")
    )
    return process_text(text, dictionary, accentor)


def clean_source(
    text: str,
    dictionary: PronunciationDictionary,
    accentor: AutoAccentor | None,
) -> str:
    return process_text(text, dictionary, accentor, is_source=True)




def entry_voice_quote(entry: dict) -> str:
    """Берёт отдельный TTS-текст, не заставляя показывать его в интерфейсе."""
    for field in ("tts_quote", "voice_quote", "quote"):
        value = str(entry.get(field, "")).strip()
        if value:
            return value
    return ""


def project_root_for(base_dir: Path) -> Path:
    """Определяет корень игры для стандартной схемы game/data/quotes."""
    if base_dir.name == "quotes" and base_dir.parent.name == "data":
        return base_dir.parent.parent
    return base_dir


def compose_entry_text(
    entry: dict,
    dictionary: PronunciationDictionary,
    accentor: AutoAccentor | None,
) -> str:
    raw_quote, raw_source = split_embedded_source(
        entry_voice_quote(entry),
        str(entry.get("source", "")),
    )
    quote = clean_quote(raw_quote, dictionary, accentor).rstrip(" .;,")
    source = clean_source(raw_source, dictionary, accentor)
    if source:
        return f"{quote}{PAUSE_LONG}{source}"
    return quote


def import_torch():
    try:
        import torch  # type: ignore
    except ImportError:
        sys.exit(
            "Не найден torch. Установите: "
            "pip install torch omegaconf --break-system-packages"
        )
    return torch


def load_model(requested_model_id: str):
    torch = import_torch()
    print("Загружаю модель Silero (первый раз потребуется интернет)...")

    candidates: list[str] = []
    for model_id in (requested_model_id, *FALLBACK_MODEL_IDS):
        if model_id not in candidates:
            candidates.append(model_id)

    last_error: Exception | None = None
    for model_id in candidates:
        try:
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language="ru",
                speaker=model_id,
            )
            model.to(torch.device("cpu"))
            print(f"Модель загружена: {model_id}. Голос: {SPEAKER}.\n")
            return model, model_id
        except Exception as exc:
            last_error = exc
            print(f"Не удалось загрузить {model_id}: {exc}")

    raise RuntimeError(f"Не удалось загрузить ни одну модель Silero: {last_error}")


def synth_one(model, text: str, out_path: Path) -> bool:
    try:
        import numpy as np

        audio = model.apply_tts(
            text=text,
            speaker=SPEAKER,
            sample_rate=SAMPLE_RATE,
            # Даже при внешнем акценторе это оставлено включённым: Silero
            # заполняет слова, которые внешний движок мог пропустить, и
            # сохраняет уже заданные вручную ударения.
            put_accent=True,
            put_yo=True,
        )

        samples = audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio.numpy()
        samples_int16 = np.clip(samples, -1.0, 1.0)
        samples_int16 = (samples_int16 * 32767).astype(np.int16)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(int(SAMPLE_RATE * DEEPEN))
            wav_file.writeframes(samples_int16.tobytes())
        return True
    except Exception as exc:
        print(f"    ОШИБКА: {exc}")
        return False


def read_entries(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Пропуск: {path.name} не найден")
        return []
    except json.JSONDecodeError as exc:
        print(f"Пропуск: ошибка JSON в {path.name}: {exc}")
        return []

    if not isinstance(payload, list):
        print(f"Пропуск: корнем {path.name} должен быть JSON-массив")
        return []
    return [entry for entry in payload if isinstance(entry, dict)]


def preview_sources(
    base_dir: Path,
    dictionary: PronunciationDictionary,
    accentor: AutoAccentor | None,
    count: int,
) -> None:
    for json_name, _ in SOURCES:
        entries = read_entries(base_dir / json_name)
        if not entries:
            continue
        print(f"\n===== {json_name} =====")
        shown = 0
        for entry in entries:
            if not entry.get("id") or not entry_voice_quote(entry):
                continue
            print(f"\n[{entry['id']}]\n{compose_entry_text(entry, dictionary, accentor)}")
            shown += 1
            if shown >= count:
                break


def process_file(
    model,
    json_path: Path,
    out_dir: Path,
    dictionary: PronunciationDictionary,
    accentor: AutoAccentor | None,
    overwrite: bool,
) -> None:
    entries = read_entries(json_path)
    if not entries:
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(entries)
    done = skipped = failed = 0
    transcript_lines: list[str] = []

    for index, entry in enumerate(entries, 1):
        entry_id = str(entry.get("id", "")).strip()
        quote = entry_voice_quote(entry)
        if not entry_id or not quote:
            continue

        text = compose_entry_text(entry, dictionary, accentor)
        transcript_lines.append(f"{entry_id}\t{text}")

        out_path = out_dir / f"{entry_id}.wav"
        if not overwrite and out_path.exists() and out_path.stat().st_size > 0:
            skipped += 1
            continue

        print(f"[{index}/{total}] {json_path.name}: {entry_id}")
        if synth_one(model, text, out_path):
            done += 1
        else:
            failed += 1

    transcript_path = out_dir / "_transcript.txt"
    transcript_path.write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")

    print(
        f"-> {json_path.name}: озвучено {done}, "
        f"пропущено {skipped}, ошибок {failed}\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Озвучка цитат Roma Aeterna через Silero")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="перезаписать уже существующие WAV после исправления ударений",
    )
    parser.add_argument(
        "--preview",
        type=int,
        metavar="N",
        help="показать по N подготовленных строк из каждого JSON без озвучки",
    )
    parser.add_argument(
        "--no-external-stress",
        action="store_true",
        help="не загружать silero-stress или StressRNN",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_ID,
        help=f"модель Silero TTS (по умолчанию {DEFAULT_MODEL_ID})",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    base_dir = Path(__file__).resolve().parent
    project_root = project_root_for(base_dir)
    audio_root = project_root / "audio"

    dictionary = load_pronunciation_dictionary(base_dir)
    print(
        f"Словарь: {len(dictionary.stress_overrides)} ручных ударений, "
        f"{len(dictionary.latin_pronunciation)} латинских замен."
    )
    accentor = load_auto_accentor(args.no_external_stress)

    if args.preview is not None:
        if args.preview < 1:
            print("--preview должен быть не меньше 1")
            return 2
        preview_sources(base_dir, dictionary, accentor, args.preview)
        return 0

    torch = import_torch()
    torch.set_num_threads(os.cpu_count() or 4)
    model, _ = load_model(args.model)

    print(f"Каталог WAV: {audio_root}")
    for json_name, category_dir in SOURCES:
        process_file(
            model,
            base_dir / json_name,
            audio_root / category_dir,
            dictionary,
            accentor,
            args.overwrite,
        )

    print("Готово.")
    if not args.overwrite:
        print("Для обновления старых WAV после изменения ударений запустите с --overwrite.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

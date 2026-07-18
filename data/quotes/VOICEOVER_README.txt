ROMA AETERNA — ФИНАЛЬНАЯ СИСТЕМА ОЗВУЧКИ

Файлы, которые должны лежать в одной папке:
  generate_voiceover_silero_professional.py
  reference_formatter.py
  stress_dictionary.json
  world_wonder_quotes.json
  great_people_quotes.json
  tech_quotes.json

Что изменено
1. Создан новый сводный словарь ударений: 2818 русских замен и 90 латинских произношений.
2. Во всех 294 записях добавлено поле tts_source. Поле source остаётся красивым текстом для интерфейса.
3. Ссылки озвучиваются единообразно: «Книга третья», «Том шестой», «Глава восьмая»,
   «Параграф второй», «Стих двадцать первый», «Надпись девятьсот шестидесятая».
4. Добавлен отдельный reference_formatter.py для античных, библейских, юридических,
   эпиграфических и поэтических ссылок.
5. Генератор умеет проверять проект и заново синхронизировать tts_source.
6. Обработка большого словаря ускорена: слова заменяются одним проходом, а не тысячами regex-вызовов.

ПРОВЕРКА ПЕРЕД ГЕНЕРАЦИЕЙ

  python generate_voiceover_silero_professional.py --check

Ожидаемый результат:
  «Проверка пройдена: ошибок 0».

ПРОСМОТР БЕЗ СОЗДАНИЯ WAV

  python generate_voiceover_silero_professional.py --preview 3 --no-external-stress

ОБНОВЛЕНИЕ tts_source ПОСЛЕ РЕДАКТИРОВАНИЯ source

  python generate_voiceover_silero_professional.py --sync-tts-sources
  python generate_voiceover_silero_professional.py --check

УДАЛЕНИЕ СТАРОЙ ОЗВУЧКИ

Если скрипт лежит в game/data/quotes:

  rm -f ../../audio/world_wonders/*.wav
  rm -f ../../audio/great_people/*.wav
  rm -f ../../audio/tech/*.wav

Если скрипт лежит в корне проекта:

  rm -f audio/world_wonders/*.wav
  rm -f audio/great_people/*.wav
  rm -f audio/tech/*.wav

СОЗДАНИЕ НОВЫХ WAV

  python generate_voiceover_silero_professional.py --overwrite

ПРОВЕРКА КОЛИЧЕСТВА WAV

Если скрипт лежит в game/data/quotes:

  find ../../audio -name '*.wav' | wc -l

Должно получиться 294 файла WAV.

ЗАВИСИМОСТИ TERMUX

  pip install torch omegaconf numpy --break-system-packages

Внешний акцентор необязателен. Новый словарь полностью покрывает многоcложные слова
в подготовленных источниках; Silero дополнительно использует put_accent=True и put_yo=True.

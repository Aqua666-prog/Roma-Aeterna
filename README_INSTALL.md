# Установка v2.70.0

Положите рядом следующие файлы:

- `roma_aeterna.py`
- `roma_economy.py`
- `roma_resources.py`

Существующие `roma_annals.py` и `roma_barbarians.py` оставьте в той же папке.

Проверка и запуск:

```bash
python roma_aeterna.py --self-test
python roma_aeterna.py --update-integrity
python roma_aeterna.py
```

Тесты ресурсного модуля:

```bash
PYTHONPATH=. python -m unittest tests/test_roma_resources.py -v
```

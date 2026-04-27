VENV_PYTHON := ./venv/Scripts/python.exe
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python)
HOST ?= 127.0.0.1
PORT ?= 8008

.PHONY: install run dev poll info read-purifier read-humidifier discover-purifier discover-humidifier check

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) -m uvicorn src.app:app --host $(HOST) --port $(PORT)

dev:
	$(PYTHON) -m uvicorn src.app:app --host $(HOST) --port $(PORT) --reload

poll:
	$(PYTHON) -c "from src.db import init_db; from src.collector import collect_once; init_db(); collect_once()"

info:
	$(PYTHON) scripts/miot.py info

read-purifier:
	$(PYTHON) scripts/miot.py read purifier

read-humidifier:
	$(PYTHON) scripts/miot.py read humidifier

discover-purifier:
	$(PYTHON) scripts/miot.py discover purifier

discover-humidifier:
	$(PYTHON) scripts/miot.py discover humidifier

check:
	$(PYTHON) -m compileall src scripts

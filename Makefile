PYTHON ?= .venv/bin/python

.PHONY: bootstrap verify verify-private test preview emulator
bootstrap:
	$(PYTHON) scripts/bootstrap_keyboard.py
	$(PYTHON) scripts/bootstrap_emulator.py

verify:
	$(PYTHON) scripts/reproduce.py --source-only

emulator:
	$(PYTHON) scripts/serve_emulator.py

verify-private:
	$(PYTHON) scripts/reproduce.py

test:
	$(PYTHON) scripts/test_portable.py

preview:
	$(PYTHON) scripts/build_native.py
	$(PYTHON) scripts/build_preview.py
	$(PYTHON) scripts/serve_native.py --bind 127.0.0.1 --port 8787

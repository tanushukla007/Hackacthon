# ABHEDYA-CHAKRA — local-first build and run
.PHONY: help install sample ingest api web demo dev check test routes diagnose theme bench docs zip clean clean-big standin profile

PY ?= python3

help:
	@echo "make install   install backend + frontend dependencies (pinned)"
	@echo "make sample    generate the synthetic development CSV (not the real dataset)"
	@echo "make api       run the FastAPI backend on :8000"
	@echo "make web       run the Vite frontend on :5173 (proxies /api to :8000)"
	@echo "make demo      run the demo UI on :5174 (proxies /api to :8000)"
	@echo "make check     contract + doc parity + reconciliation + metric correctness"
	@echo "make diagnose  show why the risk distribution looks the way it does"
	@echo "make test      run the UI tests (hover facts, SSR render, jsdom DOM)"
	@echo "make routes    regenerate the route index inside docs/BACKEND_API.md"
	@echo "make theme     render both UI sheets to samples/_theme_{dark,light}.png"
	@echo "make bench     measure ingest/trace performance on THIS machine"
	@echo "make docs      rebuild every PDF and DOCX"
	@echo "make zip       build the submission archive abhedya-chakra.zip"

install:
	$(PY) -m pip install -r backend/requirements.txt
	cd frontend && npm ci || npm install

sample:
	$(PY) tools/make_sample_dataset.py 250000

api:
	cd backend && $(PY) -m uvicorn app.main:app --host 0.0.0.0 --port 8000

web:
	cd frontend && npm run dev

demo:
	cd frontend-demo && npm run dev

check:
	$(PY) tools/contract_check.py
	$(PY) tools/test_reconcile.py
	$(PY) tools/test_evaluate.py

test:
	cd frontend && bash run_tests.sh
	cd frontend-demo && bash run_tests.sh

routes:
	$(PY) tools/route_index.py --write

diagnose:
	$(PY) tools/diagnose_risk.py

theme:
	$(PY) tools/theme_preview.py samples/_theme

bench:
	$(PY) tools/bench.py --traces 25

profile:
	$(PY) tools/profile_dataset.py $(CSV) --check

docs:
	$(PY) tools/build_docs.py

zip:
	$(PY) tools/make_zip.py

clean:
	rm -rf data/artifacts/facts.parquet frontend/dist

# Everything regenerable and bulky. The 2M stand-in is ~257 MB and rebuilds in
# about 20 s; facts.parquet rebuilds on the next ingest. Stop the API first --
# deleting facts.parquet under a READY server pulls the data out from under it.
clean-big:
	rm -rf out/STANDIN_2M.csv data/_features_baseline.npz data/_slice_*.csv \
	       data/artifacts/facts.parquet
	@echo "regenerate with: python3 tools/make_2m_standin.py  (~20 s)"

standin:
	python3 tools/make_2m_standin.py

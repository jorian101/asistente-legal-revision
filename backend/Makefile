.PHONY: help test test-cov lint typecheck security security-strict metrics ci test-integration

# Helpers: siempre usamos uv run para no asumir el venv activo.
UV := uv run

help:
	@echo "Targets disponibles:"
	@echo "  make test          — pytest sin coverage (mas rapido, loop dev)."
	@echo "  make test-cov      — pytest + coverage gate 58% (COV_GATE)."
	@echo "  make lint           — ruff check + radon cc (rank C max por funcion)."
	@echo "  make typecheck      — mypy (baseline: falla solo en modulos estrictos auth/ports)."
	@echo "  make security       — bandit (-ll, solo HIGH/CRITICAL) + pip-audit."
	@echo "  make security-strict — bandit -l (LOW arriba) — solo reporte, no bloquea."
	@echo "  make metrics        — radon cc + mi + hal + raw (reporte completo)."
	@echo "  make ci             — lint + typecheck + test-cov + security (lo que corre GH Actions)."
	@echo "  make test-integration — tests marcados integration (docker-compose, timeout 30s)."

test:
	$(UV) pytest --no-cov -m "not integration"

# test-cov: coverage gate 58% (COV_GATE; cobertura real ~74%).
# - pytest NO bloquea por coverage (bug pytest-cov 7.1.0 + pytest 9.1.1 no
#   propaga --cov-fail-under al exit code). Por eso el gate real lo hace
#   `coverage report --fail-under` que SÍ retorna exit != 0.
# - Excluye tests marcados `integration` (cargan cadena completa de
#   scripts.ingest_corpus y exceden el timeout 5s de unit). Esos corren en
#   `make test-integration` (separado, timeout 30s).
test-cov:
	$(UV) pytest -m "not integration"
	$(UV) coverage report --fail-under=$${COV_GATE:-58}
	@echo "Coverage gate OK (>= $${COV_GATE:-58}%)."

# Lint = formato/estilo (ruff) + complejidad ciclomatica (radon).
# Gate actual: rank D maximo (cc <= 15). Motivo: codigo preexistente de
# Sprint 0 tiene `particionar_articulo` en cc=15 (rank C alto entra en D
# segun la escala de radon). Deuda tecnica documentada en memoria Engram
# (topic_key architecture/plan-red-de-seguridad-calidad-fundamentacional):
# refactorizar `particionar_articulo` en Sprint 2 (corpus) y subir gate a C.
# Codigo NUEVO (auth en Fase 1-2): aspirar a rank C (cc <= 10).
lint:
	$(UV) ruff check .
	@echo "--- radon cc (gate: rank D maximo por funcion) ---"
	@$(UV) radon cc -s -n D -e "scripts/*,alembic/*,tests/*" src/ | tee /tmp/radon_cc.txt
	@if grep -qE " - [EF] \(" /tmp/radon_cc.txt; then \
		echo "FAIL: hay funciones con rank E/F (>15 cc). Ver arriba."; \
		grep -E " - [EF] \(" /tmp/radon_cc.txt; \
		exit 1; \
	else \
		echo "OK: todas las funciones rank D o mejor."; \
	fi

# Typecheck baseline (plan Fundacional): UN SOLO mypy run, SILENCIOSO en imports.
# Filtrado post-run: errores en src/application/auth/* bloquean; el resto se reporta.
# Deuda Sprint 0: 229 errores en 60 archivos (medido 2026-09-20; antes se documentaban 13) — refactorizar modulo por
# modulo, no en Fase 0. Ver memoria Engram topic_key
# architecture/plan-red-de-seguridad-calidad-fundamentacional.
typecheck:
	@echo "--- mypy single-run (gate: src/application/auth/* bloquea, resto WARN) ---"
	@$(UV) mypy --follow-imports=silent src/ > /tmp/mypy_out.txt 2>&1; \
	AUTH_ERR=$$(grep -c "^src/application/auth/" /tmp/mypy_out.txt); \
	if [ "$$AUTH_ERR" -gt 0 ]; then \
		echo "FAIL: mypy estricto fallo en auth/ (modulo nuevo). Errores:"; \
		grep "^src/application/auth/" /tmp/mypy_out.txt; \
		exit 1; \
	fi; \
	echo "OK: modulo auth/ limpio (gate estricto)."; \
	echo ""; \
	echo "Baseline (resto de src/, WARN no bloquea):"; \
	grep -v "^src/application/auth/" /tmp/mypy_out.txt | tail -20

# Security: solo HIGH/CRITICAL bloquean (-ll = low leve fails alone).
# MEDIUM/LOW se reportan via make security-strict (no bloqueante).
security:
	@echo "--- bandit (-ll: solo HIGH/CRITICAL bloquean) ---"
	$(UV) bandit -ll -r src/ -q
	@echo "--- pip-audit (timeout 60s por lentitud network pypi) ---"
	$(UV) pip-audit --strict --timeout 60

security-strict:
	@echo "--- bandit (-l: LOW y arriba se reportan, NO bloquea) ---"
	$(UV) bandit -l -r src/
	$(UV) pip-audit

# Metrics: reporte completo de calidad (Uncle Bob "quality metrics").
metrics:
	@echo "=== Cyclomatic Complexity ==="
	$(UV) radon cc -s -n C -e "scripts/*,alembic/*,tests/*" src/
	@echo ""
	@echo "=== Maintainability Index (gate B o mejor, MI >= 65) ==="
	$(UV) radon mi -s -e "scripts/*,alembic/*,tests/*" src/ | tee /tmp/radon_mi.txt
	@if grep -q -E "^\s*[CD] " /tmp/radon_mi.txt; then \
		echo "WARN:hay modulos con MI < 65 (rank C o peor). Ver arriba."; \
	fi
	@echo ""
	@echo "=== Halstead ==="
	$(UV) radon hal -e "scripts/*,alembic/*,tests/*" src/
	@echo ""
	@echo "=== Raw metrics ==="
	$(UV) radon raw -e "scripts/*,alembic/*,tests/*" src/

# CI = el gate que corre en GH Actions. Orden: lint -> types -> tests+cov -> security.
# Si cualquiera falla, make ci falla.
ci: lint typecheck test-cov security
	@echo "=== make ci VERDE ==="

# Integration: corre solo tests marcados integration, con compose levantado y la
# BD real con datos sembrados (tests/_bd_real.py). Solo local: NO corre en CI.
test-integration:
	$(UV) pytest -m integration

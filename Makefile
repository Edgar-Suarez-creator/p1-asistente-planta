PY ?= python
CORE ?= ../planta-core

.PHONY: setup eval demo test cypher neo4j

setup:            ## instala planta-core y este paquete, y genera los datos sintéticos (semilla 14224)
	$(PY) -m pip install -e $(CORE) -e ".[dev]"
	cd $(CORE) && $(PY) -m planta_core.generar

eval:             ## reproduce evaluacion/RESULTS.md
	$(PY) -m evaluacion.run

demo:             ## demo local sin credenciales en http://127.0.0.1:8001
	$(PY) -m app.servidor --exportar
	$(PY) -m app.servidor

test:
	$(PY) -m pytest -q

cypher:           ## exporta el grafo a neo4j/planta.cypher
	$(PY) tareas.py cypher

neo4j: cypher     ## levanta Neo4j 5 y carga el grafo (requiere Docker)
	docker compose up -d neo4j
	docker compose exec -T neo4j cypher-shell -u neo4j -p planta-demo < neo4j/planta.cypher

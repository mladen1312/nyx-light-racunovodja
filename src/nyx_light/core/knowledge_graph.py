"""
Nyx Light — Knowledge Graph

Graf znanja za relacije između entiteta:
  - Klijent → ima → Dobavljač
  - Dobavljač → izdaje → Račun
  - Račun → kontira_se_na → Konto
  - Konto → pripada → Razred
  - Zaposlenik → korigirao → Knjiženje (L2 memorija)
  - Zakon → sadrži → Članak
  - Članak → regulira → Poslovni_događaj

Dva moda:
  1. Neo4j (produkcija) — pravi graph DB
  2. SQLite (fallback) — relacijska tablica kao lightweight graph
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.knowledge_graph")

DB_PATH = Path("data/memory_db/knowledge_graph.db")


class KnowledgeGraph:
    """
    Knowledge Graph s Neo4j ili SQLite backendom.

    Čuva relacije:
      (source) -[relation]-> (target)
    sa metadata i vremenskim atributima.
    """

    def __init__(self, neo4j_uri: str = "", neo4j_user: str = "", neo4j_pass: str = ""):
        self._neo4j = None
        self._db: Optional[sqlite3.Connection] = None
        self._mode = "none"

        # Try Neo4j first
        if neo4j_uri:
            try:
                from neo4j import GraphDatabase
                self._neo4j = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
                self._neo4j.verify_connectivity()
                self._mode = "neo4j"
                logger.info("Knowledge Graph: Neo4j connected (%s)", neo4j_uri)
                return
            except Exception as e:
                logger.warning("Neo4j nedostupan: %s — koristim SQLite", e)
                self._neo4j = None

        # Fallback to SQLite
        self._init_sqlite()
        self._mode = "sqlite"
        logger.info("Knowledge Graph: SQLite mode (%s)", DB_PATH)

    def _init_sqlite(self):
        """Kreiraj SQLite tablice za graph."""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")

        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                properties TEXT DEFAULT '{}',
                weight REAL DEFAULT 1.0,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (source_id) REFERENCES nodes(id),
                FOREIGN KEY (target_id) REFERENCES nodes(id)
            );

            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
            CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
        """)
        self._db.commit()

    # ───────────────────────── Node Operations ─────────────────────────

    def add_node(self, node_id: str, label: str, properties: Optional[Dict] = None) -> bool:
        """Dodaj ili ažuriraj čvor."""
        props = json.dumps(properties or {}, ensure_ascii=False)

        if self._mode == "neo4j":
            return self._neo4j_add_node(node_id, label, props)

        try:
            self._db.execute(
                """INSERT INTO nodes (id, label, properties) VALUES (?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   properties=excluded.properties, updated_at=datetime('now')""",
                (node_id, label, props),
            )
            self._db.commit()
            return True
        except Exception as e:
            logger.error("add_node error: %s", e)
            return False

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Dohvati čvor po ID-u."""
        if self._mode == "neo4j":
            return self._neo4j_get_node(node_id)

        row = self._db.execute(
            "SELECT id, label, properties, created_at FROM nodes WHERE id=?",
            (node_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "label": row[1],
            "properties": json.loads(row[2]), "created_at": row[3],
        }

    def find_nodes(self, label: Optional[str] = None, **props) -> List[Dict[str, Any]]:
        """Nađi čvorove po labelu i/ili propertijima."""
        query = "SELECT id, label, properties FROM nodes WHERE 1=1"
        params = []
        if label:
            query += " AND label=?"
            params.append(label)

        rows = self._db.execute(query, params).fetchall()
        results = []
        for r in rows:
            node_props = json.loads(r[2])
            # Filter by additional properties
            match = all(node_props.get(k) == v for k, v in props.items())
            if match or not props:
                results.append({"id": r[0], "label": r[1], "properties": node_props})
        return results

    # ───────────────────────── Edge Operations ─────────────────────────

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        properties: Optional[Dict] = None,
        weight: float = 1.0,
    ) -> bool:
        """Dodaj relaciju između čvorova."""
        props = json.dumps(properties or {}, ensure_ascii=False)

        if self._mode == "neo4j":
            return self._neo4j_add_edge(source_id, target_id, relation, props, weight)

        try:
            # Ensure nodes exist
            for nid in (source_id, target_id):
                self._db.execute(
                    "INSERT OR IGNORE INTO nodes (id, label) VALUES (?, ?)",
                    (nid, "unknown"),
                )

            self._db.execute(
                "INSERT INTO edges (source_id, target_id, relation, properties, weight) VALUES (?, ?, ?, ?, ?)",
                (source_id, target_id, relation, props, weight),
            )
            self._db.commit()
            return True
        except Exception as e:
            logger.error("add_edge error: %s", e)
            return False

    def get_neighbors(
        self,
        node_id: str,
        relation: Optional[str] = None,
        direction: str = "out",
    ) -> List[Dict[str, Any]]:
        """Dohvati susjede čvora."""
        if direction == "out":
            query = "SELECT e.relation, e.weight, e.properties, n.id, n.label, n.properties FROM edges e JOIN nodes n ON e.target_id=n.id WHERE e.source_id=?"
        elif direction == "in":
            query = "SELECT e.relation, e.weight, e.properties, n.id, n.label, n.properties FROM edges e JOIN nodes n ON e.source_id=n.id WHERE e.target_id=?"
        else:  # both
            query = """
                SELECT e.relation, e.weight, e.properties, n.id, n.label, n.properties
                FROM edges e JOIN nodes n ON (e.target_id=n.id AND e.source_id=?)
                UNION ALL
                SELECT e.relation, e.weight, e.properties, n.id, n.label, n.properties
                FROM edges e JOIN nodes n ON (e.source_id=n.id AND e.target_id=?)
            """

        params = [node_id] if direction != "both" else [node_id, node_id]
        if relation:
            query += " AND e.relation=?"
            params.append(relation)

        rows = self._db.execute(query, params).fetchall()
        return [{
            "relation": r[0], "weight": r[1],
            "edge_properties": json.loads(r[2]),
            "node_id": r[3], "node_label": r[4],
            "node_properties": json.loads(r[5]),
        } for r in rows]

    def get_path(self, from_id: str, to_id: str, max_depth: int = 4) -> List[List[str]]:
        """Nađi put između dva čvora (BFS)."""
        visited = set()
        queue = [(from_id, [from_id])]
        paths = []

        while queue:
            current, path = queue.pop(0)
            if current == to_id:
                paths.append(path)
                continue
            if len(path) >= max_depth:
                continue
            if current in visited:
                continue
            visited.add(current)

            neighbors = self.get_neighbors(current, direction="out")
            for n in neighbors:
                if n["node_id"] not in visited:
                    queue.append((n["node_id"], path + [n["relation"], n["node_id"]]))

        return paths

    # ───────────────────────── Accounting-Specific ─────────────────────

    def record_kontiranje_pattern(
        self,
        client_id: str,
        dobavljac_oib: str,
        opis: str,
        konto_duguje: str,
        konto_potrazuje: str,
    ):
        """Zapiši uzorak kontiranja u graf (za L2 memoriju)."""
        # Create nodes
        self.add_node(f"client:{client_id}", "Klijent", {"client_id": client_id})
        self.add_node(f"dobavljac:{dobavljac_oib}", "Dobavljac", {"oib": dobavljac_oib})
        self.add_node(f"konto:{konto_duguje}", "Konto", {"broj": konto_duguje})
        self.add_node(f"konto:{konto_potrazuje}", "Konto", {"broj": konto_potrazuje})

        # Create edges
        pattern_id = f"pattern:{client_id}:{dobavljac_oib}:{konto_duguje}"
        self.add_node(pattern_id, "KontiranjePatter", {
            "opis": opis, "konto_duguje": konto_duguje,
            "konto_potrazuje": konto_potrazuje,
            "timestamp": datetime.now().isoformat(),
        })

        self.add_edge(f"client:{client_id}", pattern_id, "koristi_pattern")
        self.add_edge(pattern_id, f"konto:{konto_duguje}", "duguje_na")
        self.add_edge(pattern_id, f"konto:{konto_potrazuje}", "potrazuje_na")
        self.add_edge(f"dobavljac:{dobavljac_oib}", pattern_id, "kontira_se_kao")

    def suggest_konto(self, client_id: str, dobavljac_oib: str) -> List[Dict[str, Any]]:
        """Predloži konto na temelju prethodnih uzoraka."""
        neighbors = self.get_neighbors(f"dobavljac:{dobavljac_oib}", direction="out")
        patterns = [n for n in neighbors if n["relation"] == "kontira_se_kao"]

        suggestions = []
        for p in patterns:
            props = p.get("node_properties", {})
            suggestions.append({
                "konto_duguje": props.get("konto_duguje", ""),
                "konto_potrazuje": props.get("konto_potrazuje", ""),
                "opis": props.get("opis", ""),
                "confidence": min(1.0, p.get("weight", 1.0)),
            })

        return sorted(suggestions, key=lambda x: x["confidence"], reverse=True)

    # ───────────────────────── Neo4j Methods ──────────────────────────

    def _neo4j_add_node(self, node_id: str, label: str, props: str) -> bool:
        try:
            with self._neo4j.session() as session:
                session.run(
                    f"MERGE (n:{label} {{id: $id}}) SET n.properties = $props, n.updated_at = datetime()",
                    id=node_id, props=props,
                )
            return True
        except Exception as e:
            logger.error("Neo4j add_node: %s", e)
            return False

    def _neo4j_get_node(self, node_id: str) -> Optional[Dict]:
        try:
            with self._neo4j.session() as session:
                result = session.run("MATCH (n {id: $id}) RETURN n", id=node_id)
                record = result.single()
                if record:
                    node = record["n"]
                    return {"id": node_id, "label": list(node.labels)[0], "properties": dict(node)}
        except Exception as e:
            logger.error("Neo4j get_node: %s", e)
        return None

    def _neo4j_add_edge(self, src: str, tgt: str, rel: str, props: str, weight: float) -> bool:
        try:
            with self._neo4j.session() as session:
                session.run(
                    f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
                    f"MERGE (a)-[r:{rel}]->(b) "
                    f"SET r.properties = $props, r.weight = $weight",
                    src=src, tgt=tgt, props=props, weight=weight,
                )
            return True
        except Exception as e:
            logger.error("Neo4j add_edge: %s", e)
            return False

    # ───────────────────────── Stats ──────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        if self._mode == "sqlite" and self._db:
            nodes = self._db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = self._db.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            labels = self._db.execute("SELECT DISTINCT label FROM nodes").fetchall()
            relations = self._db.execute("SELECT DISTINCT relation FROM edges").fetchall()
            return {
                "mode": "sqlite",
                "nodes": nodes,
                "edges": edges,
                "labels": [r[0] for r in labels],
                "relations": [r[0] for r in relations],
            }
        return {"mode": self._mode, "status": "connected" if self._neo4j else "disconnected"}

    def close(self):
        if self._neo4j:
            self._neo4j.close()
        if self._db:
            self._db.close()

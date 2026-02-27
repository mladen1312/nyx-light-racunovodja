"""
Nyx Light — Knowledge Graph (Neo4j + In-Memory Fallback)

Grafovska baza znanja za međusobno povezane računovodstvene koncepte:
  - Klijent → koristi → ERP sustav
  - Klijent → ima → Konto pravilo
  - Zakon → definira → Stopa
  - Konto → pripada → Razred
  - Dobavljač → fakturira → Klijent

Dva moda:
  1. Neo4j (produkcija): Bolt driver na localhost:7687
  2. In-Memory Graph (fallback): Dict-based za testiranje i razvoj

Optimizirano za Apple Silicon — ~0.1ms query na in-memory grafu.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nyx_light.kg")


class KnowledgeGraph:
    """
    Knowledge Graph s Neo4j i in-memory fallbackom.

    In-memory struktura:
      nodes: {node_id: {type, properties}}
      edges: {edge_id: {from, to, type, properties}}
      index: {type: set(node_ids)}  -- za brzi lookup po tipu
    """

    def __init__(self, neo4j_uri: str = "", neo4j_user: str = "", neo4j_pass: str = ""):
        self._neo4j_uri = neo4j_uri
        self._neo4j_driver = None
        self._use_neo4j = False

        # In-memory graph
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[str, Dict[str, Any]] = {}
        self._adjacency: Dict[str, Set[str]] = defaultdict(set)  # node_id → set(edge_ids)
        self._type_index: Dict[str, Set[str]] = defaultdict(set)  # type → set(node_ids)

        self._stats = {"nodes": 0, "edges": 0, "queries": 0}

        # Try Neo4j
        if neo4j_uri:
            self._init_neo4j(neo4j_uri, neo4j_user, neo4j_pass)

        if not self._use_neo4j:
            logger.info("KnowledgeGraph: in-memory mode")

    def _init_neo4j(self, uri: str, user: str, password: str):
        try:
            from neo4j import GraphDatabase
            self._neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
            self._neo4j_driver.verify_connectivity()
            self._use_neo4j = True
            logger.info("KnowledgeGraph: Neo4j connected at %s", uri)
        except ImportError:
            logger.info("neo4j driver nije instaliran — koristim in-memory graf")
        except Exception as e:
            logger.warning("Neo4j nedostupan (%s) — fallback na in-memory", e)

    # ──────────────────────────────────────────────
    # CRUD operacije
    # ──────────────────────────────────────────────

    def add_node(self, node_id: str, node_type: str, properties: Optional[Dict] = None) -> str:
        """Dodaj čvor u graf."""
        props = properties or {}
        props["_type"] = node_type
        props["_created"] = datetime.now().isoformat()

        if self._use_neo4j:
            self._neo4j_add_node(node_id, node_type, props)
        else:
            self._nodes[node_id] = {"type": node_type, "properties": props}
            self._type_index[node_type].add(node_id)

        self._stats["nodes"] = len(self._nodes)
        return node_id

    def add_edge(self, from_id: str, to_id: str, edge_type: str,
                 properties: Optional[Dict] = None) -> str:
        """Dodaj vezu između čvorova."""
        edge_id = f"{from_id}--{edge_type}-->{to_id}"
        props = properties or {}
        props["_type"] = edge_type
        props["_created"] = datetime.now().isoformat()

        if self._use_neo4j:
            self._neo4j_add_edge(from_id, to_id, edge_type, props)
        else:
            self._edges[edge_id] = {
                "from": from_id, "to": to_id, "type": edge_type, "properties": props,
            }
            self._adjacency[from_id].add(edge_id)
            self._adjacency[to_id].add(edge_id)

        self._stats["edges"] = len(self._edges)
        return edge_id

    def get_node(self, node_id: str) -> Optional[Dict]:
        if self._use_neo4j:
            return self._neo4j_get_node(node_id)
        return self._nodes.get(node_id)

    def get_neighbors(self, node_id: str, edge_type: Optional[str] = None
                      ) -> List[Dict[str, Any]]:
        """Dohvati susjede čvora (opcionalno filtrirano po tipu veze)."""
        self._stats["queries"] += 1

        if self._use_neo4j:
            return self._neo4j_neighbors(node_id, edge_type)

        results = []
        for edge_id in self._adjacency.get(node_id, set()):
            edge = self._edges[edge_id]
            if edge_type and edge["type"] != edge_type:
                continue
            # Get the other end
            other_id = edge["to"] if edge["from"] == node_id else edge["from"]
            other_node = self._nodes.get(other_id, {})
            results.append({
                "node_id": other_id,
                "node_type": other_node.get("type", ""),
                "edge_type": edge["type"],
                "node_properties": other_node.get("properties", {}),
                "edge_properties": edge.get("properties", {}),
            })
        return results

    def query_by_type(self, node_type: str) -> List[Dict[str, Any]]:
        """Dohvati sve čvorove određenog tipa."""
        self._stats["queries"] += 1

        if self._use_neo4j:
            return self._neo4j_query_type(node_type)

        return [
            {"node_id": nid, **self._nodes[nid]}
            for nid in self._type_index.get(node_type, set())
        ]

    def find_path(self, from_id: str, to_id: str, max_depth: int = 5
                  ) -> Optional[List[str]]:
        """BFS shortest path između dva čvora."""
        self._stats["queries"] += 1

        if from_id == to_id:
            return [from_id]

        visited = {from_id}
        queue = [(from_id, [from_id])]

        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue

            for edge_id in self._adjacency.get(current, set()):
                edge = self._edges[edge_id]
                neighbor = edge["to"] if edge["from"] == current else edge["from"]

                if neighbor == to_id:
                    return path + [neighbor]

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    # ──────────────────────────────────────────────
    # Računovodstvene helper metode
    # ──────────────────────────────────────────────

    def add_client(self, oib: str, name: str, erp: str = "CPP", **kwargs) -> str:
        return self.add_node(f"client:{oib}", "Client", {
            "oib": oib, "name": name, "erp": erp, **kwargs,
        })

    def add_konto_rule(self, client_oib: str, dobavljac: str,
                       konto: str, opis: str) -> str:
        """Dodaj pravilo kontiranja za klijenta."""
        rule_id = f"rule:{client_oib}:{dobavljac}:{konto}"
        self.add_node(rule_id, "KontoRule", {
            "dobavljac": dobavljac, "konto": konto, "opis": opis,
        })
        self.add_edge(f"client:{client_oib}", rule_id, "HAS_RULE")
        return rule_id

    def get_konto_rules(self, client_oib: str) -> List[Dict]:
        """Dohvati sva pravila kontiranja za klijenta."""
        return self.get_neighbors(f"client:{client_oib}", "HAS_RULE")

    def add_law_reference(self, law_name: str, article: str,
                          stopa: str, opis: str) -> str:
        law_id = f"law:{law_name}"
        if law_id not in self._nodes:
            self.add_node(law_id, "Law", {"name": law_name})

        article_id = f"law:{law_name}:cl{article}"
        self.add_node(article_id, "Article", {
            "article": article, "stopa": stopa, "opis": opis,
        })
        self.add_edge(law_id, article_id, "DEFINES")
        return article_id

    # ──────────────────────────────────────────────
    # Seed default knowledge
    # ──────────────────────────────────────────────

    def seed_defaults(self):
        """Popuni graf osnovnim računovodstvenim znanjem."""
        # Kontni razredi
        razredi = {
            "0": "Dugotrajna imovina",
            "1": "Kratkotrajna imovina",
            "2": "Kratkoročne obveze",
            "3": "Zalihe i dugoročne obveze",
            "4": "Troškovi",
            "5": "Troškovi po vrstama (produkcija)",
            "6": "Prihodi",
            "7": "Rashodi",
            "8": "Rezultat poslovanja",
            "9": "Izvanbilančni zapisi",
        }
        for razred, opis in razredi.items():
            self.add_node(f"razred:{razred}", "KontniRazred", {
                "razred": razred, "opis": opis,
            })

        # PDV stope
        for stopa, opis in [("25", "Standardna"), ("13", "Snižena"), ("5", "Najniža")]:
            self.add_node(f"pdv:{stopa}", "PDVStopa", {"stopa": stopa, "opis": opis})
            self.add_edge("law:ZakonPDV", f"pdv:{stopa}", "PROPISUJE")

        # Zakoni
        for law in ["ZakonPDV", "ZakonDobit", "ZakonDohodak", "ZakonRacunovodstvo"]:
            if f"law:{law}" not in self._nodes:
                self.add_node(f"law:{law}", "Law", {"name": law})

        logger.info("Knowledge graph seeded: %d nodes, %d edges",
                    len(self._nodes), len(self._edges))

    # ──────────────────────────────────────────────
    # Neo4j backend
    # ──────────────────────────────────────────────

    def _neo4j_add_node(self, node_id: str, node_type: str, props: Dict):
        with self._neo4j_driver.session() as s:
            s.run(
                f"MERGE (n:{node_type} {{id: $id}}) SET n += $props",
                id=node_id, props=props,
            )

    def _neo4j_add_edge(self, from_id, to_id, edge_type, props):
        with self._neo4j_driver.session() as s:
            s.run(
                f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
                f"MERGE (a)-[r:{edge_type}]->(b) SET r += $props",
                from_id=from_id, to_id=to_id, props=props,
            )

    def _neo4j_get_node(self, node_id: str) -> Optional[Dict]:
        with self._neo4j_driver.session() as s:
            result = s.run("MATCH (n {id: $id}) RETURN n", id=node_id)
            record = result.single()
            if record:
                return dict(record["n"])
        return None

    def _neo4j_neighbors(self, node_id: str, edge_type: Optional[str]) -> List[Dict]:
        with self._neo4j_driver.session() as s:
            q = "MATCH (a {id: $id})-[r]-(b) "
            if edge_type:
                q = f"MATCH (a {{id: $id}})-[r:{edge_type}]-(b) "
            q += "RETURN b, type(r) as rel_type, properties(r) as rel_props"
            result = s.run(q, id=node_id)
            return [
                {"node_id": dict(r["b"]).get("id", ""),
                 "edge_type": r["rel_type"],
                 "node_properties": dict(r["b"]),
                 "edge_properties": r["rel_props"]}
                for r in result
            ]

    def _neo4j_query_type(self, node_type: str) -> List[Dict]:
        with self._neo4j_driver.session() as s:
            result = s.run(f"MATCH (n:{node_type}) RETURN n")
            return [{"node_id": dict(r["n"]).get("id", ""), **dict(r["n"])} for r in result]

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "backend": "neo4j" if self._use_neo4j else "in-memory",
            "nodes": len(self._nodes),
            "edges": len(self._edges),
        }

    def close(self):
        if self._neo4j_driver:
            self._neo4j_driver.close()

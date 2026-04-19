from __future__ import annotations

from dataclasses import field
from decimal import Decimal

import networkx as nx
from pydantic import ConfigDict, model_validator
from pydantic.dataclasses import dataclass

from payment_router.core import fx
from payment_router.core.graph import NetworkEdge, PaymentGraph
from payment_router.core.models import Hop, Route


@dataclass(config=ConfigDict(frozen=True))
class RoutingPreference:
    cost_weight: float = 0.5
    time_weight: float = 0.5
    max_hops: int = 5
    _normalized_weights: tuple[float, float] = field(init=False, repr=False)

    @model_validator(mode="after")
    def validate_weights(self) -> RoutingPreference:
        total = self.cost_weight + self.time_weight
        if total <= 0:
            raise ValueError("cost_weight and time_weight cannot both be zero")
        object.__setattr__(
            self,
            "_normalized_weights",
            (self.cost_weight / total, self.time_weight / total),
        )
        return self

    @property
    def alpha(self) -> float:
        return self._normalized_weights[0]

    @property
    def beta(self) -> float:
        return self._normalized_weights[1]


Route.model_rebuild(_types_namespace={"RoutingPreference": RoutingPreference})


class PaymentRouter:
    def __init__(self, graph: PaymentGraph) -> None:
        self._graph = graph

    def find_route(
        self,
        from_currency: str,
        to_currency: str,
        amount: Decimal,
        preference: RoutingPreference,
    ) -> Route | None:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if amount <= 0:
            return None
        if source_currency == target_currency:
            return self._zero_hop_route(source_currency, amount, preference)
        if source_currency not in self._graph.graph or target_currency not in self._graph.graph:
            return None
        if not nx.has_path(self._graph.graph, source_currency, target_currency):
            return None

        score_context = self._build_score_context(preference)

        try:
            node_path = nx.shortest_path(
                self._graph.graph,
                source=source_currency,
                target=target_currency,
                weight=self._weight_function(score_context),
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        if len(node_path) - 1 > preference.max_hops:
            node_path = self._best_path_within_hops(
                source_currency,
                target_currency,
                preference,
                score_context,
            )
            if node_path is None:
                return None

        return self._route_from_path(node_path, amount, preference, score_context)

    def find_cheapest(
        self,
        from_currency: str,
        to_currency: str,
        amount: Decimal,
    ) -> Route | None:
        return self.find_route(
            from_currency,
            to_currency,
            amount,
            RoutingPreference(cost_weight=1.0, time_weight=0.0),
        )

    def find_fastest(
        self,
        from_currency: str,
        to_currency: str,
        amount: Decimal,
    ) -> Route | None:
        return self.find_route(
            from_currency,
            to_currency,
            amount,
            RoutingPreference(cost_weight=0.0, time_weight=1.0),
        )

    def find_all_routes(
        self,
        from_currency: str,
        to_currency: str,
        amount: Decimal,
        preference: RoutingPreference,
        top_n: int = 3,
    ) -> list[Route]:
        source_currency = from_currency.strip().upper()
        target_currency = to_currency.strip().upper()

        if top_n <= 0 or amount <= 0:
            return []
        if source_currency == target_currency:
            return [self._zero_hop_route(source_currency, amount, preference)]
        if source_currency not in self._graph.graph or target_currency not in self._graph.graph:
            return []

        score_context = self._build_score_context(preference)
        projected_graph = self._build_projected_graph(score_context)

        try:
            path_generator = nx.shortest_simple_paths(
                projected_graph,
                source_currency,
                target_currency,
                weight="weight",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

        routes: list[Route] = []
        for node_path in path_generator:
            if len(node_path) - 1 > preference.max_hops:
                continue

            route = self._route_from_path(node_path, amount, preference, score_context)
            if route is not None:
                routes.append(route)
            if len(routes) == top_n:
                break

        routes.sort(key=lambda route: self._route_score(route, score_context))
        return routes

    def _build_score_context(self, preference: RoutingPreference) -> _ScoreContext:
        edges = [
            data["edge"]
            for _, _, _, data in self._graph.graph.edges(keys=True, data=True)
            if isinstance(data.get("edge"), NetworkEdge)
        ]
        max_fee = max((edge.fee_usd for edge in edges), default=Decimal("0"))
        max_time = max((Decimal(str(edge.time_hours)) for edge in edges), default=Decimal("0"))
        return _ScoreContext(
            alpha=preference.alpha,
            beta=preference.beta,
            max_fee=max_fee,
            max_time=max_time,
        )

    def _weight_function(self, score_context: _ScoreContext):
        def weight(_u: str, _v: str, edge_bundle: dict[str, dict[str, object]]) -> float | None:
            candidate_weights = [
                self._edge_weight(data.get("edge"), score_context) for data in edge_bundle.values()
            ]
            visible_weights = [weight for weight in candidate_weights if weight is not None]
            return min(visible_weights) if visible_weights else None

        return weight

    def _build_projected_graph(self, score_context: _ScoreContext) -> nx.DiGraph:
        projected_graph = nx.DiGraph()
        projected_graph.add_nodes_from(self._graph.graph.nodes)

        for from_currency, to_currency in self._graph.graph.edges():
            best_edge = self._select_best_edge(from_currency, to_currency, score_context)
            if best_edge is None:
                continue
            projected_graph.add_edge(
                from_currency,
                to_currency,
                weight=self._edge_weight(best_edge, score_context),
            )

        return projected_graph

    def _best_path_within_hops(
        self,
        from_currency: str,
        to_currency: str,
        preference: RoutingPreference,
        score_context: _ScoreContext,
    ) -> list[str] | None:
        projected_graph = self._build_projected_graph(score_context)
        candidate_paths = nx.all_simple_paths(
            projected_graph,
            source=from_currency,
            target=to_currency,
            cutoff=preference.max_hops,
        )
        best_path: list[str] | None = None
        best_score: float | None = None
        for node_path in candidate_paths:
            score = self._path_score(node_path, score_context)
            if best_score is None or score < best_score:
                best_path = node_path
                best_score = score
        return best_path

    def _route_from_path(
        self,
        node_path: list[str],
        amount: Decimal,
        preference: RoutingPreference,
        score_context: _ScoreContext,
    ) -> Route | None:
        edges: list[NetworkEdge] = []
        for from_currency, to_currency in zip(node_path, node_path[1:]):
            edge = self._select_best_edge(from_currency, to_currency, score_context)
            if edge is None:
                return None
            edges.append(edge)

        hops = [
            Hop(
                from_node=edge.from_currency,
                to_node=edge.to_currency,
                network_name=edge.network_name,
                fee_usd=edge.fee_usd,
                time_hours=Decimal(str(edge.time_hours)),
                currency_in=edge.from_currency,
                currency_out=edge.to_currency,
                fx_rate=edge.fx_rate,
                data_source=edge.data_source,
            )
            for edge in edges
        ]
        total_fee_usd = sum((edge.fee_usd for edge in edges), start=Decimal("0"))
        total_time_hours = sum(
            (Decimal(str(edge.time_hours)) for edge in edges),
            start=Decimal("0"),
        )
        gross_target_amount = amount
        for edge in edges:
            gross_target_amount *= edge.fx_rate

        target_fee = total_fee_usd * fx.get_mid_rate("USD", node_path[-1])
        final_amount = gross_target_amount - target_fee
        if final_amount < 0:
            final_amount = Decimal("0")

        return Route(
            hops=hops,
            total_fee_usd=total_fee_usd,
            total_time_hours=total_time_hours,
            source_currency=node_path[0],
            target_currency=node_path[-1],
            source_amount=amount,
            final_amount=final_amount,
            routing_preference=preference,
        )

    def _select_best_edge(
        self,
        from_currency: str,
        to_currency: str,
        score_context: _ScoreContext,
    ) -> NetworkEdge | None:
        best_edge: NetworkEdge | None = None
        best_weight: float | None = None
        for edge in self._graph.get_edges(from_currency, to_currency):
            weight = self._edge_weight(edge, score_context)
            if weight is None:
                continue
            if best_weight is None or weight < best_weight:
                best_edge = edge
                best_weight = weight
        return best_edge

    def _path_score(self, node_path: list[str], score_context: _ScoreContext) -> float:
        score = 0.0
        for from_currency, to_currency in zip(node_path, node_path[1:]):
            edge = self._select_best_edge(from_currency, to_currency, score_context)
            if edge is None:
                return float("inf")
            edge_weight = self._edge_weight(edge, score_context)
            if edge_weight is None:
                return float("inf")
            score += edge_weight
        return score

    def _route_score(self, route: Route, score_context: _ScoreContext) -> float:
        score = 0.0
        for hop in route.hops:
            edge = NetworkEdge(
                network_name=hop.network_name,
                from_currency=hop.currency_in,
                to_currency=hop.currency_out,
                fee_usd=hop.fee_usd,
                time_hours=float(hop.time_hours),
                fx_rate=hop.fx_rate,
                data_source=hop.data_source,
                amount_at_send=route.source_amount,
            )
            edge_weight = self._edge_weight(edge, score_context)
            if edge_weight is not None:
                score += edge_weight
        return score

    @staticmethod
    def _edge_weight(edge: object, score_context: _ScoreContext) -> float | None:
        if not isinstance(edge, NetworkEdge):
            return None

        fee_component = (
            float(edge.fee_usd / score_context.max_fee) if score_context.max_fee > 0 else 0.0
        )
        edge_time = Decimal(str(edge.time_hours))
        time_component = (
            float(edge_time / score_context.max_time) if score_context.max_time > 0 else 0.0
        )
        return (score_context.alpha * fee_component) + (score_context.beta * time_component)

    @staticmethod
    def _zero_hop_route(
        currency: str,
        amount: Decimal,
        preference: RoutingPreference,
    ) -> Route:
        return Route(
            hops=[],
            total_fee_usd=Decimal("0"),
            total_time_hours=Decimal("0"),
            source_currency=currency,
            target_currency=currency,
            source_amount=amount,
            final_amount=amount,
            routing_preference=preference,
        )


@dataclass(config=ConfigDict(frozen=True))
class _ScoreContext:
    alpha: float
    beta: float
    max_fee: Decimal
    max_time: Decimal

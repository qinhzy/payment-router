from __future__ import annotations

from dataclasses import field
from decimal import Decimal

import networkx as nx
from pydantic import ConfigDict, Field, model_validator
from pydantic.dataclasses import dataclass

from payment_router.core import fx
from payment_router.core.graph import NetworkEdge, PaymentGraph
from payment_router.core.models import Hop, Route


@dataclass(config=ConfigDict(frozen=True, allow_inf_nan=False))
class RoutingPreference:
    cost_weight: float = Field(default=0.5, ge=0)
    time_weight: float = Field(default=0.5, ge=0)
    max_hops: int = Field(default=5, ge=1)
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

        if not amount.is_finite() or amount <= 0:
            return None
        if source_currency == target_currency:
            routes = self._same_currency_routes(
                source_currency,
                amount,
                preference,
                top_n=1,
            )
            return routes[0] if routes else None
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

        route = self._route_from_path(node_path, amount, preference, score_context)
        if route is not None:
            return route

        # The static shortest path can still be unusable when a fixed fee consumes
        # the live balance. Continue through ranked alternatives instead of
        # returning a zero-value route or incorrectly reporting no path.
        alternatives = self.find_all_routes(
            source_currency,
            target_currency,
            amount,
            preference,
            top_n=1,
        )
        return alternatives[0] if alternatives else None

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

        if top_n <= 0 or not amount.is_finite() or amount <= 0:
            return []
        if source_currency == target_currency:
            return self._same_currency_routes(
                source_currency,
                amount,
                preference,
                top_n=top_n,
            )
        if source_currency not in self._graph.graph or target_currency not in self._graph.graph:
            return []

        score_context = self._build_score_context(preference)
        expanded_graph = self._build_expanded_graph(score_context)

        try:
            path_generator = nx.shortest_simple_paths(
                expanded_graph,
                source_currency,
                target_currency,
                weight="weight",
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

        scored_routes: list[tuple[float, Route]] = []
        try:
            for expanded_path in path_generator:
                edges = self._edges_from_expanded_path(expanded_graph, expanded_path)
                if len(edges) > preference.max_hops:
                    continue

                route = self._route_from_edges(edges, amount, preference)
                if route is not None:
                    scored_routes.append((self._edge_path_score(edges, score_context), route))
                if len(scored_routes) == top_n:
                    break
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

        scored_routes.sort(key=self._scored_route_sort_key)
        return [route for _, route in scored_routes]

    def _build_score_context(self, preference: RoutingPreference) -> _ScoreContext:
        edges = [
            data["edge"]
            for _, _, _, data in self._graph.graph.edges(keys=True, data=True)
            if isinstance(data.get("edge"), NetworkEdge)
        ]
        max_cost = max(
            (self._edge_cost_usd(edge) for edge in edges),
            default=Decimal("0"),
        )
        max_time = max((Decimal(str(edge.time_hours)) for edge in edges), default=Decimal("0"))
        return _ScoreContext(
            alpha=preference.alpha,
            beta=preference.beta,
            max_cost=max_cost,
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
            if from_currency == to_currency:
                continue
            best_edge = self._select_best_edge(from_currency, to_currency, score_context)
            if best_edge is None:
                continue
            projected_graph.add_edge(
                from_currency,
                to_currency,
                weight=self._edge_weight(best_edge, score_context),
            )

        return projected_graph

    def _build_expanded_graph(self, score_context: _ScoreContext) -> nx.DiGraph:
        """Represent each parallel payment edge as its own intermediate node."""
        expanded_graph = nx.DiGraph()
        expanded_graph.add_nodes_from(self._graph.graph.nodes)

        edges = [
            edge
            for _, _, _, data in self._graph.graph.edges(keys=True, data=True)
            if isinstance((edge := data.get("edge")), NetworkEdge)
            and edge.from_currency != edge.to_currency
            and self._edge_weight(edge, score_context) is not None
        ]
        edges.sort(key=self._edge_sort_key)

        for index, edge in enumerate(edges):
            edge_node = ("payment-edge", index)
            expanded_graph.add_node(edge_node, edge=edge)
            expanded_graph.add_edge(
                edge.from_currency,
                edge_node,
                weight=self._edge_weight(edge, score_context),
            )
            expanded_graph.add_edge(edge_node, edge.to_currency, weight=0.0)

        return expanded_graph

    @staticmethod
    def _edges_from_expanded_path(
        expanded_graph: nx.DiGraph,
        expanded_path: list[object],
    ) -> list[NetworkEdge]:
        return [
            edge
            for node in expanded_path
            if isinstance((edge := expanded_graph.nodes[node].get("edge")), NetworkEdge)
        ]

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
        final_amount = amount
        for from_currency, to_currency in zip(node_path, node_path[1:], strict=False):
            edge = self._select_best_edge(
                from_currency,
                to_currency,
                score_context,
                available_amount=final_amount,
            )
            if edge is None:
                return None
            edges.append(edge)
            fee_in_source_currency = edge.fee_usd * fx.get_mid_rate(
                "USD",
                edge.from_currency,
            )
            final_amount = (final_amount - fee_in_source_currency) * edge.fx_rate

        return self._route_from_edges(edges, amount, preference)

    def _route_from_edges(
        self,
        edges: list[NetworkEdge],
        amount: Decimal,
        preference: RoutingPreference,
    ) -> Route | None:
        if not edges:
            return None

        final_amount = amount
        for edge in edges:
            fee_in_source_currency = edge.fee_usd * fx.get_mid_rate(
                "USD",
                edge.from_currency,
            )
            if final_amount <= fee_in_source_currency:
                return None
            final_amount = (final_amount - fee_in_source_currency) * edge.fx_rate

        hops = [
            Hop(
                from_node=edge.from_currency,
                to_node=edge.to_currency,
                network_name=edge.network_name,
                fee_usd=edge.fee_usd,
                time_hours=Decimal(str(edge.time_hours)),
                time_min_hours=Decimal(str(edge.time_min_hours)),
                time_max_hours=Decimal(str(edge.time_max_hours)),
                currency_in=edge.from_currency,
                currency_out=edge.to_currency,
                fx_rate=edge.fx_rate,
                data_source=edge.data_source,
                fee_data_source=edge.fee_data_source,
                time_data_source=edge.time_data_source,
                fx_data_source=edge.fx_data_source,
            )
            for edge in edges
        ]
        total_fee_usd = sum((edge.fee_usd for edge in edges), start=Decimal("0"))
        total_time_hours = sum(
            (Decimal(str(edge.time_hours)) for edge in edges),
            start=Decimal("0"),
        )
        return Route(
            hops=hops,
            total_fee_usd=total_fee_usd,
            total_time_hours=total_time_hours,
            total_time_min_hours=sum(
                (Decimal(str(edge.time_min_hours)) for edge in edges),
                start=Decimal("0"),
            ),
            total_time_max_hours=sum(
                (Decimal(str(edge.time_max_hours)) for edge in edges),
                start=Decimal("0"),
            ),
            source_currency=edges[0].from_currency,
            target_currency=edges[-1].to_currency,
            source_amount=amount,
            final_amount=final_amount,
            routing_preference=preference,
        )

    def _select_best_edge(
        self,
        from_currency: str,
        to_currency: str,
        score_context: _ScoreContext,
        available_amount: Decimal | None = None,
    ) -> NetworkEdge | None:
        best_edge: NetworkEdge | None = None
        best_weight: float | None = None
        for edge in self._graph.get_edges(from_currency, to_currency):
            if available_amount is not None:
                fee_in_source_currency = edge.fee_usd * fx.get_mid_rate(
                    "USD",
                    edge.from_currency,
                )
                if available_amount <= fee_in_source_currency:
                    continue
            weight = self._edge_weight(edge, score_context)
            if weight is None:
                continue
            if best_weight is None or weight < best_weight:
                best_edge = edge
                best_weight = weight
        return best_edge

    def _path_score(self, node_path: list[str], score_context: _ScoreContext) -> float:
        score = 0.0
        for from_currency, to_currency in zip(node_path, node_path[1:], strict=False):
            edge = self._select_best_edge(from_currency, to_currency, score_context)
            if edge is None:
                return float("inf")
            edge_weight = self._edge_weight(edge, score_context)
            if edge_weight is None:
                return float("inf")
            score += edge_weight
        return score

    def _edge_path_score(
        self,
        edges: list[NetworkEdge],
        score_context: _ScoreContext,
    ) -> float:
        weights = [self._edge_weight(edge, score_context) for edge in edges]
        if any(weight is None for weight in weights):
            return float("inf")
        return sum(weight for weight in weights if weight is not None)

    def _same_currency_routes(
        self,
        currency: str,
        amount: Decimal,
        preference: RoutingPreference,
        *,
        top_n: int,
    ) -> list[Route]:
        if currency not in self._graph.graph:
            return []

        edges = self._graph.get_edges(currency, currency)
        if not edges:
            return [self._zero_hop_route(currency, amount, preference)]

        score_context = self._build_score_context(preference)
        scored_routes: list[tuple[float, Route]] = []
        for edge in edges:
            route = self._route_from_edges([edge], amount, preference)
            if route is not None:
                scored_routes.append((self._edge_path_score([edge], score_context), route))

        scored_routes.sort(key=self._scored_route_sort_key)
        return [route for _, route in scored_routes[:top_n]]

    @staticmethod
    def _edge_sort_key(edge: NetworkEdge) -> tuple[object, ...]:
        return (
            edge.from_currency,
            edge.to_currency,
            edge.network_name,
            edge.fee_usd,
            edge.time_hours,
            edge.fx_rate,
            edge.data_source.value,
        )

    @staticmethod
    def _scored_route_sort_key(scored_route: tuple[float, Route]) -> tuple[object, ...]:
        score, route = scored_route
        return (
            score,
            len(route.hops),
            tuple(hop.network_name for hop in route.hops),
            tuple(hop.to_node for hop in route.hops),
        )

    def _edge_weight(self, edge: object, score_context: _ScoreContext) -> float | None:
        if not isinstance(edge, NetworkEdge):
            return None

        cost_component = (
            float(self._edge_cost_usd(edge) / score_context.max_cost)
            if score_context.max_cost > 0
            else 0.0
        )
        edge_time = Decimal(str(edge.time_hours))
        time_component = (
            float(edge_time / score_context.max_time) if score_context.max_time > 0 else 0.0
        )
        return (score_context.alpha * cost_component) + (score_context.beta * time_component)

    @staticmethod
    def _edge_cost_usd(edge: NetworkEdge) -> Decimal:
        mid_rate = fx.get_mid_rate(edge.from_currency, edge.to_currency)
        spread_fraction = max(
            Decimal("1") - (edge.fx_rate / mid_rate),
            Decimal("0"),
        )
        spread_cost_source = edge.amount_at_send * spread_fraction
        return edge.fee_usd + fx.to_usd(spread_cost_source, edge.from_currency)

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
    max_cost: Decimal
    max_time: Decimal

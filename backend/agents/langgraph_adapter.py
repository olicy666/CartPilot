from __future__ import annotations

from collections.abc import Callable
from typing import Any


try:
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
except ModuleNotFoundError:
    LANGGRAPH_AVAILABLE = False
    START = "__start__"
    END = "__end__"

    class StateGraph:  # type: ignore[no-redef]
        """Tiny local fallback for the subset of LangGraph used by this MVP.

        The real project uses LangGraph when installed from requirements.txt. This
        fallback keeps local demos and tests runnable in environments without the
        dependency.
        """

        def __init__(self, state_schema: type[Any]):
            self._nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
            self._edges: dict[str, str] = {}
            self._conditional_edges: dict[str, tuple[Callable[[dict[str, Any]], str], dict[str, str]]] = {}

        def add_node(
            self,
            name: str,
            action: Callable[[dict[str, Any]], dict[str, Any]],
        ) -> None:
            self._nodes[name] = action

        def add_edge(self, start_key: str, end_key: str) -> None:
            self._edges[start_key] = end_key

        def add_conditional_edges(
            self,
            source: str,
            path: Callable[[dict[str, Any]], str],
            path_map: dict[str, str],
        ) -> None:
            self._conditional_edges[source] = (path, path_map)

        def compile(self) -> "_CompiledFallbackGraph":
            return _CompiledFallbackGraph(
                nodes=self._nodes,
                edges=self._edges,
                conditional_edges=self._conditional_edges,
            )


class _CompiledFallbackGraph:
    def __init__(
        self,
        nodes: dict[str, Callable[[dict[str, Any]], dict[str, Any]]],
        edges: dict[str, str],
        conditional_edges: dict[str, tuple[Callable[[dict[str, Any]], str], dict[str, str]]],
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._conditional_edges = conditional_edges

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        current = self._edges.get(START)
        next_state = dict(state)

        while current and current != END:
            update = self._nodes[current](next_state)
            next_state.update(update)

            if current in self._conditional_edges:
                route_fn, route_map = self._conditional_edges[current]
                route = route_fn(next_state)
                current = route_map[route]
            else:
                current = self._edges.get(current)

        return next_state

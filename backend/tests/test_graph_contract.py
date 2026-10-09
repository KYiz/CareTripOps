from langgraph.checkpoint.memory import MemorySaver

from app.graph import build_graph


def test_graph_compiles_with_required_nodes():
    graph = build_graph(MemorySaver())
    names = set(graph.get_graph().nodes)
    assert {"requirements", "wait_clarification", "itinerary", "discovery", "comparison", "evidence",
            "manager", "prepare_approval", "wait_approval", "booking", "review",
            "rejected", "human_review"}.issubset(names)

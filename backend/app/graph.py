"""The CareTrip workflow graph. Nodes live in app.workflow.*; this module only wires them together.

Node names are looked up here when the graph is built, so tests can swap a node by patching this module.
"""

from langgraph.graph import END, START, StateGraph

from app.workflow.checkout import (approval_worker, booking_worker, human_review_worker, payment_failed_worker,
                                   prepare_payment_worker, rejected_worker, review_worker, route_after_payment,
                                   route_booking, route_decision, route_payment, route_prepared, wait_approval,
                                   wait_payment)
from app.workflow.offers import (comparison_worker, discovery_worker, evidence_worker, manager_worker, route_candidate,
                                 route_manager, wait_review)
from app.workflow.planning import itinerary_worker, requirements_worker, route_requirements, wait_clarification
from app.workflow.state import FlowState


def build_graph(checkpointer):
    graph = StateGraph(FlowState)
    for name, node in {
        "requirements": requirements_worker, "wait_clarification": wait_clarification,
        "itinerary": itinerary_worker,
        "discovery": discovery_worker, "comparison": comparison_worker,
        "evidence": evidence_worker, "manager": manager_worker, "wait_review": wait_review,
        "prepare_approval": approval_worker, "wait_approval": wait_approval,
        "prepare_payment": prepare_payment_worker, "wait_payment": wait_payment,
        "payment_failed": payment_failed_worker,
        "booking": booking_worker, "review": review_worker,
        "rejected": rejected_worker, "human_review": human_review_worker,
    }.items():
        graph.add_node(name, node)
    graph.add_edge(START, "requirements")
    graph.add_conditional_edges("requirements", route_requirements)
    graph.add_edge("wait_clarification", "requirements")
    graph.add_edge("itinerary", "discovery")
    graph.add_edge("discovery", "comparison")
    graph.add_conditional_edges("comparison", route_candidate)
    graph.add_edge("evidence", "manager")
    graph.add_conditional_edges("manager", route_manager)
    graph.add_edge("wait_review", "comparison")
    graph.add_conditional_edges("prepare_approval", route_prepared)
    graph.add_conditional_edges("wait_approval", route_decision)
    graph.add_conditional_edges("prepare_payment", route_payment)
    graph.add_conditional_edges("wait_payment", route_after_payment)
    graph.add_conditional_edges("booking", route_booking)
    for terminal in ("review", "rejected", "human_review", "payment_failed"):
        graph.add_edge(terminal, END)
    return graph.compile(checkpointer=checkpointer)


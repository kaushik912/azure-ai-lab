"""LangGraph flow: retrieve -> grounded? -> answer | decline.

'decline' makes no LLM call: cheap and prevents hallucination.
Easy extension points: retry-with-rewritten-query loop, HITL, tools.
"""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .clients import openai_client
from .config import get_settings
from .retrieval import hybrid_search


class State(TypedDict, total=False):
    question: str
    context: list[dict]
    answer: str


async def retrieve_node(state: State) -> State:
    return {"context": await hybrid_search(state["question"])}


def is_grounded(state: State) -> str:
    s = get_settings()
    ctx = state.get("context") or []
    ok = any(c["rerank_score"] >= s.min_rerank_score for c in ctx)
    return "answer" if ok else "decline"


def build_messages(state: State) -> list[dict]:
    ctx = state.get("context") or []
    system = "Answer concisely."
    if ctx:
        joined = "\n\n".join(f"[{c['source']}] {c['content']}" for c in ctx)
        system = f"Answer ONLY from the context; cite sources in [brackets].\n\n{joined}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": state["question"]},
    ]


async def answer_node(state: State) -> State:
    s = get_settings()
    resp = await openai_client().chat.completions.create(
        model=s.azure_openai_chat_deployment,
        messages=build_messages(state),
        max_tokens=s.max_output_tokens,
        temperature=0.1,
    )
    return {"answer": resp.choices[0].message.content or ""}


async def decline_node(state: State) -> State:
    return {"answer": "I don't know based on the indexed documents."}


def build_graph():
    g = StateGraph(State)
    g.add_node("retrieve", retrieve_node)
    g.add_node("answer", answer_node)
    g.add_node("decline", decline_node)
    g.add_edge(START, "retrieve")
    g.add_conditional_edges("retrieve", is_grounded, {"answer": "answer", "decline": "decline"})
    g.add_edge("answer", END)
    g.add_edge("decline", END)
    return g.compile()

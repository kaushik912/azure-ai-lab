import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import State, build_graph, build_messages, is_grounded, retrieve_node
from .clients import openai_client
from .config import get_settings

app = FastAPI(title="azure-ai-lab")
graph = build_graph()


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/ask")
async def ask(req: AskRequest):
    """Full LangGraph run: retrieve -> answer | decline."""
    out = await graph.ainvoke({"question": req.question})
    return {"answer": out["answer"], "sources": out.get("context", [])}


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """SSE token streaming. Same grounding gate as /ask."""
    state: State = {"question": req.question}
    state.update(await retrieve_node(state))

    async def gen():
        if is_grounded(state) == "decline":
            yield f"data: {json.dumps('I don' + chr(39) + 't know based on the indexed documents.')}\n\n"
            yield "data: [DONE]\n\n"
            return
        s = get_settings()
        stream = await openai_client().chat.completions.create(
            model=s.azure_openai_chat_deployment,
            messages=build_messages(state),
            max_tokens=s.max_output_tokens,
            temperature=0.1,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield f"data: {json.dumps(chunk.choices[0].delta.content)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

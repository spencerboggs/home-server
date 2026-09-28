import threading
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="LLMLingua")
state = {"ready": False, "error": "", "compressor": None}


class Payload(BaseModel):
    text: str


def load() -> None:
    try:
        from llmlingua import PromptCompressor

        state["compressor"] = PromptCompressor(device_map="cpu")
        state["ready"] = True
    except Exception as exc:
        state["error"] = str(exc)


@app.on_event("startup")
def startup() -> None:
    threading.Thread(target=load, daemon=True).start()


@app.get("/health")
def health() -> dict:
    return {"ready": state["ready"], "error": state["error"]}


@app.post("/compress")
def compress(payload: Payload) -> dict:
    if not state["ready"] or state["compressor"] is None:
        detail = state["error"] or "LLMLingua is still loading its model"
        raise HTTPException(status_code=503, detail=detail)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    result = state["compressor"].compress_prompt(text, rate=0.5)
    compressed = result.get("compressed_prompt") if isinstance(result, dict) else None
    if not compressed:
        raise HTTPException(status_code=502, detail="LLMLingua did not return compressed text")
    return {"text": compressed}

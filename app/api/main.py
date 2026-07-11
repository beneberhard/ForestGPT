from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import OPENAI_BASE_URL, OPENAI_MODEL
from app.geo.routes import router as stands_router
from app.llm.routes import router as chat_router
from app.rag.routes import router as documents_router
from app.simulation.routes import router as simulation_router

app = FastAPI(
    title="ForestGPT Trial API",
    description="Decision-support backend for stands, forest growth simulations, RAG, and manager chat.",
    version="0.1.0",
)

app.include_router(stands_router)
app.include_router(simulation_router)
app.include_router(documents_router)
app.include_router(chat_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")


@app.get("/")
def frontend_redirect() -> RedirectResponse:
    return RedirectResponse(url="/app/")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "openai_base_url": OPENAI_BASE_URL, "openai_model": OPENAI_MODEL}

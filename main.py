from fastapi import FastAPI
import uvicorn

from api.contracts import router as contracts_router
from api.health import router as health_router

app = FastAPI()
app.include_router(health_router)
app.include_router(contracts_router)


@app.get("/")
def read_root() -> dict:
    return {"status": "ok"}


@app.get("/db/health")
def db_health() -> dict:
    with engine.connect() as conn:
        value = conn.execute(text("SELECT 1")).scalar()
    return {"db_ok": value == 1}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

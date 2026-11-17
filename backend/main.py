import os
import socket
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis
from fastapi import APIRouter, FastAPI, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

r = redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,  # respostas voltam como str, não bytes
)

# Modelagem no Redis:
#   item:<id>      -> Hash com os campos do item
#   items:by_date  -> Sorted Set (membro = id, pontuação = created_at) para listar por data
INDEX = "items:by_date"


def key(item_id: str) -> str:
    return f"item:{item_id}"


# Atualiza só se o item existir, de forma atômica (evita recriar um item apagado).
UPDATE_IF_EXISTS = r.register_script(
    """
if redis.call('EXISTS', KEYS[1]) == 0 then
  return 0
end
redis.call('HSET', KEYS[1], unpack(ARGV))
return 1
"""
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await r.aclose()


app = FastAPI(title="Lab App API", lifespan=lifespan)
api = APIRouter(prefix="/api")  # o ALB só encaminha /api/* para cá


# ---------- Schemas ----------
class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    done: bool = False


class ItemUpdate(BaseModel):
    """Usado no PATCH: todos os campos são opcionais."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    done: Optional[bool] = None


class ItemOut(ItemCreate):
    id: str
    created_at: datetime
    updated_at: datetime


# ---------- Helpers ----------
def now() -> datetime:
    return datetime.now(timezone.utc)


def to_id(item_id: str) -> str:
    """Valida e normaliza o id (UUID). Id inválido é tratado como inexistente."""
    try:
        return str(uuid.UUID(item_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Item não encontrado")


def to_hash(fields: dict) -> dict:
    """O Redis só guarda texto: bool vira "1"/"0"."""
    return {k: ("1" if v else "0") if isinstance(v, bool) else v for k, v in fields.items()}


def to_out(item_id: str, h: dict) -> ItemOut:
    ts = now().isoformat()
    return ItemOut(
        id=item_id,
        name=h.get("name") or "(sem nome)",
        description=h.get("description", ""),
        done=h.get("done") == "1",
        created_at=h.get("created_at", ts),
        updated_at=h.get("updated_at", ts),
    )


async def fetch_many(ids: list[str]) -> list[tuple[str, dict]]:
    if not ids:
        return []
    async with r.pipeline(transaction=False) as p:
        for i in ids:
            p.hgetall(key(i))
        results = await p.execute()
    return [(i, h) for i, h in zip(ids, results) if h]


async def apply_update(item_id: str, fields: dict) -> ItemOut:
    payload = {**to_hash(fields), "updated_at": now().isoformat()}
    args: list[str] = []
    for k, v in payload.items():
        args += [k, v]
    updated = await UPDATE_IF_EXISTS(keys=[key(item_id)], args=args)
    if not updated:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return to_out(item_id, await r.hgetall(key(item_id)))


# ---------- Saúde ----------
@api.get("/health")
async def health():
    # health check do ALB: não toca no Redis de propósito
    return {"status": "ok"}


@api.get("/db-health")
async def db_health():
    await r.ping()
    return {"redis": "ok"}


@api.get("/whoami")
async def whoami():
    # container: o hostname dentro do container é o ID dele
    # ip/zona/instance_id: vêm da EC2 hospedeira, injetados pelo user_data
    return {
        "container": socket.gethostname(),
        "ip": os.getenv("HOST_IP", "desconhecido"),
        "zone": os.getenv("HOST_AZ", "desconhecida"),
        "instance_id": os.getenv("HOST_INSTANCE_ID", "desconhecida"),
    }


# ---------- CRUD ----------
@api.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(data: ItemCreate):
    item_id = str(uuid.uuid4())
    ts = now()
    h = {
        **to_hash(data.model_dump()),
        "created_at": ts.isoformat(),
        "updated_at": ts.isoformat(),
    }
    # grava o item e o índice juntos, de forma atômica
    async with r.pipeline(transaction=True) as p:
        p.hset(key(item_id), mapping=h)
        p.zadd(INDEX, {item_id: ts.timestamp()})
        await p.execute()
    return to_out(item_id, h)


@api.get("/items", response_model=list[ItemOut])
async def list_items(
    done: Optional[bool] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    if done is None:
        # caminho rápido: o Sorted Set já está ordenado (mais novos primeiro)
        ids = await r.zrevrange(INDEX, skip, skip + limit - 1)
        rows = await fetch_many(ids)
    else:
        # o Redis não filtra por campo: lê tudo e filtra aqui (ok para poucos itens)
        ids = await r.zrevrange(INDEX, 0, -1)
        rows = [(i, h) for i, h in await fetch_many(ids) if (h.get("done") == "1") == done]
        rows = rows[skip : skip + limit]
    return [to_out(i, h) for i, h in rows]


@api.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: str):
    item_id = to_id(item_id)
    h = await r.hgetall(key(item_id))
    if not h:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return to_out(item_id, h)


@api.put("/items/{item_id}", response_model=ItemOut)
async def replace_item(item_id: str, data: ItemCreate):
    """Substitui o item inteiro (todos os campos)."""
    return await apply_update(to_id(item_id), data.model_dump())


@api.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: str, data: ItemUpdate):
    """Atualiza só os campos enviados."""
    changes = {k: v for k, v in data.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    return await apply_update(to_id(item_id), changes)


@api.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: str):
    item_id = to_id(item_id)
    async with r.pipeline(transaction=True) as p:
        p.delete(key(item_id))
        p.zrem(INDEX, item_id)
        deleted, _ = await p.execute()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.include_router(api)

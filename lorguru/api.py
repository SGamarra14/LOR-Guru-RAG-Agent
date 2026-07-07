# -*- coding: utf-8 -*-
"""La API de LoR Guru (fase 2).

Diseño:

- **Lifespan que solo carga.** Al arrancar se cargan datos + glosario +
  modelo de embeddings + índice YA construido (`cargar_recursos`). Si el
  índice no existe, el arranque falla rápido con el comando de build — el
  servidor nunca decide reconstruir (separación indexado/servido).
- **BYOK.** El endpoint de agente recibe `proveedor`, `modelo` (opcional) y
  `api_key` en el body (nunca query string). La clave se usa para esa
  llamada vía LiteLLM y no se persiste, no se loguea y no aparece en errores.
- **Streaming.** /agente/stream expone el loop como Server-Sent Events POR
  PASOS (inicio, tool_use, tool_result, respuesta). El streaming token a
  token queda documentado como pendiente explícito de la fase 3 (ver
  GUIA_FASE2.md, sección 6a).
- **CORS** con orígenes desde la variable de entorno ORIGENES_CORS
  (separados por coma), default el localhost de Next.js.
"""
import json
import os
import re
from contextlib import asynccontextmanager
from typing import Literal, Optional

import litellm
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import __version__
from .agente import PROVEEDORES, carta_a_dict, consultar_agente, eventos_agente
from .stores import (MODELO_EMBEDDINGS, Recursos, buscar_semantica,
                     cargar_recursos, filtrar_cartas)

load_dotenv()

recursos: Recursos = None  # se llena en el lifespan


@asynccontextmanager
async def lifespan(app: FastAPI):
    global recursos
    recursos = cargar_recursos()  # RuntimeError con instrucciones si falta el build
    print(f"API lista: {len(recursos.df)} cartas, embeddings {MODELO_EMBEDDINGS}")
    yield


app = FastAPI(
    title="LoR Guru API",
    version=__version__,
    description="Búsqueda de cartas de Legends of Runeterra en lenguaje "
                "natural (es_mx): filtros exactos, búsqueda semántica e "
                "híbrida, y agente multi-proveedor (BYOK).",
    lifespan=lifespan,
)

ORIGENES_CORS = [o.strip() for o in
                 os.environ.get("ORIGENES_CORS", "http://localhost:3000").split(",")
                 if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENES_CORS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas ---------------------------------------------------------------

class FiltroParams(BaseModel):
    """Los mismos parámetros validados en fase 1 para filtrar_cartas."""
    region: Optional[str] = Field(None, description="Ref de región (inglés), p. ej. 'Noxus'")
    costo_min: Optional[int] = Field(None, ge=0)
    costo_max: Optional[int] = Field(None, ge=0)
    ataque_min: Optional[int] = Field(None, ge=0)
    ataque_max: Optional[int] = Field(None, ge=0)
    vida_min: Optional[int] = Field(None, ge=0)
    vida_max: Optional[int] = Field(None, ge=0)
    tipo: Optional[str] = Field(None, description="'Unidad', 'Hechizo', 'Hito' o 'Equipo'")
    supertipo: Optional[str] = Field(None, description="'Campeón'")
    keywords: Optional[list[str]] = Field(None, description="Refs de keywords; la carta debe tener todas")
    rareza: Optional[str] = Field(None, description="Ref de rareza, p. ej. 'Champion'")
    velocidad: Optional[str] = Field(None, description="Ref de velocidad de hechizo, p. ej. 'Burst'")


class BusquedaRequest(BaseModel):
    texto_consulta: str = Field(..., min_length=1,
                                description="Descripción en español del efecto buscado")
    top_k: int = Field(10, ge=1, le=100)
    filtro_metadata: Optional[FiltroParams] = Field(
        None, description="Filtros exactos para acotar ANTES de buscar (híbrido)")


class AgenteRequest(BaseModel):
    consulta: str = Field(..., min_length=1)
    proveedor: Literal["anthropic", "gemini", "openai"] = "anthropic"
    modelo: Optional[str] = Field(None, description="Default por proveedor si se omite")
    api_key: str = Field(..., min_length=8,
                         description="La clave del usuario para el proveedor "
                                     "elegido (BYOK). Solo en body, nunca en "
                                     "query string; no se persiste ni loguea.")
    max_turnos: int = Field(6, ge=1, le=10)


class CartaOut(BaseModel):
    cardCode: str
    nombre: str
    regiones: list[str]
    regionRefs: list[str]
    coste: int
    ataque: int
    vida: int
    tipo: str
    supertipo: str
    rareza: str
    rarityRef: str
    velocidadRef: str
    keywords: list[str]
    keywordRefs: list[str]
    descripcion: str
    descripcionSubida: str
    imagen: str
    imagenFull: str
    distancia: Optional[float] = None


class CartasResponse(BaseModel):
    total: int
    cartas: list[CartaOut]


class LlamadaTool(BaseModel):
    tool: str
    entrada: dict
    total: int


class AgenteResponse(BaseModel):
    respuesta: str
    cartas: list[CartaOut]
    llamadas: list[LlamadaTool]
    metodo_cartas: Literal["citadas", "ultima_llamada", "ninguna"]


class ProveedorOut(BaseModel):
    id: str
    modelo_default: str
    verificado: bool


# --- Helpers ----------------------------------------------------------------

def _df_a_cartas(df) -> list[dict]:
    cartas = []
    for _, fila in df.iterrows():
        carta = carta_a_dict(fila, recursos.glosario, completo=True)
        if "distancia" in fila:
            carta["distancia"] = float(fila["distancia"])
        cartas.append(carta)
    return cartas


def _mensaje_proveedor(e: Exception) -> str:
    """Extrae el mensaje humano del error del proveedor (p. ej. 'Your credit
    balance is too low...') sin volcar el body completo. Los mensajes de los
    proveedores no incluyen la api_key, pero se recorta por higiene."""
    texto = getattr(e, "message", "") or str(e)
    encontrado = re.search(r'"message"\s*:\s*"([^"]+)"', texto)
    return (encontrado.group(1) if encontrado else texto)[:300]


def _error_agente(e: Exception) -> HTTPException:
    """Mapea errores del proveedor a HTTP útil para el cliente, sin filtrar
    jamás la api_key en el mensaje."""
    if isinstance(e, litellm.AuthenticationError):
        return HTTPException(401, "El proveedor rechazó la api_key enviada.")
    if isinstance(e, litellm.RateLimitError):
        return HTTPException(429, "El proveedor devolvió rate limit; reintenta en unos segundos.")
    if isinstance(e, (litellm.BadRequestError, litellm.NotFoundError)):
        # Aquí caen tanto modelos inválidos como problemas de cuenta (p. ej.
        # crédito agotado) — el mensaje del proveedor es lo accionable.
        return HTTPException(400, f"El proveedor rechazó la petición: {_mensaje_proveedor(e)}")
    if isinstance(e, ValueError):
        return HTTPException(400, str(e))
    return HTTPException(502, f"Error del proveedor: {type(e).__name__}")


# --- Endpoints ---------------------------------------------------------------

@app.get("/salud")
def salud():
    return {"ok": True, "version": __version__, "cartas": len(recursos.df),
            "modelo_embeddings": MODELO_EMBEDDINGS}


@app.get("/proveedores", response_model=list[ProveedorOut])
def proveedores():
    """Los proveedores BYOK. `verificado`=False significa que el set de
    evaluación NO se ha corrido contra ese proveedor (hoy: openai/GPT, sin
    API key para probarlo) — el cliente debería señalarlo en su UI."""
    return [{"id": pid, **datos} for pid, datos in PROVEEDORES.items()]


@app.post("/cartas/filtrar", response_model=CartasResponse)
def filtrar(filtro: FiltroParams):
    try:
        resultado = filtrar_cartas(recursos.df, **filtro.model_dump(exclude_none=True))
    except TypeError as e:
        raise HTTPException(400, f"Filtro inválido: {e}")
    return {"total": len(resultado), "cartas": _df_a_cartas(resultado)}


@app.post("/cartas/buscar", response_model=CartasResponse)
def buscar(peticion: BusquedaRequest):
    filtro = (peticion.filtro_metadata.model_dump(exclude_none=True)
              if peticion.filtro_metadata else None)
    resultado = buscar_semantica(recursos, peticion.texto_consulta,
                                 top_k=peticion.top_k, filtro_metadata=filtro)
    return {"total": len(resultado), "cartas": _df_a_cartas(resultado)}


@app.post("/agente", response_model=AgenteResponse)
def agente(peticion: AgenteRequest):
    try:
        return consultar_agente(
            recursos, peticion.consulta, api_key=peticion.api_key,
            proveedor=peticion.proveedor, modelo=peticion.modelo,
            max_turnos=peticion.max_turnos,
        )
    except Exception as e:
        raise _error_agente(e)


@app.post("/agente/stream")
def agente_stream(peticion: AgenteRequest):
    """El mismo loop, como Server-Sent Events POR PASOS: eventos JSON
    `inicio`, `tool_use`, `tool_result` y `respuesta` (el final, con texto y
    cartas). Suficiente para que la fase 3 muestre progreso en tiempo real;
    el streaming token a token del texto queda para la fase 3."""
    def flujo():
        try:
            for evento in eventos_agente(
                    recursos, peticion.consulta, api_key=peticion.api_key,
                    proveedor=peticion.proveedor, modelo=peticion.modelo,
                    max_turnos=peticion.max_turnos):
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"
        except Exception as e:
            error = _error_agente(e)
            yield ("data: " + json.dumps(
                {"tipo": "error", "status": error.status_code,
                 "detalle": error.detail}, ensure_ascii=False) + "\n\n")

    return StreamingResponse(flujo(), media_type="text/event-stream")

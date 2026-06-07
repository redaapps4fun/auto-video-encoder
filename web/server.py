"""FastAPI web server for headless mode."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PySide6.QtCore import QMetaObject, Qt, Q_ARG

from config import _deep_merge, _base_defaults
from web.bridge import HeadlessBridge


def get_static_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "web" / "static"
    return Path(__file__).resolve().parent / "static"


class EventHub:
    """Broadcast bridge events to connected WebSocket clients."""

    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def broadcast_from_thread(self, event: dict):
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(event), self._loop)

    async def add(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket):
        async with self._lock:
            self._clients.discard(ws)

    async def _broadcast(self, event: dict):
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


def _invoke_qt(bridge: HeadlessBridge, method: str, *args):
    connection = Qt.ConnectionType.BlockingQueuedConnection
    if not args:
        ok = QMetaObject.invokeMethod(bridge, method, connection)
    elif len(args) == 1 and isinstance(args[0], dict):
        ok = QMetaObject.invokeMethod(
            bridge, method, connection, Q_ARG(str, json.dumps(args[0]))
        )
    elif len(args) == 1 and isinstance(args[0], str):
        ok = QMetaObject.invokeMethod(bridge, method, connection, Q_ARG(str, args[0]))
    else:
        raise ValueError("Unsupported invoke arguments")
    if not ok:
        raise RuntimeError(f"Failed to invoke {method} on Qt thread")


def create_app(bridge: HeadlessBridge, hub: EventHub) -> FastAPI:
    app = FastAPI(title="Auto Video Encoder")

    @app.on_event("startup")
    async def _startup():
        hub.set_loop(asyncio.get_running_loop())
        bridge.register_event_callback(hub.broadcast_from_thread)

    @app.get("/api/metadata")
    def get_metadata():
        from ui.resources import (
            ABR_PRESETS,
            ALL_ENCODERS,
            ANAMORPHIC_MODES,
            AUDIO_ENCODERS,
            COLOR_MATRICES,
            COLOR_RANGES,
            COLORSPACE_PRESETS,
            COMB_DETECT_MODES,
            CONTAINER_FORMATS,
            CRF_PRESETS,
            CROP_MODES,
            DEBLOCK_STRENGTHS,
            DEBLOCK_TUNES,
            DEINTERLACE_TYPES,
            DENOISE_STRENGTHS,
            DENOISE_TYPES,
            FRAMERATES,
            HDR_METADATA_OPTIONS,
            HW_DECODING_OPTIONS,
            MIXDOWNS,
            NLMEANS_TUNES,
            SAMPLE_RATES,
            SHARPEN_STRENGTHS,
            SHARPEN_TYPES,
            SIMPLE_ENCODERS,
            VIDEO_EXTENSIONS,
        )
        from tools import handbrake_available_for_download

        return {
            "abr_presets": ABR_PRESETS,
            "crf_presets": CRF_PRESETS,
            "simple_encoders": [{"label": l, "value": v} for l, v in SIMPLE_ENCODERS],
            "all_encoders": ALL_ENCODERS,
            "audio_encoders": AUDIO_ENCODERS,
            "mixdowns": MIXDOWNS,
            "sample_rates": SAMPLE_RATES,
            "framerates": FRAMERATES,
            "anamorphic_modes": [m.lower() for m in ANAMORPHIC_MODES],
            "crop_modes": [c.lower() for c in CROP_MODES],
            "color_ranges": [c.lower() for c in COLOR_RANGES],
            "color_matrices": [""] + [cm for cm in COLOR_MATRICES if cm != "Auto"],
            "denoise_types": [d.lower() for d in DENOISE_TYPES],
            "denoise_strengths": [""] + DENOISE_STRENGTHS,
            "nlmeans_tunes": [""] + NLMEANS_TUNES,
            "sharpen_types": [s.lower() for s in SHARPEN_TYPES],
            "sharpen_strengths": [""] + SHARPEN_STRENGTHS,
            "deblock_strengths": [d.lower() for d in DEBLOCK_STRENGTHS],
            "deblock_tunes": [""] + DEBLOCK_TUNES,
            "deinterlace_types": [d.lower() for d in DEINTERLACE_TYPES],
            "comb_detect_modes": [c.lower() for c in COMB_DETECT_MODES],
            "colorspace_presets": [c.lower() for c in COLORSPACE_PRESETS],
            "container_formats": [c.lower() for c in CONTAINER_FORMATS],
            "hdr_metadata_options": [o.lower() for o in HDR_METADATA_OPTIONS],
            "hw_decoding_options": [o.lower() for o in HW_DECODING_OPTIONS],
            "chroma_smooth_strengths": ["off"] + SHARPEN_STRENGTHS,
            "video_extensions_default": VIDEO_EXTENSIONS,
            "handbrake_downloadable": handbrake_available_for_download(),
        }

    @app.get("/api/config")
    def get_config():
        from copy import deepcopy
        return deepcopy(bridge.config.data)

    @app.put("/api/config")
    def put_config(body: dict[str, Any]):
        try:
            merged = _deep_merge(_base_defaults(), body)
            _invoke_qt(bridge, "apply_config", merged)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @app.get("/api/tools/status")
    def tools_status():
        return bridge.get_tools_status()

    @app.delete("/api/processed-history")
    def clear_processed_history(source: str = ""):
        payload = {"source": source} if source else {}
        try:
            _invoke_qt(bridge, "clear_processed_history", payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/tools/download")
    def tools_download(body: dict[str, str]):
        tool = body.get("tool", "")
        if tool not in ("handbrake", "ffprobe"):
            raise HTTPException(status_code=400, detail="tool must be 'handbrake' or 'ffprobe'")
        try:
            _invoke_qt(bridge, "download_tool", tool)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True}

    @app.post("/api/engine/start")
    def engine_start():
        if bridge.is_running:
            raise HTTPException(status_code=409, detail="Encoder is already running")
        _invoke_qt(bridge, "start_engine")
        return {"ok": True}

    @app.post("/api/engine/stop")
    def engine_stop():
        if not bridge.is_running:
            return {"ok": True}
        _invoke_qt(bridge, "stop_engine")
        return {"ok": True}

    @app.get("/api/engine/status")
    def engine_status():
        return bridge.get_status_snapshot()

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        await hub.add(ws)
        try:
            await ws.send_json({"type": "snapshot", **bridge.get_status_snapshot()})
            while True:
                await asyncio.sleep(3600)
        except WebSocketDisconnect:
            pass
        finally:
            await hub.remove(ws)

    static_dir = get_static_dir()
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    return app


def start_web_server(bridge: HeadlessBridge, host: str, port: int) -> tuple[EventHub, threading.Thread]:
    import uvicorn

    hub = EventHub()
    app = create_app(bridge, hub)

    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="web-ui")
    thread.start()
    return hub, thread

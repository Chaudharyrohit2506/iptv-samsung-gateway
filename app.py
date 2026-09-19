import os, time, uuid, subprocess
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

SERVER = os.getenv("XTREAM_SERVER", "http://desyra.co:8080").rstrip("/")
USERNAME = os.getenv("XTREAM_USERNAME", "")
PASSWORD = os.getenv("XTREAM_PASSWORD", "")
GATEWAY_KEY = os.getenv("GATEWAY_KEY", "")
PUBLIC_BASE = os.getenv("PUBLIC_BASE", "").rstrip("/")
HLS_ROOT = Path(os.getenv("HLS_ROOT", "/tmp/iptv_hls"))
HLS_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Xtream Samsung Playback Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

def check_key(key: str | None):
    if GATEWAY_KEY and key != GATEWAY_KEY:
        raise HTTPException(401, "Invalid gateway key")

def xtream_url(action: str = "", category_id: str | None = None, series_id: str | None = None):
    params = {"username": USERNAME, "password": PASSWORD}
    if action:
        params["action"] = action
    if category_id:
        params["category_id"] = category_id
    if series_id:
        params["series_id"] = series_id
    return SERVER + "/player_api.php?" + urlencode(params)

def get_json(url: str):
    req = Request(url, headers={"User-Agent": "IPTV-Gateway/1.0", "Accept": "application/json,*/*"})
    try:
        with urlopen(req, timeout=25) as r:
            status = getattr(r, "status", 200)
            body = r.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Xtream HTTP error: status={e.code}, body={body[:300]!r}")
        raise HTTPException(502, f"Xtream server returned HTTP {e.code}")
    except URLError as e:
        print(f"Xtream connection error: {e}")
        raise HTTPException(502, "Could not connect to Xtream server")
    except Exception as e:
        print(f"Xtream request error: {type(e).__name__}: {e}")
        raise HTTPException(502, "Xtream request failed")

    if status < 200 or status >= 300:
        print(f"Xtream unexpected status: {status}, body={body[:300]!r}")
        raise HTTPException(502, f"Xtream server returned HTTP {status}")

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        print(f"Xtream non-JSON response: {body[:500]!r}")
        raise HTTPException(
            502,
            "Xtream server returned a non-JSON response. Check the Render logs for the upstream response."
        )

@app.get("/health")
def health():
    return {
        "ok": True,
        "xtream_server": SERVER,
        "configured": bool(USERNAME and PASSWORD),
        "has_username": bool(USERNAME),
        "has_password": bool(PASSWORD),
        "username_length": len(USERNAME),
        "password_length": len(PASSWORD),
        "has_gateway_key": bool(GATEWAY_KEY),
    }

@app.get("/api/catalog")
def catalog(kind: str = Query("live"), category_id: str | None = None, key: str | None = None):
    check_key(key)
    actions = {
        "live": "get_live_streams",
        "live_categories": "get_live_categories",
        "vod": "get_vod_streams",
        "vod_categories": "get_vod_categories",
        "series": "get_series",
        "series_categories": "get_series_categories",
    }
    if kind not in actions:
        raise HTTPException(400, "Unsupported catalog kind")
    return JSONResponse(get_json(xtream_url(actions[kind], category_id=category_id)))

@app.get("/api/series/{series_id}")
def series_info(series_id: str, key: str | None = None):
    check_key(key)
    return JSONResponse(get_json(xtream_url("get_series_info", series_id=series_id)))

def source_url(kind: str, stream_id: str, ext: str):
    if kind == "live":
        return f"{SERVER}/live/{USERNAME}/{PASSWORD}/{stream_id}.ts"
    if kind == "vod":
        return f"{SERVER}/movie/{USERNAME}/{PASSWORD}/{stream_id}.{ext}"
    if kind == "series":
        return f"{SERVER}/series/{USERNAME}/{PASSWORD}/{stream_id}.{ext}"
    raise HTTPException(400, "Unsupported stream type")

def start_hls(kind: str, stream_id: str, ext: str = "ts"):
    job = uuid.uuid4().hex
    out = HLS_ROOT / job
    out.mkdir(parents=True, exist_ok=True)
    src = source_url(kind, stream_id, ext)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", src,
        "-map", "0:v:0?", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "6",
        "-hls_flags", "delete_segments+append_list",
        "-hls_segment_filename", str(out / "seg_%05d.ts"),
        str(out / "index.m3u8"),
    ]
    p = subprocess.Popen(cmd)
    (out / "pid").write_text(str(p.pid))
    (out / "created").write_text(str(time.time()))
    return job

@app.get("/api/play")
def play(kind: str, stream_id: str, ext: str = "ts", key: str | None = None):
    check_key(key)
    if kind not in {"live", "vod", "series"}:
        raise HTTPException(400, "kind must be live, vod or series")
    job = start_hls(kind, stream_id, ext)
    base = PUBLIC_BASE or ""
    return {"job": job, "hls": f"{base}/hls/{job}/index.m3u8"}

@app.get("/hls/{job}/{file_name}")
def hls(job: str, file_name: str):
    if "/" in job or "/" in file_name or "\\" in job or "\\" in file_name:
        raise HTTPException(400, "Invalid path")
    root = HLS_ROOT / job
    path = root / file_name
    if not path.exists():
        raise HTTPException(404, "Segment not ready")
    media = "application/vnd.apple.mpegurl" if file_name.endswith(".m3u8") else "video/mp2t"
    return FileResponse(path, media_type=media)

@app.get("/")
def root():
    return PlainTextResponse("Xtream Samsung Playback Gateway is running.")

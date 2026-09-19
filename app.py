import os, time, uuid, shutil, subprocess, threading
from pathlib import Path
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
    q = f"?username={USERNAME}&password={PASSWORD}"
    if action:
        q += f"&action={action}"
    if category_id:
        q += f"&category_id={category_id}"
    if series_id:
        q += f"&series_id={series_id}"
    return SERVER + "/player_api.php" + q

def get_json(url: str):
    import urllib.request, json
    req = urllib.request.Request(url, headers={"User-Agent": "IPTV-Gateway/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))

@app.get("/health")
def health():
    return {"ok": True, "xtream_server": SERVER, "configured": bool(USERNAME and PASSWORD)}

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

    # Browser-friendly H.264/AAC HLS. This is intentionally transcoded because
    # the user's Samsung browser could not decode the provider stream directly.
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
    # Only serve files inside the generated job directory.
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

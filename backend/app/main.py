import os
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Optional
import qrcode
from io import BytesIO

from fastapi import FastAPI, Depends, File, UploadFile, HTTPException, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

import datetime
from app.config import settings
from app import supabase_client
from app.schemas import (
    StatsResponse, EventCreate, EventResponse, PhotoResponse,
    AdminLoginRequest, SettingsResponse, SettingsUpdate
)
from app.watcher import folder_watcher
from app.camera import camera_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database schema managed in Supabase

# Keep track of active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Remaining connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to connection: {e}")

manager = ConnectionManager()
main_loop = None

def get_photo_urls(photo_id: str, request_url: str) -> tuple[str, str]:
    """Helper to resolve download and qrcode URLs relative to the current public URL or base request URL."""
    base = settings.PUBLIC_URL if settings.PUBLIC_URL and settings.PUBLIC_URL != "http://localhost:8000" else request_url
    base = base.rstrip('/')
    return f"{base}/download/{photo_id}", f"{base}/api/photos/{photo_id}/qrcode"

def broadcast_new_photo(photo):
    """Callback triggered by FolderWatcher or CameraManager from a background thread.
    Uses asyncio.run_coroutine_threadsafe to push to the main async event loop.
    """
    if not main_loop:
        logger.warning("Event loop not initialized yet. Skipping broadcast.")
        return

    # Create dummy request url fallback
    base_url = settings.PUBLIC_URL
    dl_url, qr_url = get_photo_urls(photo.id, base_url)
    
    photo_data = {
        "event": "new_photo",
        "data": {
            "id": photo.id,
            "filename": photo.filename,
            "original_name": photo.original_name,
            "created_at": photo.created_at.isoformat(),
            "event_id": photo.event_id,
            "download_url": dl_url,
            "qrcode_url": qr_url
        }
    }
    
    logger.info(f"Broadcasting new photo: {photo.id}")
    asyncio.run_coroutine_threadsafe(manager.broadcast(photo_data), main_loop)

def check_admin(authorization: Optional[str] = Header(None)):
    """Simple passcode validation."""
    token = authorization
    if token and token.startswith("Bearer "):
        token = token[7:]
    
    if not token or token != settings.ADMIN_PASSCODE:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid admin passcode.")
    return True

# Server Startup
@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    # Auto-initialize default active event if none exists in Supabase
    try:
        active_event = supabase_client.get_active_event()
        if not active_event:
            supabase_client.create_event("My First Vixora Event")
            logger.info("Initialized default active event in Supabase.")
    except Exception as e:
        logger.error(f"Failed to auto-initialize default active event: {e}")

    # Start services depending on configured capture mode
    start_capture_services()

def start_capture_services():
    """Starts either the folder watcher or HDMI camera depending on the active setting."""
    if settings.CAPTURE_MODE == "watcher":
        logger.info(f"Startup: Starting Folder Watcher on {settings.WATCH_DIR}")
        folder_watcher.start(settings.WATCH_DIR, broadcast_new_photo)
        camera_manager.stop()
    elif settings.CAPTURE_MODE == "hdmi":
        logger.info(f"Startup: Starting HDMI Camera on Index {settings.CAMERA_INDEX}")
        camera_manager.start(settings.CAMERA_INDEX, broadcast_new_photo)
        folder_watcher.stop()
    else:
        logger.warning(f"Unknown capture mode: {settings.CAPTURE_MODE}")

# Server Shutdown
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Server shutting down. Stopping all background services...")
    folder_watcher.stop()
    camera_manager.stop()

# ==================== ADMIN API ENDPOINTS ====================

@app.post("/api/admin/login")
def admin_login(payload: AdminLoginRequest):
    if payload.passcode == settings.ADMIN_PASSCODE:
        return {"token": settings.ADMIN_PASSCODE, "message": "Login successful"}
    raise HTTPException(status_code=401, detail="Invalid admin passcode.")

@app.get("/api/admin/stats", response_model=StatsResponse)
def get_stats(authenticated: bool = Depends(check_admin)):
    stats = supabase_client.get_stats()
    return stats

@app.get("/api/admin/settings", response_model=SettingsResponse)
def get_admin_settings(authenticated: bool = Depends(check_admin)):
    return {
        "capture_mode": settings.CAPTURE_MODE,
        "camera_index": settings.CAMERA_INDEX,
        "watch_dir": str(settings.WATCH_DIR),
        "public_url": settings.PUBLIC_URL,
        "passcode_preview": "••••" if settings.ADMIN_PASSCODE else "None"
    }

@app.put("/api/admin/settings", response_model=SettingsResponse)
def update_admin_settings(payload: SettingsUpdate, authenticated: bool = Depends(check_admin)):
    if payload.capture_mode is not None:
        settings.CAPTURE_MODE = payload.capture_mode
    if payload.camera_index is not None:
        settings.CAMERA_INDEX = payload.camera_index
    if payload.watch_dir is not None:
        settings.WATCH_DIR = Path(payload.watch_dir)
        settings.WATCH_DIR.mkdir(parents=True, exist_ok=True)
    if payload.public_url is not None:
        settings.PUBLIC_URL = payload.public_url.rstrip('/')

    logger.info("Settings updated. Restarting capture services...")
    start_capture_services()

    return {
        "capture_mode": settings.CAPTURE_MODE,
        "camera_index": settings.CAMERA_INDEX,
        "watch_dir": str(settings.WATCH_DIR),
        "public_url": settings.PUBLIC_URL,
        "passcode_preview": "••••" if settings.ADMIN_PASSCODE else "None"
    }

@app.post("/api/admin/event", response_model=EventResponse)
def create_event(payload: EventCreate, authenticated: bool = Depends(check_admin)):
    new_event = supabase_client.create_event(payload.name)
    
    # Restart services so new captures map to the new event
    start_capture_services()
    
    # Notify connected displays that event changed
    asyncio.run_coroutine_threadsafe(
        manager.broadcast({"event": "event_changed", "data": {"name": new_event["name"]}}),
        main_loop
    )

    created_at_dt = datetime.datetime.utcnow()
    if "created_at" in new_event:
        try:
            created_at_dt = datetime.datetime.fromisoformat(new_event["created_at"].replace('Z', '+00:00'))
        except Exception:
            pass

    return {
        "id": new_event["id"],
        "name": new_event["name"],
        "created_at": created_at_dt,
        "is_active": new_event["is_active"],
        "photos_count": 0
    }

@app.get("/api/admin/photos", response_model=List[PhotoResponse])
def get_event_photos(request: Request, authenticated: bool = Depends(check_admin)):
    photos = supabase_client.get_event_photos()
    
    response = []
    base_request_url = str(request.base_url)
    
    for photo in photos:
        # Check if the photo is deleted from local disk (on the admin computer)
        file_path = settings.PHOTOS_DIR / photo["filename"]
        if not file_path.exists():
            # Delete from Supabase
            supabase_client.delete_photo(photo["id"])
            supabase_client.delete_file(photo["filename"])
            filename_path = Path(photo["filename"])
            thumb_filename = f"{filename_path.stem}_thumb.jpg"
            supabase_client.delete_file(thumb_filename)
            continue
            
        dl_url, qr_url = get_photo_urls(photo["id"], base_request_url)
        
        created_at_dt = datetime.datetime.utcnow()
        if "created_at" in photo:
            try:
                created_at_dt = datetime.datetime.fromisoformat(photo["created_at"].replace('Z', '+00:00'))
            except Exception:
                pass
                
        response.append({
            "id": photo["id"],
            "filename": photo["filename"],
            "original_name": photo.get("original_name", ""),
            "created_at": created_at_dt,
            "event_id": photo["event_id"],
            "download_url": dl_url,
            "qrcode_url": qr_url
        })
        
    return response

@app.post("/api/admin/wipe")
def wipe_all_data(authenticated: bool = Depends(check_admin)):
    """Wipes all photos from Supabase database and storage, and deletes local photo files from disk."""
    logger.info("Wiping all session data...")
    
    # Stop capture services temporarily
    folder_watcher.stop()
    camera_manager.stop()
    
    try:
        # 1. Clean Supabase database and storage
        supabase_client.wipe_all_data()
        
        # 2. Delete files from local photos folder
        if settings.PHOTOS_DIR.exists():
            for file in settings.PHOTOS_DIR.iterdir():
                if file.is_file():
                    try:
                        file.unlink()
                    except Exception as e:
                        logger.error(f"Failed to delete file {file}: {e}")
                        
        # 3. Delete files from local watch folder
        if settings.WATCH_DIR.exists():
            for file in settings.WATCH_DIR.iterdir():
                if file.is_file() and file.suffix.lower() in ('.jpg', '.jpeg', '.png'):
                    try:
                        file.unlink()
                    except Exception as e:
                        logger.error(f"Failed to delete watch file {file}: {e}")
        
        logger.info("Wipe complete. Restarting services.")
        start_capture_services()
        
        # Broadcast to displays to clear current photo
        asyncio.run_coroutine_threadsafe(
            manager.broadcast({"event": "wiped", "data": {}}),
            main_loop
        )
        
        return {"message": "All Supabase records, storage bucket files, and local photo files successfully wiped."}
    except Exception as e:
        start_capture_services()
        raise HTTPException(status_code=500, detail=f"Failed to wipe data: {e}")

# ==================== CAMERA MJPEG & MANUAL CAPTURE ====================

def gen_live_stream_frames():
    """Generator for streaming live MJPEG frames from the camera manager."""
    while True:
        frame_bytes = camera_manager.get_current_frame_jpeg()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        # Sleep briefly to set streaming rate around 20-30 FPS
        time.sleep(0.04)

@app.get("/api/camera/stream")
def get_camera_stream(authenticated: bool = Depends(check_admin)):
    """Exposes live camera preview as MJPEG stream."""
    if settings.CAPTURE_MODE != "hdmi":
        raise HTTPException(status_code=400, detail="Camera stream only available in HDMI Mode.")
    return StreamingResponse(
        gen_live_stream_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.post("/api/camera/capture", response_model=PhotoResponse)
def trigger_manual_capture(request: Request, authenticated: bool = Depends(check_admin)):
    """Triggers manual snapshot from the HDMI stream."""
    if settings.CAPTURE_MODE != "hdmi":
        raise HTTPException(status_code=400, detail="Manual capture only available in HDMI Mode.")
    
    try:
        photo = camera_manager.capture_photo()
        dl_url, qr_url = get_photo_urls(photo.id, str(request.base_url))
        return {
            "id": photo.id,
            "filename": photo.filename,
            "original_name": photo.original_name,
            "created_at": photo.created_at,
            "event_id": photo.event_id,
            "download_url": dl_url,
            "qrcode_url": qr_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture frame: {e}")

# ==================== PUBLIC / GUEST ENDPOINTS ====================

@app.get("/api/photos/{photo_id}/image")
def get_photo_image(photo_id: str):
    """Serves the raw photo image file, redirecting to Supabase if missing from local disk."""
    try:
        res = supabase_client._request(f"/rest/v1/photos?id=eq.{photo_id}&select=*")
        if not res or not isinstance(res, list) or len(res) == 0:
            raise HTTPException(status_code=404, detail="Photo not found")
        photo = res[0]
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Photo not found in Supabase: {e}")

    file_path = settings.PHOTOS_DIR / photo["filename"]
    if file_path.exists():
        return FileResponse(str(file_path), media_type="image/jpeg", filename=photo.get("original_name") or photo["filename"])
        
    # Redirect to Supabase Storage public CDN
    supabase_url = settings.SUPABASE_URL.rstrip('/')
    public_url = f"{supabase_url}/storage/v1/object/public/photos/{photo['filename']}"
    return RedirectResponse(public_url)

@app.get("/api/photos/{photo_id}/thumbnail")
def get_photo_thumbnail(photo_id: str):
    """Serves the compressed thumbnail image file, falling back to the high-res image if missing."""
    try:
        res = supabase_client._request(f"/rest/v1/photos?id=eq.{photo_id}&select=*")
        if not res or not isinstance(res, list) or len(res) == 0:
            raise HTTPException(status_code=404, detail="Photo not found")
        photo = res[0]
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Photo not found in Supabase: {e}")

    filename_path = Path(photo["filename"])
    thumb_filename = f"{filename_path.stem}_thumb.jpg"
    thumb_path = settings.PHOTOS_DIR / thumb_filename
    
    if thumb_path.exists():
        return FileResponse(str(thumb_path), media_type="image/jpeg", filename=thumb_filename)
        
    # Fallback to local high-res
    file_path = settings.PHOTOS_DIR / photo["filename"]
    if file_path.exists():
        return FileResponse(str(file_path), media_type="image/jpeg", filename=photo.get("original_name") or photo["filename"])
        
    # Redirect to Supabase Storage public CDN for thumbnail
    supabase_url = settings.SUPABASE_URL.rstrip('/')
    public_url = f"{supabase_url}/storage/v1/object/public/photos/{thumb_filename}"
    return RedirectResponse(public_url)

@app.get("/api/photos/{photo_id}/qrcode")
def get_photo_qrcode(photo_id: str, request: Request, public_url: Optional[str] = None):
    """Generates the QR code pointing to the download URL dynamically in-memory."""
    try:
        res = supabase_client._request(f"/rest/v1/photos?id=eq.{photo_id}&select=id")
        if not res or not isinstance(res, list) or len(res) == 0:
            raise HTTPException(status_code=404, detail="Photo not found")
        photo = res[0]
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Photo not found in Supabase: {e}")

    # Generate public link
    if public_url:
        download_url = f"{public_url.rstrip('/')}/download/{photo['id']}"
    else:
        download_url, _ = get_photo_urls(photo['id'], str(request.base_url))
    
    # Generate QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(download_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save image to BytesIO buffer
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return Response(content=buf.getvalue(), media_type="image/png")

# ==================== WEBSOCKET INTERFACES ====================
@app.websocket("/api/ws/display")
async def websocket_display_endpoint(websocket: WebSocket):
    """Slideshow/TV display websocket connection."""
    await manager.connect(websocket)
    
    try:
        active_event = supabase_client.get_active_event()
        if active_event:
            latest_photos = supabase_client.get_event_photos()
            photos_data = []
            for photo in latest_photos:
                file_path = settings.PHOTOS_DIR / photo["filename"]
                if not file_path.exists():
                    # Delete from Supabase
                    supabase_client.delete_photo(photo["id"])
                    supabase_client.delete_file(photo["filename"])
                    filename_path = Path(photo["filename"])
                    thumb_filename = f"{filename_path.stem}_thumb.jpg"
                    supabase_client.delete_file(thumb_filename)
                    continue
                    
                dl_url, qr_url = get_photo_urls(photo["id"], str(websocket.base_url))
                photos_data.append({
                    "id": photo["id"],
                    "filename": photo["filename"],
                    "original_name": photo.get("original_name", ""),
                    "created_at": photo.get("created_at", ""),
                    "event_id": photo["event_id"],
                    "download_url": dl_url,
                    "qrcode_url": qr_url
                })
            
            await websocket.send_json({
                "event": "init",
                "data": photos_data
            })
    except Exception as e:
        logger.error(f"Error in websocket initialization: {e}")

    try:
        while True:
            # Keep connection alive, listen for any messages (none expected from display)
            data = await websocket.receive_text()
            logger.info(f"WS Display received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WS Display exception: {e}")
        manager.disconnect(websocket)

# ==================== STATIC FRONTEND SERVING & ROUTING ====================

@app.get("/download/{photo_id}")
async def serve_download_page(photo_id: str):
    """Serves the index.html fallback for /download/{photo_id} so the guest gets the React SPA frontend."""
    index_path = Path(settings.STATIC_DIR) / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {
        "message": f"Download photo ID: {photo_id}",
        "frontend_status": f"Frontend static build not found at: {settings.STATIC_DIR}. Please build the frontend."
    }

@app.get("/")
async def serve_index():
    index_path = Path(settings.STATIC_DIR) / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {
        "message": "VIXORA V2 Camera Server API is running.",
        "frontend_status": f"Frontend static build not found at: {settings.STATIC_DIR}. Please build the frontend."
    }

@app.get("/{catchall:path}")
async def serve_frontend(catchall: str):
    if catchall.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
        
    index_path = Path(settings.STATIC_DIR) / "index.html"
    file_path = Path(settings.STATIC_DIR) / catchall
    
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
        
    if index_path.exists():
        return FileResponse(index_path)
        
    return {
        "message": "VIXORA V2 Camera Server API is running.",
        "frontend_status": f"Frontend static build not found at: {settings.STATIC_DIR}. Please build the frontend."
    }

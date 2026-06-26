import os
import cv2
import time
import threading
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import io

from app.config import settings
import uuid
import datetime
from app import supabase_client

class MockPhoto:
    def __init__(self, data):
        self.id = data["id"]
        self.filename = data["filename"]
        self.original_name = data.get("original_name", "")
        self.created_at = datetime.datetime.fromisoformat(data["created_at"].replace('Z', '+00:00')) if "created_at" in data else datetime.datetime.utcnow()
        self.event_id = data["event_id"]

logger = logging.getLogger("camera")

class CameraManager:
    def __init__(self):
        self.cap = None
        self.camera_index = None
        self.frame = None
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()
        self.callback_func = None

    def start(self, camera_index: int, callback_func=None):
        with self.lock:
            if self.is_running and self.camera_index == camera_index:
                logger.info(f"Camera {camera_index} is already running.")
                return
            
            # Stop if running on another index
            self._stop_internal()
            
            self.camera_index = camera_index
            self.callback_func = callback_func
            self.is_running = True
            
            # Start background thread to read frames
            self.thread = threading.Thread(target=self._read_frames_loop, daemon=True)
            self.thread.start()
            logger.info(f"Background stream thread started for camera index {camera_index}")

    def stop(self):
        with self.lock:
            self._stop_internal()

    def _stop_internal(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None
        if self.cap:
            logger.info("Releasing camera capture device...")
            self.cap.release()
            self.cap = None
        self.frame = None

    def _read_frames_loop(self):
        """Threaded loop to read frames from cv2.VideoCapture continuously.
        This prevents the hardware buffer from building up lag.
        """
        logger.info(f"Initializing VideoCapture({self.camera_index})...")
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
        
        # Try to set high capture resolution (1080p or 4K)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        
        retry_delay = 2.0
        
        while self.is_running:
            if not self.cap or not self.cap.isOpened():
                logger.warning(f"Camera index {self.camera_index} is not open. Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
                continue

            ret, frame = self.cap.read()
            if not ret or frame is None:
                logger.warning("Failed to read frame from camera. Reconnecting...")
                self.cap.release()
                time.sleep(1.0)
                continue

            with self.lock:
                self.frame = frame.copy()
            
            # Sleep slightly to prevent high CPU utilization
            time.sleep(0.01)

    def get_current_frame_jpeg(self) -> bytes:
        """Returns the current frame encoded as JPEG bytes."""
        with self.lock:
            frame = self.frame
            
        if frame is not None:
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            if ret:
                return buffer.tobytes()
        
        # Fallback placeholder image when camera is not connected / frame is empty
        return self._generate_placeholder_frame("NO CAMERA CONNECTED")

    def _generate_placeholder_frame(self, text: str) -> bytes:
        """Generates a black image with text using Pillow as a fallback."""
        img = Image.new('RGB', (640, 480), color=(18, 18, 24))
        draw = ImageDraw.Draw(img)
        # Draw a simple box and crosshair for visual feedback
        draw.rectangle([20, 20, 620, 460], outline=(40, 40, 50), width=2)
        draw.line([320, 200, 320, 280], fill=(60, 60, 70), width=1)
        draw.line([280, 240, 360, 240], fill=(60, 60, 70), width=1)
        
        # Simple text drawing
        draw.text((320, 240), text, fill=(150, 150, 160), anchor="mm")
        
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80)
        return buf.getvalue()

    def capture_photo(self):
        """Captures the current frame from the camera stream, saves it locally and uploads/registers in Supabase."""
        with self.lock:
            frame = self.frame
            
        if frame is None:
            raise RuntimeError("Camera has no active frame. Is it connected and turned on?")
            
        try:
            # 1. Get active event from Supabase
            active_event = supabase_client.get_active_event()
            if not active_event:
                active_event = supabase_client.create_event("My First Vixora Event")
                logger.info("No active event found. Created default event in Supabase.")

            # 2. Generate unique name
            photo_uuid = str(uuid.uuid4())
            photo_id = f"cap_{photo_uuid[:8]}"
            dest_filename = f"{photo_id}.jpg"
            dest_path = settings.PHOTOS_DIR / dest_filename
            
            # 3. Save frame high resolution
            # Use quality=85 (highly optimized, target size 1-2 MB)
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ret:
                raise RuntimeError("Failed to encode frame to JPEG.")
                
            high_res_bytes = buffer.tobytes()
            with open(dest_path, 'wb') as f:
                f.write(high_res_bytes)

            # Generate and save compressed thumbnail (max 800px boundary, quality 65, target ~100KB)
            thumb_bytes = None
            thumb_filename = f"{photo_id}_thumb.jpg"
            try:
                max_thumb_size = 800
                height, width = frame.shape[:2]
                if width > max_thumb_size or height > max_thumb_size:
                    if width > height:
                        thumb_w = max_thumb_size
                        thumb_h = int(height * (max_thumb_size / width))
                    else:
                        thumb_h = max_thumb_size
                        thumb_w = int(width * (max_thumb_size / height))
                    thumb_frame = cv2.resize(frame, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
                else:
                    thumb_frame = frame.copy()
                
                ret_thumb, buffer_thumb = cv2.imencode('.jpg', thumb_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
                if ret_thumb:
                    thumb_bytes = buffer_thumb.tobytes()
                    thumb_path = settings.PHOTOS_DIR / thumb_filename
                    with open(thumb_path, 'wb') as f:
                        f.write(thumb_bytes)
                    logger.info(f"Compressed and saved new thumbnail photo: {thumb_filename}")
            except Exception as thumb_err:
                logger.error(f"Thumbnail generation failed in camera: {thumb_err}")

            # 4. Upload to Supabase Storage
            logger.info(f"Uploading captured photo to Supabase Storage: {dest_filename}")
            supabase_client.upload_file(dest_filename, high_res_bytes)
            
            if thumb_bytes:
                logger.info(f"Uploading captured thumbnail to Supabase Storage: {thumb_filename}")
                supabase_client.upload_file(thumb_filename, thumb_bytes)
            else:
                logger.warning("No thumbnail bytes generated, uploading high-res as thumbnail fallback...")
                supabase_client.upload_file(thumb_filename, high_res_bytes)

            # 5. Insert into Supabase database
            new_photo_data = supabase_client.insert_photo(
                photo_id=photo_uuid,
                filename=dest_filename,
                original_name="HDMI_Capture.jpg",
                event_id=active_event["id"]
            )
            
            new_photo = MockPhoto(new_photo_data)
            logger.info(f"Captured and registered photo from HDMI stream: {dest_filename}")
            
            # 6. Trigger callback for WS clients
            if self.callback_func:
                self.callback_func(new_photo)
                
            return new_photo
        except Exception as e:
            logger.error(f"Error in HDMI stream capture: {e}")
            raise e

# Global instance
camera_manager = CameraManager()

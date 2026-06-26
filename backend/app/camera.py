import os
import cv2
import time
import threading
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import io

from app.config import settings
from app.database import SessionLocal
from app.models import Event, Photo

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

    def capture_photo(self) -> Photo:
        """Captures the current frame from the camera stream, saves it to disk and registers it in the DB."""
        with self.lock:
            frame = self.frame
            
        if frame is None:
            raise RuntimeError("Camera has no active frame. Is it connected and turned on?")
            
        db = SessionLocal()
        try:
            # 1. Get active event
            active_event = db.query(Event).filter(Event.is_active == True).order_by(Event.id.desc()).first()
            if not active_event:
                active_event = Event(name="Default Event")
                db.add(active_event)
                db.commit()
                db.refresh(active_event)

            # 2. Generate unique name
            photo_id = "cap_" + str(int(time.time())) + "_" + str(threading.get_ident())
            dest_filename = f"{photo_id}.jpg"
            dest_path = settings.PHOTOS_DIR / dest_filename
            
            # 3. Save frame high resolution
            # Use quality=85 (highly optimized, target size 1-2 MB)
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ret:
                raise RuntimeError("Failed to encode frame to JPEG.")
                
            with open(dest_path, 'wb') as f:
                f.write(buffer.tobytes())

            # Generate and save compressed thumbnail (max 800px boundary, quality 65, target ~100KB)
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
                    thumb_filename = f"{photo_id}_thumb.jpg"
                    thumb_path = settings.PHOTOS_DIR / thumb_filename
                    with open(thumb_path, 'wb') as f:
                        f.write(buffer_thumb.tobytes())
                    logger.info(f"Compressed and saved new thumbnail photo: {thumb_filename}")
            except Exception as thumb_err:
                logger.error(f"Thumbnail generation failed in camera: {thumb_err}")

            # 4. Insert into database
            new_photo = Photo(
                id=photo_id,
                filename=dest_filename,
                original_name="HDMI_Capture.jpg",
                event_id=active_event.id
            )
            db.add(new_photo)
            db.commit()
            db.refresh(new_photo)
            
            logger.info(f"Captured photo from HDMI stream: {dest_filename}")
            
            # 5. Trigger callback for WS clients
            if self.callback_func:
                self.callback_func(new_photo)
                
            return new_photo
        except Exception as e:
            logger.error(f"Error in HDMI stream capture: {e}")
            db.rollback()
            raise e
        finally:
            db.close()

# Global instance
camera_manager = CameraManager()

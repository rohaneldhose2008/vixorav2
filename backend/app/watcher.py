import os
import time
import shutil
import logging
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image

from app.config import settings

logger = logging.getLogger("watcher")

class NewPhotoHandler(FileSystemEventHandler):
    def __init__(self, callback_func):
        super().__init__()
        self.callback_func = callback_func
        self.processed_files = set()
        self.lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        # Check if the file is an image
        if file_path.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
            return

        filename = file_path.name
        with self.lock:
            if filename in self.processed_files:
                logger.info(f"File {filename} already processed or scheduled. Skipping duplicate event.")
                return
            self.processed_files.add(filename)

        logger.info(f"New file detected in watch folder: {file_path}")
        # Run processing in a safe way
        self.process_file_with_retry(file_path)

    def process_file_with_retry(self, file_path: Path):
        """Tethering software can take a brief moment to write the full image.
        We retry opening the image file until it is fully written and unlocked.
        """
        max_retries = 10
        delay = 0.5
        
        for attempt in range(max_retries):
            try:
                time.sleep(delay)
                # Check if file size is stable
                initial_size = file_path.stat().st_size
                time.sleep(0.2)
                current_size = file_path.stat().st_size
                
                if initial_size != current_size or current_size == 0:
                    continue # file is still being written
                
                # Try opening it to verify it's a valid, uncorrupted image
                with Image.open(file_path) as img:
                    img.verify()
                
                # File is ready
                logger.info(f"File {file_path.name} is fully written. Processing...")
                self.callback_func(file_path)
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} to open {file_path.name} failed: {e}")
                
        logger.error(f"Failed to process file {file_path} after {max_retries} retries.")

class FolderWatcher:
    def __init__(self):
        self.observer = None
        self.watch_dir = None
        self.callback_func = None
        self.is_running = False

    def start(self, watch_dir: Path, callback_func):
        self.watch_dir = Path(watch_dir)
        self.callback_func = callback_func
        
        # Ensure watch dir exists
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        
        # Stop existing observer if running
        self.stop()
        
        logger.info(f"Starting Folder Watcher on: {self.watch_dir}")
        event_handler = NewPhotoHandler(self._handle_new_photo)
        self.observer = Observer()
        self.observer.schedule(event_handler, path=str(self.watch_dir), recursive=False)
        self.observer.start()
        self.is_running = True

    def stop(self):
        if self.observer:
            logger.info("Stopping Folder Watcher...")
            self.observer.stop()
            self.observer.join()
            self.observer = None
        self.is_running = False

    def _handle_new_photo(self, src_path: Path):
        """Copies/compresses the photo and uploads it to Supabase database and storage."""
        import uuid
        import io
        import urllib.parse
        from app import supabase_client
        
        try:
            # 1. Get active event from Supabase
            active_event = supabase_client.get_active_event()
            if not active_event:
                # If no active event exists, create a default one in Supabase
                active_event = supabase_client.create_event("My First Vixora Event")
                logger.info("No active event found. Created default event in Supabase.")

            # 2. Check for duplicate to avoid multiple processing of the same filesystem event
            from app.supabase_client import _request
            existing = _request(f"/rest/v1/photos?original_name=eq.{urllib.parse.quote(src_path.name)}&event_id=eq.{active_event['id']}&select=id")
            if existing and len(existing) > 0:
                logger.info(f"Photo {src_path.name} already processed in Supabase. Skipping duplicate.")
                return

            # 3. Generate a secure, unique UUID photo_id
            photo_uuid = str(uuid.uuid4())
            clean_stem = "".join([c if c.isalnum() or c in ('-', '_') else '_' for c in src_path.stem])
            dest_filename = f"{clean_stem}_{photo_uuid[:8]}{src_path.suffix}"
            
            # Temporary local path in photos directory
            dest_path = settings.PHOTOS_DIR / dest_filename
            thumb_filename = f"{Path(dest_filename).stem}_thumb.jpg"
            thumb_path = settings.PHOTOS_DIR / thumb_filename
            
            # 4. Copy and compress file locally
            high_res_bytes = None
            thumb_bytes = None
            
            try:
                from PIL import ImageOps
                with Image.open(src_path) as img:
                    img = ImageOps.exif_transpose(img)
                    
                    # Compress high resolution
                    max_size = 2400
                    width, height = img.size
                    if width > max_size or height > max_size:
                        if width > height:
                            new_width = max_size
                            new_height = int(height * (max_size / width))
                        else:
                            new_height = max_size
                            new_width = int(width * (max_size / height))
                        high_res_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    else:
                        high_res_img = img
                    
                    # Save locally and get bytes
                    buffer_high = io.BytesIO()
                    high_res_img.convert('RGB').save(buffer_high, 'JPEG', quality=85, optimize=True)
                    high_res_bytes = buffer_high.getvalue()
                    
                    # Also save locally for recovery/fallback
                    high_res_img.convert('RGB').save(dest_path, 'JPEG', quality=85, optimize=True)
                    
                    # Generate thumbnail
                    try:
                        max_thumb_size = 800
                        if width > max_thumb_size or height > max_thumb_size:
                            if width > height:
                                new_thumb_w = max_thumb_size
                                new_thumb_h = int(height * (max_thumb_size / width))
                            else:
                                new_thumb_h = max_thumb_size
                                new_thumb_w = int(width * (max_thumb_size / height))
                            thumb_img = img.resize((new_thumb_w, new_thumb_h), Image.Resampling.LANCZOS)
                        else:
                            thumb_img = img
                        
                        buffer_thumb = io.BytesIO()
                        thumb_img.convert('RGB').save(buffer_thumb, 'JPEG', quality=65, optimize=True)
                        thumb_bytes = buffer_thumb.getvalue()
                        
                        # Save locally
                        thumb_img.convert('RGB').save(thumb_path, 'JPEG', quality=65, optimize=True)
                    except Exception as thumb_err:
                        logger.error(f"Thumbnail generation failed: {thumb_err}")
            except Exception as e:
                logger.error(f"Image compression failed: {e}. Falling back to copying raw file.")
                shutil.copy2(src_path, dest_path)
                with open(dest_path, 'rb') as f:
                    high_res_bytes = f.read()

            # 5. Upload to Supabase Storage
            if high_res_bytes:
                logger.info(f"Uploading high-res to Supabase Storage: {dest_filename}")
                supabase_client.upload_file(dest_filename, high_res_bytes)
                
            if thumb_bytes:
                logger.info(f"Uploading thumbnail to Supabase Storage: {thumb_filename}")
                supabase_client.upload_file(thumb_filename, thumb_bytes)
            else:
                logger.warning(f"No thumbnail bytes generated, uploading high-res as thumbnail fallback...")
                supabase_client.upload_file(thumb_filename, high_res_bytes)

            # 6. Insert into Supabase database
            new_photo_data = supabase_client.insert_photo(
                photo_id=photo_uuid,
                filename=dest_filename,
                original_name=src_path.name,
                event_id=active_event["id"]
            )
            
            logger.info(f"Successfully processed, uploaded, and stored photo: {dest_filename}")
            
            # 7. Notify web app about the new photo
            if self.callback_func:
                class MockPhoto:
                    def __init__(self, data):
                        self.id = data["id"]
                        self.filename = data["filename"]
                        self.original_name = data.get("original_name", "")
                        self.created_at = datetime.datetime.fromisoformat(data["created_at"].replace('Z', '+00:00')) if "created_at" in data else datetime.datetime.utcnow()
                        self.event_id = data["event_id"]
                
                import datetime
                self.callback_func(MockPhoto(new_photo_data))
                
        except Exception as e:
            logger.error(f"Error in folder watcher photo processing: {e}")

# Global instance
folder_watcher = FolderWatcher()

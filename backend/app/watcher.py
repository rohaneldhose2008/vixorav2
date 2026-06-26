import os
import time
import shutil
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image

from app.config import settings
from app.database import SessionLocal
from app.models import Event, Photo

logger = logging.getLogger("watcher")

class NewPhotoHandler(FileSystemEventHandler):
    def __init__(self, callback_func):
        super().__init__()
        self.callback_func = callback_func

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        # Check if the file is an image
        if file_path.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
            return

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
        """Copies the photo to Vixora's internal photos folder and creates database entry."""
        import uuid
        db = SessionLocal()
        try:
            # 1. Get active event
            active_event = db.query(Event).filter(Event.is_active == True).order_by(Event.id.desc()).first()
            if not active_event:
                # If no active event exists, create a default one
                active_event = Event(name="Default Event")
                db.add(active_event)
                db.commit()
                db.refresh(active_event)
                logger.info("No active event found. Created default 'Default Event'.")

            # 2. Check for duplicate to avoid multiple processing of the same filesystem event
            existing_photo = db.query(Photo).filter(
                Photo.original_name == src_path.name,
                Photo.event_id == active_event.id
            ).first()
            
            if existing_photo:
                logger.info(f"Photo {src_path.name} already processed. Skipping duplicate event.")
                return

            # 3. Generate a secure, unique UUID photo_id
            photo_uuid = str(uuid.uuid4())
            # Maintain the original stem in the filename for readability on disk
            clean_stem = "".join([c if c.isalnum() or c in ('-', '_') else '_' for c in src_path.stem])
            dest_filename = f"{clean_stem}_{photo_uuid[:8]}{src_path.suffix}"
            dest_path = settings.PHOTOS_DIR / dest_filename
            
            # 4. Copy file to local photos folder
            shutil.copy2(src_path, dest_path)
            
            # 5. Insert into Database
            new_photo = Photo(
                id=photo_uuid,
                filename=dest_filename,
                original_name=src_path.name,
                event_id=active_event.id
            )
            db.add(new_photo)
            db.commit()
            db.refresh(new_photo)
            
            logger.info(f"Successfully processed and stored photo: {dest_filename}")
            
            # 6. Notify web app about the new photo
            if self.callback_func:
                self.callback_func(new_photo)
                
        except Exception as e:
            logger.error(f"Error in folder watcher photo processing: {e}")
            db.rollback()
        finally:
            db.close()

# Global instance
folder_watcher = FolderWatcher()

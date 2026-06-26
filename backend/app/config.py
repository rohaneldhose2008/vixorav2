import os
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "VIXORA - QR Share System"
    DEBUG: bool = True
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    STATIC_DIR: str = os.getenv("STATIC_DIR", str(BASE_DIR.parent / "frontend" / "dist"))
    PHOTOS_DIR: Path = BASE_DIR / "photos"
    WATCH_DIR: Path = BASE_DIR / "watch_folder"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR}/vixora2.db")
    
    # Security
    ADMIN_PASSCODE: str = os.getenv("ADMIN_PASSCODE", "1234")
    
    # Camera Index for HDMI Capture mode
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    
    # Active mode: "watcher" (tethering folder) or "hdmi" (webcam stream)
    CAPTURE_MODE: str = os.getenv("CAPTURE_MODE", "watcher")
    
    # Public URL for generating QR codes (e.g., https://xxx.ngrok-free.app)
    PUBLIC_URL: str = os.getenv("PUBLIC_URL", "http://localhost:8001")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()

# Ensure required directories exist
settings.PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
settings.WATCH_DIR.mkdir(parents=True, exist_ok=True)

from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class PhotoResponse(BaseModel):
    id: str
    filename: str
    original_name: Optional[str]
    created_at: datetime
    event_id: int
    download_url: str
    qrcode_url: str

    model_config = ConfigDict(from_attributes=True)

class EventCreate(BaseModel):
    name: str

class EventResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    is_active: bool
    photos_count: int

    model_config = ConfigDict(from_attributes=True)

class AdminLoginRequest(BaseModel):
    passcode: str

class SettingsResponse(BaseModel):
    capture_mode: str
    camera_index: int
    watch_dir: str
    public_url: str
    passcode_preview: str # Return masked password or status

class SettingsUpdate(BaseModel):
    capture_mode: Optional[str] = None
    camera_index: Optional[int] = None
    watch_dir: Optional[str] = None
    public_url: Optional[str] = None
    passcode: Optional[str] = None

class StatsResponse(BaseModel):
    total_events: int
    total_photos: int
    current_event_name: Optional[str]
    current_event_photos_count: int

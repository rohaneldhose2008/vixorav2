import urllib.request
import urllib.error
import urllib.parse
import json
import logging
from pathlib import Path
from app.config import settings

logger = logging.getLogger("supabase_client")

def _request(endpoint: str, method: str = "GET", headers: dict = None, data: bytes = None) -> dict:
    url = f"{settings.SUPABASE_URL}{endpoint}"
    req_headers = {
        "apikey": settings.SUPABASE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_KEY}"
    }
    if headers:
        req_headers.update(headers)
        
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            res_data = response.read()
            if res_data:
                try:
                    return json.loads(res_data.decode("utf-8"))
                except json.JSONDecodeError:
                    return {"raw": res_data.decode("utf-8")}
            return {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        logger.error(f"Supabase request failed: {method} {endpoint} -> Status {e.code}: {err_msg}")
        raise RuntimeError(f"Supabase HTTP error {e.code}: {err_msg}")
    except Exception as e:
        logger.error(f"Supabase request exception: {method} {endpoint} -> {e}")
        raise e

def get_active_event() -> dict:
    res = _request("/rest/v1/events?is_active=eq.true&order=id.desc&limit=1")
    if res and isinstance(res, list) and len(res) > 0:
        return res[0]
    return None

def create_event(name: str) -> dict:
    try:
        # Deactivate existing active events
        _request("/rest/v1/events?is_active=eq.true", method="PATCH", 
                 headers={"Content-Type": "application/json"},
                 data=json.dumps({"is_active": False}).encode("utf-8"))
    except Exception:
        pass
                 
    # Create new event
    res = _request("/rest/v1/events?select=*", method="POST",
                   headers={"Content-Type": "application/json", "Prefer": "return=representation"},
                   data=json.dumps({"name": name, "is_active": True}).encode("utf-8"))
    if res and isinstance(res, list) and len(res) > 0:
        return res[0]
    raise RuntimeError("Failed to create event in Supabase")

def insert_photo(photo_id: str, filename: str, original_name: str, event_id: int) -> dict:
    res = _request("/rest/v1/photos?select=*", method="POST",
                   headers={"Content-Type": "application/json", "Prefer": "return=representation"},
                   data=json.dumps({
                       "id": photo_id,
                       "filename": filename,
                       "original_name": original_name,
                       "event_id": event_id
                   }).encode("utf-8"))
    if res and isinstance(res, list) and len(res) > 0:
        return res[0]
    raise RuntimeError("Failed to insert photo in Supabase")

def upload_file(filename: str, file_bytes: bytes, mime_type: str = "image/jpeg") -> bool:
    url_encoded_filename = urllib.parse.quote(filename)
    _request(f"/storage/v1/object/photos/{url_encoded_filename}", method="POST",
             headers={"Content-Type": mime_type},
             data=file_bytes)
    return True

def delete_file(filename: str) -> bool:
    try:
        _request(f"/storage/v1/object/photos/{filename}", method="DELETE")
        return True
    except Exception as e:
        logger.error(f"Failed to delete file {filename} from storage: {e}")
        return False

def delete_photo(photo_id: str) -> bool:
    try:
        _request(f"/rest/v1/photos?id=eq.{photo_id}", method="DELETE")
        return True
    except Exception as e:
        logger.error(f"Failed to delete photo row {photo_id} from database: {e}")
        return False

def get_stats() -> dict:
    try:
        events = _request("/rest/v1/events?select=id")
        total_events = len(events) if isinstance(events, list) else 0
        
        photos = _request("/rest/v1/photos?select=id")
        total_photos = len(photos) if isinstance(photos, list) else 0
        
        active_event = get_active_event()
        current_name = active_event["name"] if active_event else None
        
        current_count = 0
        if active_event:
            active_event_photos = _request(f"/rest/v1/photos?event_id=eq.{active_event['id']}&select=id")
            current_count = len(active_event_photos) if isinstance(active_event_photos, list) else 0
            
        return {
            "total_events": total_events,
            "total_photos": total_photos,
            "current_event_name": current_name,
            "current_event_photos_count": current_count
        }
    except Exception as e:
        logger.error(f"Failed to fetch stats: {e}")
        return {
            "total_events": 0,
            "total_photos": 0,
            "current_event_name": None,
            "current_event_photos_count": 0
        }

def get_event_photos() -> list:
    active_event = get_active_event()
    if not active_event:
        return []
    res = _request(f"/rest/v1/photos?event_id=eq.{active_event['id']}&order=created_at.desc")
    return res if isinstance(res, list) else []

def wipe_all_data() -> bool:
    # 1. Delete all events (which cascades to photos database rows)
    try:
        _request("/rest/v1/events", method="DELETE")
    except Exception as e:
        logger.error(f"Failed to delete events: {e}")
        
    # 2. Delete all files in storage bucket
    try:
        files = _request("/storage/v1/bucket/photos/list", method="POST",
                         headers={"Content-Type": "application/json"},
                         data=json.dumps({"sortBy": {"column": "name", "order": "asc"}}).encode("utf-8"))
        if files and isinstance(files, list):
            file_names = [f["name"] for f in files if "name" in f]
            if file_names:
                _request("/storage/v1/object/photos", method="DELETE",
                         headers={"Content-Type": "application/json"},
                         data=json.dumps({"prefixes": file_names}).encode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to clean storage during wipe: {e}")
        
    # 3. Create a new default active event
    create_event("My First Vixora Event")
    return True

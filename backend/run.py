import os
import uvicorn
from app.config import settings

if __name__ == "__main__":
    # Disable reload by default to prevent restarts when photos are written to disk
    port = int(os.getenv("PORT", 8001))
    print(f"Starting VIXORA V2 Backend on http://0.0.0.0:{port}")
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=port, 
        reload=False,
        log_level="info"
    )

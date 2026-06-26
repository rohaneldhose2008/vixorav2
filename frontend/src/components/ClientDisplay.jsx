import React, { useState, useEffect } from 'react';
import { Camera, QrCode } from 'lucide-react';

function ClientDisplay() {
  const [photos, setPhotos] = useState([]);
  const [status, setStatus] = useState("connecting");
  const [currentPage, setCurrentPage] = useState(0);
  const BACKEND_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '');

  useEffect(() => {
    const wsProtocol = BACKEND_URL.startsWith('https') ? 'wss:' : 'ws:';
    const wsHost = BACKEND_URL.replace(/^https?:\/\//, '');
    const wsUrl = `${wsProtocol}//${wsHost}/api/ws/display`;
    
    let ws;
    let reconnectTimeout;

    const connect = () => {
      setStatus("connecting");
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setStatus("connected");
        console.log("WebSocket display client connected.");
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          console.log("WebSocket event:", payload);
          
          if (payload.event === "init") {
            setPhotos(payload.data || []);
            setCurrentPage(0);
          } else if (payload.event === "new_photo") {
            // Add new photo to the front of the list without slicing, and jump to page 1
            setPhotos(prev => [payload.data, ...prev]);
            setCurrentPage(0);
          } else if (payload.event === "wiped" || payload.event === "event_changed") {
            setPhotos([]);
            setCurrentPage(0);
          }
        } catch (e) {
          console.error("Error parsing WS message:", e);
        }
      };

      ws.onclose = () => {
        setStatus("disconnected");
        console.log("WebSocket closed. Retrying in 3 seconds...");
        reconnectTimeout = setTimeout(connect, 3000);
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
        ws.close();
      };
    };

    connect();

    return () => {
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, []);

  // Pagination logic
  const photosPerPage = 10;
  const totalPages = Math.ceil(photos.length / photosPerPage);
  const pagePhotos = photos.slice(currentPage * photosPerPage, (currentPage + 1) * photosPerPage);

  const goToPrevPage = () => {
    if (currentPage > 0) {
      setCurrentPage(prev => prev - 1);
    }
  };

  const goToNextPage = () => {
    if (currentPage < totalPages - 1) {
      setCurrentPage(prev => prev + 1);
    }
  };

  // Determine dynamic grid layout sizes based on number of active photos on the current page
  const count = pagePhotos.length;
  let gridStyle = {};
  let qrSize = 90;
  let showQrText = true;

  if (count === 1) {
    gridStyle = { gridTemplateColumns: '1fr', gridTemplateRows: '1fr' };
    qrSize = 130;
  } else if (count === 2) {
    gridStyle = { gridTemplateColumns: 'repeat(2, 1fr)', gridTemplateRows: '1fr' };
    qrSize = 120;
  } else if (count <= 4) {
    gridStyle = { gridTemplateColumns: 'repeat(2, 1fr)', gridTemplateRows: 'repeat(2, 1fr)' };
    qrSize = 95;
  } else if (count <= 6) {
    gridStyle = { gridTemplateColumns: 'repeat(3, 1fr)', gridTemplateRows: 'repeat(2, 1fr)' };
    qrSize = 85;
  } else {
    gridStyle = { gridTemplateColumns: 'repeat(5, 1fr)', gridTemplateRows: 'repeat(2, 1fr)' };
    qrSize = 75;
    showQrText = count <= 8; // Hide text if 9 or 10 to fit in the grid cell height
  }

  return (
    <div className="slideshow-fullscreen">
      {photos.length === 0 ? (
        <div className="slideshow-standby">
          <Camera size={80} className="logo-icon-pulse" />
          <h1 className="gradient-text">VIXORA LIVE SHARE</h1>
          <p>Waiting for photos... Take a shot to display!</p>
        </div>
      ) : (
        <div className="display-grid-container" style={gridStyle}>
          {pagePhotos.map((photo) => {
            const isLatest = photo.id === photos[0]?.id;
            return (
              <div 
                key={photo.id} 
                className={`display-photo-card ${isLatest ? 'latest-card animate-slide-in' : ''}`}
              >
                {isLatest && <div className="card-badge">LATEST</div>}
                
                {/* Captured Photo */}
                <div className="display-img-wrapper">
                  <img src={`${BACKEND_URL}/api/photos/${photo.id}/thumbnail`} alt="Captured moment" />
                </div>
                
                {/* QR Code and Instructions underneath */}
                <div className="display-qr-wrapper">
                  <div className="display-qr-box" style={{ 
                    width: `${qrSize}px`, 
                    height: `${qrSize}px`
                  }}>
                    {/* Render QR code via absolute path pointing to Vercel */}
                    <img src={`${BACKEND_URL}/api/photos/${photo.id}/qrcode?public_url=${encodeURIComponent(window.location.origin)}`} alt="Scan QR" />
                  </div>
                  {showQrText && (
                    <div className="display-qr-text">
                      <h3>SCAN TO DOWNLOAD</h3>
                      <p>Open camera & scan</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      
      {/* Pagination controls at the bottom */}
      {totalPages > 1 && (
        <div className="display-pagination-bar">
          <button 
            className="pagination-btn" 
            onClick={goToPrevPage}
            disabled={currentPage === 0}
          >
            ← Previous Page
          </button>
          
          <span className="pagination-info">
            Page {currentPage + 1} of {totalPages} ({photos.length} photos)
          </span>
          
          <button 
            className="pagination-btn" 
            onClick={goToNextPage}
            disabled={currentPage === totalPages - 1}
          >
            Next Page →
          </button>
        </div>
      )}

      {/* Small Connection Status indicator */}
      <div className="status-indicator" style={{ bottom: totalPages > 1 ? '80px' : '15px' }}>
        <span className={`status-dot ${status === 'connected' ? 'connected' : status === 'connecting' ? 'connecting' : 'disconnected'}`}></span>
        {status.toUpperCase()}
      </div>
    </div>
  );
}

export default ClientDisplay;

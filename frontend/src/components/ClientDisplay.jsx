import React, { useState, useEffect } from 'react';
import { Camera, QrCode } from 'lucide-react';

function ClientDisplay() {
  const [photos, setPhotos] = useState([]);
  const [status, setStatus] = useState("connecting");
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
          } else if (payload.event === "new_photo") {
            // Add new photo to the front of the list, limit to 20
            setPhotos(prev => [payload.data, ...prev].slice(0, 20));
          } else if (payload.event === "wiped" || payload.event === "event_changed") {
            setPhotos([]);
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

  // Determine dynamic grid layout sizes based on number of active photos
  const count = photos.length;
  let cardStyle = {};
  let qrSize = 100;
  let showQrText = true;
  let containerClass = "display-grid-container";

  if (count <= 4) {
    containerClass += " layout-4";
    cardStyle = {}; // Let CSS flexbox flex-grow handle it
    qrSize = 100;
  } else if (count <= 8) {
    containerClass += " layout-8";
    cardStyle = { height: '42vh', width: '22vw', flex: 'none' };
    qrSize = 75;
  } else if (count <= 12) {
    containerClass += " layout-12";
    cardStyle = { height: '27vh', width: '22vw', flex: 'none' };
    qrSize = 60;
    showQrText = false; // Hide text to fit compact row
  } else {
    containerClass += " layout-20";
    cardStyle = { height: '20vh', width: '18vw', flex: 'none' };
    qrSize = 45;
    showQrText = false; // Hide text to fit compact grid
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
        <div className={containerClass}>
          {photos.map((photo, index) => {
            const isLatest = index === 0;
            return (
              <div 
                key={photo.id} 
                className={`display-photo-card ${isLatest ? 'latest-card animate-slide-in' : ''}`}
                style={cardStyle}
              >
                {isLatest && <div className="card-badge">LATEST</div>}
                
                {/* Captured Photo */}
                <div className="display-img-wrapper">
                  <img src={`${BACKEND_URL}/api/photos/${photo.id}/image`} alt="Captured moment" />
                </div>
                
                {/* QR Code and Instructions underneath */}
                <div className="display-qr-wrapper" style={{ padding: count > 8 ? '8px 12px' : '15px' }}>
                  <div className="display-qr-box" style={{ 
                    width: `${qrSize}px`, 
                    height: `${qrSize}px`, 
                    borderRadius: count > 8 ? '6px' : '12px' 
                  }}>
                    {/* Render QR code via absolute path pointing to local or Ngrok URL */}
                    <img src={`${BACKEND_URL}/api/photos/${photo.id}/qrcode`} alt="Scan QR" />
                  </div>
                  {showQrText && (
                    <div className="display-qr-text">
                      <h3>SCAN TO DOWNLOAD</h3>
                      <p>Open phone camera & scan</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      
      {/* Small Connection Status indicator */}
      <div className="status-indicator">
        <span className={`status-dot ${status === 'connected' ? 'connected' : status === 'connecting' ? 'connecting' : 'disconnected'}`}></span>
        {status.toUpperCase()}
      </div>
    </div>
  );
}

export default ClientDisplay;

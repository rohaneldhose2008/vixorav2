import React, { useState, useEffect } from 'react';
import { Camera, AlertCircle } from 'lucide-react';
import { supabase } from '../supabaseClient';

function ClientDisplay() {
  const [photos, setPhotos] = useState([]);
  const [status, setStatus] = useState("connecting");
  const [currentPage, setCurrentPage] = useState(0);

  const getSupabaseImageUrl = (filename, isThumb = false) => {
    let supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
    supabaseUrl = supabaseUrl.replace(/\/$/, '');
    if (!filename) return '';
    if (isThumb) {
      const extIndex = filename.lastIndexOf('.');
      if (extIndex !== -1) {
        const stem = filename.substring(0, extIndex);
        return `${supabaseUrl}/storage/v1/object/public/photos/${stem}_thumb.jpg`;
      }
    }
    return `${supabaseUrl}/storage/v1/object/public/photos/${filename}`;
  };

  useEffect(() => {
    let active = true;
    let photosSubscription = null;
    let eventsSubscription = null;

    const initSupabase = async () => {
      setStatus("connecting");
      try {
        // 1. Get active event
        const { data: activeEvents, error: eventErr } = await supabase
          .from('events')
          .select('*')
          .eq('is_active', true)
          .order('id', { ascending: false })
          .limit(1);

        if (eventErr) throw eventErr;

        if (activeEvents && activeEvents.length > 0) {
          const activeEvent = activeEvents[0];
          
          // 2. Get photos for the active event
          const { data: photosData, error: photosErr } = await supabase
            .from('photos')
            .select('*')
            .eq('event_id', activeEvent.id)
            .order('created_at', { ascending: false });

          if (photosErr) throw photosErr;

          if (active) {
            setPhotos(photosData || []);
            setStatus("connected");
          }

          // 3. Subscribe to Realtime inserts/deletes on photos table
          photosSubscription = supabase
            .channel('photos-changes')
            .on('postgres_changes', { event: '*', schema: 'public', table: 'photos' }, (payload) => {
              console.log("Photo change detected:", payload);
              if (payload.eventType === 'INSERT') {
                if (payload.new.event_id === activeEvent.id) {
                  setPhotos(prev => [payload.new, ...prev]);
                  setCurrentPage(0);
                }
              } else if (payload.eventType === 'DELETE') {
                setPhotos(prev => prev.filter(p => p.id !== payload.old.id));
              }
            })
            .subscribe();
        } else {
          if (active) {
            setPhotos([]);
            setStatus("connected");
          }
        }

        // 4. Subscribe to Realtime changes on events table (in case event is wiped/changed)
        eventsSubscription = supabase
          .channel('events-changes')
          .on('postgres_changes', { event: '*', schema: 'public', table: 'events' }, () => {
            console.log("Event table changed, refreshing dashboard...");
            initSupabase();
          })
          .subscribe();

      } catch (err) {
        console.error("Supabase connection error:", err);
        if (active) {
          setStatus("disconnected");
        }
      }
    };

    initSupabase();

    return () => {
      active = false;
      if (photosSubscription) supabase.removeChannel(photosSubscription);
      if (eventsSubscription) supabase.removeChannel(eventsSubscription);
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

  if (!supabase) {
    return (
      <div className="slideshow-fullscreen">
        <div className="slideshow-standby" style={{ padding: '40px' }}>
          <AlertCircle size={80} style={{ color: 'var(--accent-red)' }} />
          <h1 className="gradient-text">Supabase Config Missing</h1>
          <p style={{ maxWidth: '600px', margin: '0 auto 20px auto', color: 'var(--text-secondary)' }}>
            The website is running, but the Supabase cloud database credentials are not configured.
          </p>
          <div style={{ background: 'rgba(255,255,255,0.05)', padding: '15px', borderRadius: '8px', fontSize: '13px', textAlign: 'left', maxWidth: '600px', margin: '0 auto', fontFamily: 'monospace', lineHeight: '1.6' }}>
            Please add these variables to your Vercel Environment Variables:<br/>
            - <b>VITE_SUPABASE_URL</b><br/>
            - <b>VITE_SUPABASE_ANON_KEY</b>
          </div>
        </div>
      </div>
    );
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
            const downloadPageUrl = `${window.location.origin}/download/${photo.id}`;
            const qrCodeApiUrl = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(downloadPageUrl)}`;

            return (
              <div 
                key={photo.id} 
                className={`display-photo-card ${isLatest ? 'latest-card animate-slide-in' : ''}`}
              >
                {isLatest && <div className="card-badge">LATEST</div>}
                
                {/* Captured Photo */}
                <div className="display-img-wrapper">
                  <img src={getSupabaseImageUrl(photo.filename, true)} alt="Captured moment" />
                </div>
                
                {/* QR Code and Instructions underneath */}
                <div className="display-qr-wrapper">
                  <div className="display-qr-box" style={{ 
                    width: `${qrSize}px`, 
                    height: `${qrSize}px`
                  }}>
                    <img src={qrCodeApiUrl} alt="Scan QR" />
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

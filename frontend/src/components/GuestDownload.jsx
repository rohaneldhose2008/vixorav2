import React, { useState, useEffect } from 'react';
import { Download, Camera, Loader2, AlertCircle } from 'lucide-react';

function GuestDownload({ photoId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [imageSrc, setImageSrc] = useState('');
  
  const BACKEND_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '');
  const imageUrl = `${BACKEND_URL}/api/photos/${photoId}/image`;

  useEffect(() => {
    let active = true;
    let localUrl = '';

    setLoading(true);
    setError(null);

    // Fetch the photo as a blob with the bypass header
    fetch(imageUrl, {
      headers: {
        'ngrok-skip-browser-warning': 'true'
      }
    })
      .then((res) => {
        if (!res.ok) {
          throw new Error("This photo is no longer available or the event has ended.");
        }
        return res.blob();
      })
      .then((blob) => {
        if (active) {
          localUrl = window.URL.createObjectURL(blob);
          setImageSrc(localUrl);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => {
      active = false;
      if (localUrl) {
        window.URL.revokeObjectURL(localUrl);
      }
    };
  }, [photoId]);

  const handleDownload = () => {
    if (!imageSrc) return;
    const link = document.createElement('a');
    link.href = imageSrc;
    link.download = `Vixora_${photoId}.jpg`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="guest-viewport">
      <div className="glass-card guest-card">
        <div className="logo-section" style={{ justifyContent: 'center', marginBottom: '20px' }}>
          <Camera className="logo-icon" size={28} />
          <h1 className="gradient-text" style={{ fontSize: '24px' }}>VIXORA SHARE</h1>
        </div>

        {loading && (
          <div style={{ padding: '40px 0' }}>
            <Loader2 className="spinner" style={{ margin: '0 auto 20px auto' }} />
            <p style={{ color: 'var(--text-secondary)' }}>Retrieving your photo...</p>
          </div>
        )}

        {error && (
          <div className="alert alert-error">
            <AlertCircle size={20} />
            <p>{error}</p>
          </div>
        )}

        {!loading && !error && (
          <div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '15px' }}>
              Your captured moment is ready for download!
            </p>

            <div className="guest-img-wrapper">
              <img src={imageSrc} alt="Captured Moment" className="guest-img" />
            </div>

            <button className="btn btn-primary" onClick={handleDownload} style={{ width: '100%' }}>
              <Download size={18} />
              Download Photo
            </button>
            
            <p style={{ color: 'var(--text-muted)', fontSize: '12px', marginTop: '15px' }}>
              Note: This photo is stored temporarily and will be deleted when the event server stops.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default GuestDownload;

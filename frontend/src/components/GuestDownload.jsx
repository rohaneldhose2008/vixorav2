import React, { useState, useEffect } from 'react';
import { Download, Camera, Loader2, AlertCircle } from 'lucide-react';
import { supabase } from '../supabaseClient';

function GuestDownload({ photoId }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [imageSrc, setImageSrc] = useState('');
  const [photoInfo, setPhotoInfo] = useState(null);
  const [downloading, setDownloading] = useState(false);

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
    let localUrl = '';

    const fetchPhotoDetails = async () => {
      setLoading(true);
      setError(null);
      try {
        const { data, error: fetchErr } = await supabase
          .from('photos')
          .select('*')
          .eq('id', photoId)
          .single();

        if (fetchErr || !data) {
          throw new Error("This photo is no longer available or the event has ended.");
        }

        if (active) {
          setPhotoInfo(data);
          
          // Fetch the thumbnail image as a blob for preview
          const thumbUrl = getSupabaseImageUrl(data.filename, true);
          const res = await fetch(thumbUrl);
          if (!res.ok) throw new Error("Failed to load preview image.");
          
          const blob = await res.blob();
          if (active) {
            localUrl = window.URL.createObjectURL(blob);
            setImageSrc(localUrl);
            setLoading(false);
          }
        }
      } catch (err) {
        if (active) {
          setError(err.message);
          setLoading(false);
        }
      }
    };

    fetchPhotoDetails();

    return () => {
      active = false;
      if (localUrl) {
        window.URL.revokeObjectURL(localUrl);
      }
    };
  }, [photoId]);

  const handleDownload = async () => {
    if (!photoInfo) return;
    setDownloading(true);
    try {
      const highResUrl = getSupabaseImageUrl(photoInfo.filename, false);
      const res = await fetch(highResUrl);
      if (!res.ok) throw new Error("Failed to download high-resolution image.");

      const blob = await res.blob();
      const localUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = localUrl;
      link.download = `Vixora_${photoId}.jpg`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(localUrl);
    } catch (err) {
      console.warn("Direct blob download failed, falling back to new tab redirect:", err);
      // Fallback: open high-res image directly in a new tab so mobile/CORS works 100% of the time
      try {
        const highResUrl = getSupabaseImageUrl(photoInfo.filename, false);
        window.open(highResUrl, '_blank');
      } catch (e) {
        alert("Failed to open image link: " + e.message);
      }
    } finally {
      setDownloading(false);
    }
  };

  if (!supabase) {
    return (
      <div className="guest-viewport">
        <div className="glass-card guest-card" style={{ padding: '30px', textAlign: 'center' }}>
          <div className="logo-section" style={{ justifyContent: 'center', marginBottom: '20px' }}>
            <Camera className="logo-icon" size={28} />
            <h1 className="gradient-text" style={{ fontSize: '24px' }}>VIXORA SHARE</h1>
          </div>
          <AlertCircle size={48} style={{ color: 'var(--accent-red)', margin: '0 auto 15px auto' }} />
          <h3>Connection Failed</h3>
          <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '10px' }}>
            This website is missing its database connection configuration. Please inform the event admin.
          </p>
        </div>
      </div>
    );
  }

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

            <button className="btn btn-primary" onClick={handleDownload} disabled={downloading} style={{ width: '100%' }}>
              {downloading ? (
                <>
                  <Loader2 className="spinner" size={18} />
                  Downloading...
                </>
              ) : (
                <>
                  <Download size={18} />
                  Download Photo
                </>
              )}
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

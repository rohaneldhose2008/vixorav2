import React, { useState, useEffect, useRef } from 'react';
import { 
  Camera, FolderOpen, Play, Settings, RefreshCw, Trash2, 
  Plus, LogOut, ShieldAlert, Monitor, Eye, X, Download, Copy, Check
} from 'lucide-react';

const BACKEND_URL = (import.meta.env.VITE_API_URL || window.location.origin).replace(/\/$/, '');

function AdminPortal() {
  const [token, setToken] = useState(localStorage.getItem('vixora_admin_token') || '');
  const [passcode, setPasscode] = useState('');
  const [loginError, setLoginError] = useState('');
  
  // Dashboard states
  const [stats, setStats] = useState({
    total_events: 0,
    total_photos: 0,
    current_event_name: 'None',
    current_event_photos_count: 0
  });
  
  const [settingsData, setSettingsData] = useState({
    capture_mode: 'watcher',
    camera_index: 0,
    watch_dir: '',
    public_url: '',
    passcode_preview: '••••'
  });

  const [photos, setPhotos] = useState([]);
  const [newEventName, setNewEventName] = useState('');
  const [selectedPhoto, setSelectedPhoto] = useState(null);
  
  // Settings edit states
  const [editSettings, setEditSettings] = useState({ ...settingsData });
  const [settingsSuccess, setSettingsSuccess] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  
  // Loading states
  const [capturing, setCapturing] = useState(false);
  const [creatingEvent, setCreatingEvent] = useState(false);
  const [wiping, setWiping] = useState(false);
  
  const [copiedId, setCopiedId] = useState(null);

  // If not logged in, render login screen
  if (!token) {
    const handleLogin = async (e) => {
      e.preventDefault();
      try {
        const res = await fetch(`${BACKEND_URL}/api/admin/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ passcode })
        });
        
        if (res.ok) {
          const data = await res.json();
          setToken(data.token);
          localStorage.setItem('vixora_admin_token', data.token);
          setLoginError('');
        } else {
          const err = await res.json();
          setLoginError(err.detail || "Authentication failed");
        }
      } catch (err) {
        setLoginError("Could not connect to backend.");
      }
    };

    return (
      <div className="login-screen">
        <form className="glass-card login-card" onSubmit={handleLogin}>
          <div className="login-logo">
            <Camera size={48} style={{ margin: '0 auto 10px auto' }} />
            <h1 className="gradient-text">VIXORA ADMIN</h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: '14px', marginTop: '5px' }}>
              Vixora Camera Sharing System (V2)
            </p>
          </div>
          
          {loginError && (
            <div className="alert alert-error">
              <ShieldAlert size={18} />
              <span>{loginError}</span>
            </div>
          )}
          
          <div className="form-group">
            <label className="form-label">ENTER ADMIN PASSCODE</label>
            <input 
              type="password" 
              className="form-input" 
              placeholder="Default is 1234"
              value={passcode}
              onChange={(e) => setPasscode(e.target.value)}
              required
              autoFocus
            />
          </div>
          
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
            Unlock Dashboard
          </button>
        </form>
      </div>
    );
  }

  // Main Dashboard Render
  return <Dashboard 
    token={token} 
    setToken={setToken}
    stats={stats}
    setStats={setStats}
    settingsData={settingsData}
    setSettingsData={setSettingsData}
    editSettings={editSettings}
    setEditSettings={setEditSettings}
    photos={photos}
    setPhotos={setPhotos}
    newEventName={newEventName}
    setNewEventName={setNewEventName}
    selectedPhoto={selectedPhoto}
    setSelectedPhoto={setSelectedPhoto}
    settingsSuccess={settingsSuccess}
    setSettingsSuccess={setSettingsSuccess}
    settingsError={settingsError}
    setSettingsError={setSettingsError}
    capturing={capturing}
    setCapturing={setCapturing}
    creatingEvent={creatingEvent}
    setCreatingEvent={setCreatingEvent}
    wiping={wiping}
    setWiping={setWiping}
    copiedId={copiedId}
    setCopiedId={setCopiedId}
  />;
}

// Inner Dashboard Component to encapsulate hooks cleanly
function Dashboard({
  token, setToken, stats, setStats, settingsData, setSettingsData,
  editSettings, setEditSettings, photos, setPhotos, newEventName, setNewEventName,
  selectedPhoto, setSelectedPhoto, settingsSuccess, setSettingsSuccess,
  settingsError, setSettingsError, capturing, setCapturing, creatingEvent, setCreatingEvent,
  wiping, setWiping, copiedId, setCopiedId
}) {

  // Fetch all initial data
  const fetchData = async () => {
    try {
      const headers = { 'Authorization': `Bearer ${token}` };
      
      // Stats
      const statsRes = await fetch(`${BACKEND_URL}/api/admin/stats`, { headers });
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
      
      // Settings
      const settingsRes = await fetch(`${BACKEND_URL}/api/admin/settings`, { headers });
      if (settingsRes.ok) {
        const setts = await settingsRes.json();
        setSettingsData(setts);
        setEditSettings(setts);
      }
      
      // Photos list
      const photosRes = await fetch(`${BACKEND_URL}/api/admin/photos`, { headers });
      if (photosRes.ok) {
        const photosList = await photosRes.json();
        setPhotos(photosList);
      }
    } catch (err) {
      console.error("Error loading dashboard data:", err);
    }
  };

  useEffect(() => {
    fetchData();

    // Setup WebSocket listener for real-time dashboard updates
    const wsProtocol = BACKEND_URL.startsWith('https') ? 'wss:' : 'ws:';
    const wsHost = BACKEND_URL.replace(/^https?:\/\//, '');
    const wsUrl = `${wsProtocol}//${wsHost}/api/ws/display`;
    
    let ws;
    const connectWS = () => {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.event === "new_photo") {
            // Prepend new photo to list
            setPhotos(prev => [payload.data, ...prev]);
            // Increment counts
            setStats(prev => ({
              ...prev,
              total_photos: prev.total_photos + 1,
              current_event_photos_count: prev.current_event_photos_count + 1
            }));
          } else if (payload.event === "wiped" || payload.event === "event_changed") {
            fetchData();
          }
        } catch (e) {
          console.error("Error handling WS message in admin:", e);
        }
      };
      ws.onclose = () => {
        setTimeout(connectWS, 3000);
      };
    };
    connectWS();

    return () => {
      if (ws) ws.close();
    };
  }, [token]);

  // Spacebar hotkey listener for HDMI capture mode
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.code === 'Space' && settingsData.capture_mode === 'hdmi') {
        // Prevent default spacebar scroll behavior
        e.preventDefault();
        triggerCapture();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [settingsData.capture_mode]);

  const triggerCapture = async () => {
    if (capturing || settingsData.capture_mode !== 'hdmi') return;
    setCapturing(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/camera/capture`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "Capture failed");
      }
    } catch (e) {
      alert("Error triggering capture");
    } finally {
      setCapturing(false);
    }
  };

  const handleSaveSettings = async (e) => {
    e.preventDefault();
    setSettingsSuccess(false);
    setSettingsError('');
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/settings`, {
        method: 'PUT',
        headers: { 
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(editSettings)
      });
      
      if (res.ok) {
        const data = await res.json();
        setSettingsData(data);
        setEditSettings(data);
        setSettingsSuccess(true);
        // Refresh token if password changed
        if (editSettings.passcode) {
          setToken(editSettings.passcode);
          localStorage.setItem('vixora_admin_token', editSettings.passcode);
        }
        setTimeout(() => setSettingsSuccess(false), 3000);
      } else {
        const err = await res.json();
        setSettingsError(err.detail || "Failed to save settings");
      }
    } catch (e) {
      setSettingsError("Connection error.");
    }
  };

  const handleCreateEvent = async (e) => {
    e.preventDefault();
    if (!newEventName.trim()) return;
    setCreatingEvent(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/event`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ name: newEventName })
      });
      
      if (res.ok) {
        setNewEventName('');
        fetchData();
      } else {
        alert("Failed to create event");
      }
    } catch (err) {
      alert("Error connecting to server");
    } finally {
      setCreatingEvent(false);
    }
  };

  const handleWipeData = async () => {
    if (!window.confirm("WARNING: This will permanently DELETE all events, photos, and local files on this computer. Are you absolutely sure?")) {
      return;
    }
    setWiping(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/admin/wipe`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        fetchData();
        alert("All session data wiped successfully.");
      } else {
        alert("Failed to wipe data.");
      }
    } catch (e) {
      alert("Connection error.");
    } finally {
      setWiping(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('vixora_admin_token');
    setToken('');
  };

  const copyToClipboard = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <div className="admin-container">
      {/* Header */}
      <header className="admin-header">
        <div className="logo-section">
          <Camera className="logo-icon" size={32} />
          <div>
            <h1 className="gradient-text" style={{ fontSize: '28px', lineHeight: 1 }}>VIXORA PANEL</h1>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '4px' }}>
              ACTIVE MODE: <span style={{ color: '#fff', fontWeight: 'bold' }}>{settingsData.capture_mode.toUpperCase()}</span>
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '12px' }}>
          <button className="btn btn-secondary" onClick={() => window.open('/display', '_blank')}>
            <Monitor size={16} />
            TV Screen (Slideshow)
          </button>
          <button className="btn btn-secondary" onClick={handleLogout} style={{ color: 'var(--text-error)' }}>
            <LogOut size={16} />
            Lock
          </button>
        </div>
      </header>

      {/* Stats Bar */}
      <section className="stats-bar">
        <div className="stat-card">
          <Play className="stat-icon" size={24} />
          <div className="stat-info">
            <h4>Active Event</h4>
            <p style={{ fontSize: '18px', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: '180px' }}>
              {stats.current_event_name || 'None'}
            </p>
          </div>
        </div>
        <div className="stat-card">
          <Camera className="stat-icon" size={24} />
          <div className="stat-info">
            <h4>Event Photos</h4>
            <p>{stats.current_event_photos_count}</p>
          </div>
        </div>
        <div className="stat-card">
          <RefreshCw className="stat-icon" size={24} />
          <div className="stat-info">
            <h4>All-Time Photos</h4>
            <p>{stats.total_photos}</p>
          </div>
        </div>
      </section>

      {/* Grid */}
      <div className="admin-grid">
        {/* Left Side: Live stream or Watch Status + History */}
        <div>
          <div className="glass-card" style={{ marginBottom: '30px' }}>
            <h3 style={{ marginBottom: '15px' }}>Live Capture Console</h3>
            
            {settingsData.capture_mode === 'hdmi' ? (
              <div>
                <div className="camera-preview-container">
                  <img 
                    src={`${BACKEND_URL}/api/camera/stream`} 
                    alt="HDMI Live Preview" 
                    className="camera-preview" 
                    onError={(e) => {
                      // Handle stream failure/placeholder
                      e.target.style.display = 'none';
                      e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                  <div className="camera-disconnected" style={{ display: 'none' }}>
                    <ShieldAlert size={48} />
                    <p>HDMI Camera stream offline or index invalid</p>
                  </div>
                  
                  <div className="camera-controls">
                    <button 
                      className="btn btn-primary" 
                      onClick={triggerCapture}
                      disabled={capturing}
                      style={{ padding: '16px 36px', fontSize: '18px', borderRadius: '50px', animation: 'pulse-glow 2s infinite' }}
                    >
                      <Camera size={22} />
                      CAPTURE (SPACEBAR)
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ 
                padding: '40px', 
                background: 'rgba(59, 130, 246, 0.05)', 
                border: '2px dashed rgba(59, 130, 246, 0.2)', 
                borderRadius: 'var(--border-radius-sm)',
                textAlign: 'center'
              }}>
                <FolderOpen size={64} style={{ color: 'var(--accent-blue)', marginBottom: '15px', filter: 'drop-shadow(0 0 10px var(--accent-blue-glow))' }} />
                <h3>TETHERED FOLDER WATCHER RUNNING</h3>
                <p style={{ color: 'var(--text-secondary)', marginTop: '8px', fontSize: '14px', maxWidth: '500px', margin: '8px auto 0 auto' }}>
                  The backend is watching: <code style={{ background: '#000', padding: '2px 6px', borderRadius: '4px', fontSize: '13px' }}>{settingsData.watch_dir}</code>
                </p>
                <p style={{ color: 'var(--text-muted)', marginTop: '8px', fontSize: '12px' }}>
                  Take photos using your camera. Your tethering software will save them to this folder, and Vixora will instantly process them and display them on the TV screen!
                </p>
              </div>
            )}
          </div>

          {/* History */}
          <div className="glass-card">
            <h3 style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>Photos Gallery ({photos.length})</span>
              <button className="icon-button" onClick={fetchData} title="Refresh">
                <RefreshCw size={16} />
              </button>
            </h3>
            
            {photos.length === 0 ? (
              <div className="empty-state" style={{ marginTop: '20px' }}>
                <Camera size={32} style={{ marginBottom: '10px' }} />
                <p>No photos captured in this event yet.</p>
              </div>
            ) : (
              <div className="gallery-grid">
                {photos.map(p => (
                  <div className="gallery-item" key={p.id} onClick={() => setSelectedPhoto(p)}>
                    <img src={`${BACKEND_URL}/api/photos/${p.id}/image`} alt={p.original_name} />
                    <div className="gallery-overlay">
                      <span className="gallery-name">{p.original_name || p.filename}</span>
                      <Eye size={14} style={{ color: '#fff' }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Side: Settings & Event Control */}
        <div>
          {/* Settings Box */}
          <div className="glass-card" style={{ marginBottom: '30px' }}>
            <h3 style={{ marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Settings size={20} />
              Settings Config
            </h3>
            
            {settingsSuccess && <div className="alert alert-success">Settings saved successfully!</div>}
            {settingsError && <div className="alert alert-error">{settingsError}</div>}
            
            <form onSubmit={handleSaveSettings}>
              <div className="form-group">
                <label className="form-label">Capture Mode</label>
                <select 
                  className="form-select"
                  value={editSettings.capture_mode}
                  onChange={(e) => setEditSettings({ ...editSettings, capture_mode: e.target.value })}
                >
                  <option value="watcher">Tethered Folder Watcher</option>
                  <option value="hdmi">HDMI / Webcam Capture</option>
                </select>
              </div>

              {editSettings.capture_mode === 'hdmi' ? (
                <div className="form-group">
                  <label className="form-label">Camera Device Index</label>
                  <select
                    className="form-select"
                    value={editSettings.camera_index}
                    onChange={(e) => setEditSettings({ ...editSettings, camera_index: parseInt(e.target.value) })}
                  >
                    <option value="0">Camera Index 0 (Default)</option>
                    <option value="1">Camera Index 1</option>
                    <option value="2">Camera Index 2</option>
                    <option value="3">Camera Index 3</option>
                  </select>
                </div>
              ) : (
                <div className="form-group">
                  <label className="form-label">Tether Watch Directory Path</label>
                  <input 
                    type="text" 
                    className="form-input"
                    value={editSettings.watch_dir}
                    onChange={(e) => setEditSettings({ ...editSettings, watch_dir: e.target.value })}
                    required
                  />
                  <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                    Absolute path where tether software saves images.
                  </p>
                </div>
              )}

              <div className="form-group">
                <label className="form-label">Public QR Link Host URL</label>
                <input 
                  type="text" 
                  className="form-input"
                  placeholder="e.g. https://xxx.ngrok-free.app"
                  value={editSettings.public_url}
                  onChange={(e) => setEditSettings({ ...editSettings, public_url: e.target.value })}
                  required
                />
                <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  Used to generate downloadable guest QR codes. Paste your Ngrok or Cloudflare URL here.
                </p>
              </div>

              <div className="form-group">
                <label className="form-label">Change Admin Passcode</label>
                <input 
                  type="password" 
                  className="form-input"
                  placeholder="Enter new passcode to change"
                  value={editSettings.passcode || ''}
                  onChange={(e) => setEditSettings({ ...editSettings, passcode: e.target.value })}
                />
              </div>

              <button type="submit" className="btn btn-primary" style={{ width: '100%' }}>
                Apply & Save Settings
              </button>
            </form>
          </div>

          {/* Quick Actions Box */}
          <div className="glass-card">
            <h3 style={{ marginBottom: '20px' }}>Quick Controls</h3>
            
            {/* Create Event */}
            <form onSubmit={handleCreateEvent} style={{ marginBottom: '25px', borderBottom: '1px solid var(--glass-border)', paddingBottom: '20px' }}>
              <div className="form-group">
                <label className="form-label">New Event Name</label>
                <input 
                  type="text" 
                  className="form-input"
                  placeholder="e.g. Liam & Lily Wedding"
                  value={newEventName}
                  onChange={(e) => setNewEventName(e.target.value)}
                  required
                />
              </div>
              <button type="submit" className="btn btn-secondary" style={{ width: '100%' }} disabled={creatingEvent}>
                <Plus size={16} />
                Create & Switch Event
              </button>
            </form>

            {/* Wipe session */}
            <div>
              <p style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '12px' }}>
                Wipes all event logs, SQLite database, and physically deletes all saved JPGs.
              </p>
              <button 
                type="button" 
                className="btn btn-danger" 
                style={{ width: '100%' }} 
                onClick={handleWipeData}
                disabled={wiping}
              >
                <Trash2 size={16} />
                {wiping ? 'Wiping...' : 'Reset & Wipe All Session Data'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Photo Modal Preview */}
      {selectedPhoto && (
        <div className="photo-modal-overlay" onClick={() => setSelectedPhoto(null)}>
          <div className="photo-modal-content" onClick={(e) => e.stopPropagation()}>
            <button className="close-modal-btn" onClick={() => setSelectedPhoto(null)}>
              <X size={18} />
            </button>
            
            <h3 style={{ marginBottom: '15px', alignSelf: 'flex-start' }}>Photo details</h3>
            
            <div style={{ display: 'flex', gap: '20px', flexDirection: window.innerWidth < 768 ? 'column' : 'row' }}>
              <div style={{ maxWidth: '400px', flex: 1 }}>
                <img 
                  src={`${BACKEND_URL}/api/photos/${selectedPhoto.id}/image`} 
                  alt="Capture Details" 
                  style={{ width: '100%', borderRadius: 'var(--border-radius-sm)', objectFit: 'cover' }}
                />
              </div>
              
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: '10px' }}>
                <img 
                  src={`${BACKEND_URL}/api/photos/${selectedPhoto.id}/qrcode?public_url=${encodeURIComponent(window.location.origin)}`} 
                  alt="QR Code" 
                  style={{ width: '180px', height: '180px', background: '#fff', padding: '10px', borderRadius: '8px' }}
                />
                
                <h4 style={{ marginTop: '15px', color: '#fff' }}>Guest Scan Link</h4>
                <p style={{ color: 'var(--text-secondary)', fontSize: '12px', wordBreak: 'break-all', margin: '5px 0 15px 0', maxWidth: '280px' }}>
                  {selectedPhoto.download_url}
                </p>
                
                <div style={{ display: 'flex', gap: '10px', width: '100%' }}>
                  <button 
                    className="btn btn-secondary" 
                    onClick={() => copyToClipboard(selectedPhoto.download_url, selectedPhoto.id)}
                    style={{ flex: 1, padding: '8px 12px', fontSize: '13px' }}
                  >
                    {copiedId === selectedPhoto.id ? <Check size={14} style={{ color: 'var(--text-success)' }} /> : <Copy size={14} />}
                    {copiedId === selectedPhoto.id ? 'Copied' : 'Copy Link'}
                  </button>
                  <a 
                    href={`${BACKEND_URL}/api/photos/${selectedPhoto.id}/image`} 
                    download={`Vixora_${selectedPhoto.id}.jpg`}
                    className="btn btn-primary"
                    style={{ flex: 1, padding: '8px 12px', fontSize: '13px', textDecoration: 'none' }}
                  >
                    <Download size={14} />
                    Download File
                  </a>
                </div>
              </div>
            </div>
            
            <div style={{ width: '100%', borderTop: '1px solid var(--glass-border)', marginTop: '20px', paddingTop: '15px', color: 'var(--text-secondary)', fontSize: '12px', alignSelf: 'flex-start' }}>
              <p>Original filename: <strong>{selectedPhoto.original_name}</strong></p>
              <p style={{ marginTop: '4px' }}>Captured: {new Date(selectedPhoto.created_at).toLocaleString()}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminPortal;

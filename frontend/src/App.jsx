import React, { useState, useEffect } from 'react';
import AdminPortal from './components/AdminPortal';
import ClientDisplay from './components/ClientDisplay';
import GuestDownload from './components/GuestDownload';

function App() {
  const [route, setRoute] = useState('');
  const [photoId, setPhotoId] = useState('');

  useEffect(() => {
    const handleLocation = () => {
      const path = window.location.pathname;
      if (path.startsWith('/download/')) {
        const id = path.split('/download/')[1];
        setRoute('download');
        setPhotoId(id);
      } else if (path === '/display' || path === '/slideshow' || path === '/client') {
        setRoute('display');
      } else {
        setRoute('admin');
      }
    };

    handleLocation();
    
    // Listen for history popstate events (e.g. back/forward buttons)
    window.addEventListener('popstate', handleLocation);
    return () => window.removeEventListener('popstate', handleLocation);
  }, []);

  if (route === 'download') {
    return <GuestDownload photoId={photoId} />;
  }
  if (route === 'display') {
    return <ClientDisplay />;
  }
  if (route === 'admin') {
    return <AdminPortal />;
  }
  
  return (
    <div className="vixora-loader">
      <div className="spinner"></div>
      <p>Initializing Vixora...</p>
    </div>
  );
}

export default App;

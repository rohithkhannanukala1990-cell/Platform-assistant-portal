import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { AuthProvider } from './contexts/AuthContext'
import { PortalProvider } from './contexts/PortalContext'
import { PlatformContextProvider } from './contexts/PlatformContext'
import { ToastProvider } from './components/ToastNotification'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <ToastProvider>
        <PortalProvider>
          <PlatformContextProvider>
            <ErrorBoundary>
              <App />
            </ErrorBoundary>
          </PlatformContextProvider>
        </PortalProvider>
      </ToastProvider>
    </AuthProvider>
  </React.StrictMode>,
)

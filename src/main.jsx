import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { AuthProvider } from './contexts/AuthContext'
import { PortalProvider } from './contexts/PortalContext'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <PortalProvider>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </PortalProvider>
    </AuthProvider>
  </React.StrictMode>,
)

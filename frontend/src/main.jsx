import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { connectDatastore } from './services/firebase'

// Ask the backend which datastore it is on BEFORE the first render.
//
// Firestore will not let a client be pointed at an emulator once it has
// started operating, and the Audit trail subscribes as soon as it mounts.
// So this has to settle first. It never rejects — a failure leaves those
// two pages saying so rather than silently watching the wrong database.
connectDatastore().finally(() => {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})

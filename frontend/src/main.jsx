import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import posthog from 'posthog-js'
import App from './App.jsx'
import './index.css'

// Init PostHog (optional — skipped if key not set)
const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY
if (POSTHOG_KEY) {
  posthog.init(POSTHOG_KEY, {
    api_host: 'https://us.i.posthog.com',
    capture_pageview: true,
    autocapture: false,
    person_profiles: 'identified_only',
  })
}

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

if (!PUBLISHABLE_KEY) {
  console.warn(
    'Missing VITE_CLERK_PUBLISHABLE_KEY. Set it in .env.local to enable authentication.'
  )
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider
      publishableKey={PUBLISHABLE_KEY || 'pk_test_placeholder'}
      fallbackRedirectUrl="/"
    >
      <App />
    </ClerkProvider>
  </React.StrictMode>,
)

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind explicitly to IPv4 loopback — on some Windows setups Vite's
    // default "localhost" binds to ::1 only, which curl/some tools won't reach.
    host: '127.0.0.1',
    port: 5173,
  },
})

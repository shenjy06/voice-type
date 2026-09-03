import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

const rendererInput = {
  floating: resolve(__dirname, 'src/renderer/floating/index.html'),
  overlay: resolve(__dirname, 'src/renderer/overlay/index.html'),
  settings: resolve(__dirname, 'src/renderer/settings/index.html'),
  history: resolve(__dirname, 'src/renderer/history/index.html'),
  audio: resolve(__dirname, 'src/renderer/audio/index.html')
}

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()]
  },
  preload: {
    plugins: [externalizeDepsPlugin()]
  },
  renderer: {
    plugins: [react()],
    build: {
      rollupOptions: {
        input: rendererInput
      }
    }
  }
})

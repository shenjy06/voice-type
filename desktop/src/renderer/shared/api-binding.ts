// Thin re-export so renderers can use window.api with full typing even before
// the global declaration in api.ts is picked up by every file.

import type { VoiceTypeApi } from './api'

export const windowApi: VoiceTypeApi = (window as unknown as { api: VoiceTypeApi }).api

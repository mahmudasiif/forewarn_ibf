/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_CCM_DASHBOARD_URL?: string;
  readonly VITE_MAP_TILE_URL?: string;
  readonly VITE_DEFAULT_CENTER?: string;
  readonly VITE_DEFAULT_ZOOM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

export function directusUrl(env: Record<string, string | undefined> = import.meta.env):
string {
  return (env.VITE_DIRECTUS_URL ?? 'http://localhost:8065').replace(/\/+$/, '')
}

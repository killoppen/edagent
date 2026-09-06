const DEFAULT_ROLE_ATLAS_URL = 'http://localhost:3000'

export function resolveRoleAtlasUrl(configured?: string) {
  const candidate = (configured || DEFAULT_ROLE_ATLAS_URL).trim()
  try {
    const url = new URL(candidate)
    if (!['http:', 'https:'].includes(url.protocol)) throw new Error('unsupported protocol')
    return new URL('/', url).toString()
  } catch {
    return `${DEFAULT_ROLE_ATLAS_URL}/`
  }
}

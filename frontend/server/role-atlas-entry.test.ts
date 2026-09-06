import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveRoleAtlasUrl } from '../src/role-atlas-entry.ts'

test('Role Atlas entry uses the configured HTTP(S) origin', () => {
  assert.equal(resolveRoleAtlasUrl('https://roles.example.test/base'), 'https://roles.example.test/')
})

test('Role Atlas entry falls back to the local service for invalid origins', () => {
  assert.equal(resolveRoleAtlasUrl('javascript:alert(1)'), 'http://localhost:3000/')
  assert.equal(resolveRoleAtlasUrl(''), 'http://localhost:3000/')
})

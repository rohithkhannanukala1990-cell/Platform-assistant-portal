import { describe, expect, it } from 'vitest'
import {
  argoAppToDeployment,
  githubRunToDeployment,
  isDeployishRun,
  mapGithubConclusion,
} from '../utils/deploymentsMap'

describe('mapGithubConclusion', () => {
  it('maps in-progress and success/failure', () => {
    expect(mapGithubConclusion('in_progress', null)).toBe('running')
    expect(mapGithubConclusion('completed', 'success')).toBe('success')
    expect(mapGithubConclusion('completed', 'failure')).toBe('failed')
    expect(mapGithubConclusion('completed', 'cancelled')).toBe('cancelled')
  })
})

describe('isDeployishRun', () => {
  it('detects deploy-related workflow names', () => {
    expect(isDeployishRun({ id: 1, name: 'Deploy Production' })).toBe(true)
    expect(isDeployishRun({ id: 2, name: 'CI', path: '.github/workflows/ci.yml' })).toBe(false)
    expect(isDeployishRun({ id: 3, path: '.github/workflows/release.yml' })).toBe(true)
  })
})

describe('githubRunToDeployment', () => {
  it('normalizes a workflow run into a deployment row', () => {
    const row = githubRunToDeployment(
      {
        id: 42,
        name: 'Deploy',
        status: 'completed',
        conclusion: 'success',
        head_branch: 'main',
        head_sha: 'abcdef123456',
        actor: { login: 'ci-bot' },
        display_title: 'ship it',
        html_url: 'https://example.com/run/42',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      'acme/api'
    )
    expect(row.id).toBe('gh-42')
    expect(row.service).toBe('acme/api')
    expect(row.env).toBe('production')
    expect(row.status).toBe('success')
    expect(row.commit).toBe('abcdef1')
    expect(row.source).toBe('github')
  })
})

describe('argoAppToDeployment', () => {
  it('maps healthy synced apps to success', () => {
    const row = argoAppToDeployment({
      name: 'payments',
      namespace: 'prod',
      health: 'Healthy',
      sync: 'Synced',
      revision: 'deadbeefcafe',
    })
    expect(row.source).toBe('argocd')
    expect(row.status).toBe('success')
    expect(row.service).toBe('payments')
  })
})

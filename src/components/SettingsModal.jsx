import { useEffect, useState } from 'react'
import {
  X,
  Settings,
  Webhook,
  Save,
  CheckCircle2,
  AlertCircle,
  Cloud,
  GitBranch,
  Zap,
  Ticket,
  KeyRound,
  AtSign,
  Globe,
  Code2,
  Copy,
  Check,
} from 'lucide-react'

const API = 'http://127.0.0.1:8000/api/settings'

const CLOUD_OPTIONS    = ['GCP', 'AWS', 'Azure', 'DigitalOcean']
const CICD_OPTIONS     = ['GitHub Actions', 'GitLab CI', 'Jenkins']

export default function SettingsModal({ onClose }) {
  const [settings, setSettings]   = useState({})
  const [saving, setSaving]       = useState(false)
  const [saved, setSaved]         = useState(false)
  const [error, setError]         = useState(null)
  const [localValues, setLocal]   = useState({})

  useEffect(() => {
    fetch(API)
      .then((r) => r.json())
      .then((data) => { setSettings(data); setLocal(data) })
      .catch(() => setError('Could not load settings — is the backend running?'))
  }, [])

  function handleChange(key, value) {
    setLocal((prev) => ({ ...prev, [key]: value }))
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const res = await fetch(API, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(localValues),
      })
      if (!res.ok) throw new Error('Save failed')
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {
      setError('Failed to save settings.')
    } finally {
      setSaving(false)
    }
  }

  // Close on backdrop click
  function handleBackdrop(e) {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleBackdrop}
    >
      <div className="flex flex-col w-full max-w-lg bg-surface border border-border rounded-2xl shadow-2xl overflow-hidden animate-fade-in">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-sidebar">
          <div className="flex items-center gap-2.5">
            <Settings className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-bold text-white">Settings</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-card text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-col gap-6 px-6 py-6 overflow-y-auto max-h-[70vh]">

          {error && (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {error}
            </div>
          )}

          {/* Slack */}
          <Section title="Slack Integration" icon={Webhook} iconColor="text-violet-400">
            <Field
              label="Slack Webhook URL"
              hint="Paste your Incoming Webhook URL — Critical/High alerts will be posted automatically."
              type="url"
              placeholder="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXX"
              value={localValues.slack_webhook_url ?? ''}
              onChange={(v) => handleChange('slack_webhook_url', v)}
            />
          </Section>

          {/* Jira */}
          <Section title="Jira Integration" icon={Ticket} iconColor="text-blue-400">
            <Field
              label="Jira Domain"
              hint="Your Atlassian domain (without https://)."
              type="text"
              placeholder="yourcompany.atlassian.net"
              value={localValues.jira_domain ?? ''}
              onChange={(v) => handleChange('jira_domain', v)}
              icon={Globe}
            />
            <Field
              label="Jira Email"
              type="email"
              placeholder="you@yourcompany.com"
              value={localValues.jira_email ?? ''}
              onChange={(v) => handleChange('jira_email', v)}
              icon={AtSign}
            />
            <Field
              label="Jira API Token"
              hint="Generate from id.atlassian.com → Security → API tokens."
              type="password"
              placeholder="••••••••••••••••••••••"
              value={localValues.jira_api_token ?? ''}
              onChange={(v) => handleChange('jira_api_token', v)}
              icon={KeyRound}
            />
            <Field
              label="Jira Project Key"
              hint='The short key shown before issue numbers (e.g. "OPS" in OPS-123).'
              type="text"
              placeholder="OPS"
              value={localValues.jira_project_key ?? ''}
              onChange={(v) => handleChange('jira_project_key', v)}
            />
          </Section>

          {/* Automation */}
          <Section title="Automation" icon={Zap} iconColor="text-yellow-400">
            <ToggleField
              label="Auto-Triage on Paste"
              hint="Automatically trigger analysis when logs are pasted."
              checked={localValues.auto_triage_enabled === 'true'}
              onChange={(v) => handleChange('auto_triage_enabled', v ? 'true' : 'false')}
            />
          </Section>

          {/* Webhook Ingestion */}
          <Section title="Log Ingestion Webhook" icon={Code2} iconColor="text-cyan-400">
            <WebhookDocs />
          </Section>

          {/* Defaults */}
          <Section title="Default Preferences" icon={Cloud} iconColor="text-blue-400">
            <SelectField
              label="Default Cloud Provider"
              value={localValues.default_cloud ?? 'GCP'}
              options={CLOUD_OPTIONS}
              onChange={(v) => handleChange('default_cloud', v)}
            />
            <SelectField
              label="Default CI/CD Tool"
              value={localValues.default_cicd_tool ?? 'GitHub Actions'}
              options={CICD_OPTIONS}
              onChange={(v) => handleChange('default_cicd_tool', v)}
              icon={GitBranch}
            />
          </Section>

        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-sidebar">
          {saved ? (
            <span className="flex items-center gap-1.5 text-xs text-accent">
              <CheckCircle2 className="w-3.5 h-3.5" />Settings saved
            </span>
          ) : (
            <span className="text-xs text-slate-600">Changes are saved to the local database.</span>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-slate-400 hover:text-white border border-border hover:border-slate-600 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold bg-accent text-black hover:bg-green-400 rounded-lg transition-colors disabled:opacity-50"
            >
              {saving
                ? <><span className="w-3 h-3 border-2 border-black/30 border-t-black rounded-full animate-spin" />Saving…</>
                : <><Save className="w-3 h-3" />Save Settings</>
              }
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}

function Section({ title, icon: Icon, iconColor, children }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
        <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">{title}</h3>
      </div>
      {children}
    </div>
  )
}

function Field({ label, hint, type = 'text', placeholder, value, onChange }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-semibold text-slate-300">{label}</label>
      {hint && <p className="text-[11px] text-slate-600 leading-relaxed">{hint}</p>}
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-card border border-border rounded-lg px-3 py-2.5 text-sm text-slate-300 placeholder-slate-600 outline-none focus:border-accent/50 transition-colors"
      />
    </div>
  )
}

function ToggleField({ label, hint, checked, onChange }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="text-xs font-semibold text-slate-300">{label}</p>
        {hint && <p className="text-[11px] text-slate-600 mt-0.5 leading-relaxed">{hint}</p>}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative w-10 h-5 rounded-full border transition-all duration-200 shrink-0 ${
          checked ? 'bg-accent border-accent' : 'bg-slate-800 border-slate-700'
        }`}
      >
        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all duration-200 ${
          checked ? 'left-5' : 'left-0.5'
        }`} />
      </button>
    </div>
  )
}

function SelectField({ label, value, options, onChange }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <label className="text-xs font-semibold text-slate-300 shrink-0">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-card border border-border rounded-lg px-3 py-2 text-sm text-slate-300 outline-none focus:border-accent/50 transition-colors cursor-pointer"
      >
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

const CURL_EXAMPLE = `curl -X POST http://127.0.0.1:8000/api/webhooks/logs \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "my-server",
    "log_text": "ERROR: Connection refused to db:5432"
  }'`

const PYTHON_EXAMPLE = `import requests
requests.post("http://127.0.0.1:8000/api/webhooks/logs", json={
    "source": "my-server",
    "log_text": "ERROR: OOM killer invoked on pod worker-7",
})`

function WebhookDocs() {
  const [copied, setCopied] = useState(null)
  const [tab, setTab]       = useState('curl')

  const examples = { curl: CURL_EXAMPLE, python: PYTHON_EXAMPLE }

  function handleCopy() {
    navigator.clipboard.writeText(examples[tab]).then(() => {
      setCopied(tab)
      setTimeout(() => setCopied(null), 2000)
    })
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] text-slate-500 leading-relaxed">
        POST logs to this endpoint from any server, CI pipeline, or script.
        The API returns <code className="font-mono bg-slate-800 px-1 rounded text-slate-300">202 Accepted</code> immediately and
        processes the log with Gemma in the background.
      </p>

      {/* Tab bar */}
      <div className="flex border-b border-border">
        {['curl', 'python'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-1.5 text-xs font-semibold transition-colors ${
              tab === t
                ? 'text-accent border-b-2 border-accent'
                : 'text-slate-600 hover:text-slate-400'
            }`}
          >
            {t === 'curl' ? 'cURL' : 'Python'}
          </button>
        ))}
      </div>

      {/* Code block */}
      <div className="relative rounded-lg bg-slate-950 border border-slate-800 overflow-hidden">
        <pre className="p-4 text-xs font-mono text-cyan-300 leading-relaxed overflow-x-auto whitespace-pre">
          {examples[tab]}
        </pre>
        <button
          onClick={handleCopy}
          className="absolute top-2 right-2 flex items-center gap-1.5 px-2.5 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-xs text-slate-400 hover:text-white transition-colors"
        >
          {copied === tab
            ? <><Check className="w-3 h-3 text-accent" />Copied!</>
            : <><Copy className="w-3 h-3" />Copy</>
          }
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-[10px]">
        <span className="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-slate-400 font-mono">POST /api/webhooks/logs</span>
        <span className="px-2 py-1 rounded bg-green-500/10 border border-green-500/30 text-green-400">202 Accepted</span>
        <span className="px-2 py-1 rounded bg-blue-500/10 border border-blue-500/30 text-blue-400">Background AI</span>
      </div>
    </div>
  )
}

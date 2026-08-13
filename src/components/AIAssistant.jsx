import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  Send,
  Bot,
  User,
  Zap,
  AlertTriangle,
  Check,
  X,
  ChevronDown,
  Clock,
  Trash2,
  Plus,
  Settings,
  RefreshCw,
  Cpu,
  MessageSquare,
  Shield,
  Play,
  StopCircle,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
import { useToast } from './ToastNotification'

function formatRelativeTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const sec = Math.floor((Date.now() - d.getTime()) / 1000)
  if (sec < 60) return 'just now'
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`
  if (sec < 604800) return `${Math.floor(sec / 86400)}d ago`
  return d.toLocaleDateString()
}

function splitBold(line) {
  const parts = line.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) {
      return (
        <strong key={i} className="font-semibold text-slate-100">
          {p.slice(2, -2)}
        </strong>
      )
    }
    return <span key={i}>{p}</span>
  })
}

function AssistantMarkdown({ text }) {
  if (!text) return null
  const blocks = text.split(/\n{2,}/)
  return (
    <div className="text-sm text-slate-200 space-y-2">
      {blocks.map((block, bi) => (
        <div key={bi} className="space-y-1">
          {block.split('\n').map((line, li) => (
            <p key={li} className="whitespace-pre-wrap break-words leading-relaxed">
              {splitBold(line)}
            </p>
          ))}
        </div>
      ))}
    </div>
  )
}

export default function AIAssistant() {
  const { authFetch } = useAuth()
  const { showToast } = useToast()
  const { role } = useAuth()
  const isAdmin = role === 'Admin'
  const { activeWorkspace, currentEnvironment, refreshApprovals } = usePortalContext()

  const [conversations, setConversations] = useState([])
  const [activeConversation, setActiveConversation] = useState(null)
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [selectedModel, setSelectedModel] = useState('gpt-4o-mini')
  const [availableModels, setAvailableModels] = useState([])
  const [pendingExecutions, setPendingExecutions] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [contextPanel, setContextPanel] = useState(false)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [toolCount, setToolCount] = useState(0)
  const [expandedParamsId, setExpandedParamsId] = useState(null)
  const [rejectingId, setRejectingId] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  // Inline, non-blocking alerts from the latest AI response `errors` field.
  const [responseErrors, setResponseErrors] = useState([])

  const messagesEndRef = useRef(null)
  const modelMenuRef = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, isLoading, scrollToBottom])

  const loadModels = useCallback(async () => {
    try {
      const res = await authFetch('/api/llm/status')
      if (!res.ok) return
      const data = await res.json()
      const models = Array.isArray(data.models) ? data.models : []
      setAvailableModels(models)
      const def = (data.default_model || '').trim()
      if (def) {
        setSelectedModel((prev) => {
          if (models.some((m) => m.id === prev)) return prev
          return def
        })
      }
    } catch {
      setAvailableModels([])
    }
  }, [authFetch])

  const loadConversations = useCallback(async () => {
    try {
      const res = await authFetch('/api/ai/conversations')
      if (!res.ok) return
      setConversations(await res.json())
    } catch {
      setConversations([])
    }
  }, [authFetch])

  const loadPending = useCallback(async () => {
    if (!isAdmin) {
      setPendingExecutions([])
      return
    }
    try {
      const res = await authFetch('/api/ai/executions/pending')
      if (res.status === 403) {
        setPendingExecutions([])
        return
      }
      if (!res.ok) return
      setPendingExecutions(await res.json())
    } catch {
      setPendingExecutions([])
    }
  }, [authFetch, isAdmin])

  const refreshWorkspaceContext = useCallback(async () => {
    try {
      const ctxRes = await authFetch('/api/context')
      if (ctxRes.ok) {
        const data = await ctxRes.json()
        window.dispatchEvent(
          new CustomEvent('context-changed', {
            detail: { context: data, environment: data.active_environment, source: 'ai-assistant' },
          })
        )
      }
      if (activeWorkspace?.id) {
        const wr = await authFetch(`/api/workspaces/${encodeURIComponent(activeWorkspace.id)}`)
        if (wr.ok) {
          const w = await wr.json()
          const n = Array.isArray(w.tools) ? w.tools.length : 0
          setToolCount(n)
        }
      } else {
        setToolCount(0)
      }
      showToast('Context refreshed', 'success')
    } catch {
      showToast('Refresh failed', 'error')
    }
  }, [authFetch, activeWorkspace?.id, showToast])

  useEffect(() => {
    void loadModels()
    void loadConversations()
  }, [loadModels, loadConversations])

  useEffect(() => {
    void loadPending()
    if (!isAdmin) return undefined
    const t = setInterval(() => void loadPending(), 30000)
    return () => clearInterval(t)
  }, [loadPending, isAdmin])

  useEffect(() => {
    if (activeWorkspace?.id) {
      void (async () => {
        try {
          const wr = await authFetch(`/api/workspaces/${encodeURIComponent(activeWorkspace.id)}`)
          if (wr.ok) {
            const w = await wr.json()
            setToolCount(Array.isArray(w.tools) ? w.tools.length : 0)
          }
        } catch {
          setToolCount(0)
        }
      })()
    } else {
      setToolCount(0)
    }
  }, [authFetch, activeWorkspace?.id])

  useEffect(() => {
    function onDocClick(e) {
      if (modelMenuRef.current && !modelMenuRef.current.contains(e.target)) {
        setModelMenuOpen(false)
      }
    }
    document.addEventListener('click', onDocClick)
    return () => document.removeEventListener('click', onDocClick)
  }, [])

  const mergeMessagesWithPending = useCallback((rawMessages, pendingList) => {
    const byMsg = {}
    for (const pe of pendingList || []) {
      if (pe.status === 'pending_approval' && pe.message_id) {
        byMsg[pe.message_id] = pe
      }
    }
    return rawMessages.map((m) => ({
      ...m,
      pendingExecution: m.role === 'assistant' ? byMsg[m.id] || null : null,
    }))
  }, [])

  const openConversation = useCallback(
    async (id) => {
      try {
        const res = await authFetch(`/api/ai/conversations/${encodeURIComponent(id)}`)
        if (!res.ok) throw new Error(await res.text())
        const data = await res.json()
        setActiveConversation(data.conversation?.id || id)
        const raw = (data.messages || []).map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          created_at: m.created_at || null,
        }))
        setMessages(mergeMessagesWithPending(raw, data.pending_executions))
      } catch (e) {
        showToast(e.message || 'Failed to load conversation', 'error')
      }
    },
    [authFetch, mergeMessagesWithPending, showToast]
  )

  const startNewChat = useCallback(() => {
    setActiveConversation(null)
    setMessages([])
    setInputValue('')
    setResponseErrors([])
    setSidebarOpen(true)
  }, [])

  const deleteConversation = useCallback(
    async (id, e) => {
      e?.stopPropagation()
      if (!window.confirm('Delete this conversation?')) return
      try {
        const res = await authFetch(`/api/ai/conversations/${encodeURIComponent(id)}`, {
          method: 'DELETE',
        })
        if (!res.ok) throw new Error(await res.text())
        showToast('Conversation deleted', 'success')
        if (activeConversation === id) startNewChat()
        await loadConversations()
        await loadPending()
        await refreshApprovals()
      } catch (err) {
        showToast(err.message || 'Delete failed', 'error')
      }
    },
    [authFetch, activeConversation, loadConversations, loadPending, refreshApprovals, showToast, startNewChat]
  )

  const sendMessage = useCallback(async () => {
    const text = inputValue.trim()
    if (!text || isLoading) return
    setIsLoading(true)
    setInputValue('')
    setResponseErrors([])

    const optimisticId = `local-user-${Date.now()}`
    setMessages((prev) => [
      ...prev,
      {
        id: optimisticId,
        role: 'user',
        content: text,
        created_at: new Date().toISOString(),
      },
    ])

    try {
      const res = await authFetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          conversation_id: activeConversation || undefined,
          workspace_id: activeWorkspace?.id || undefined,
          environment: currentEnvironment || 'development',
          model: selectedModel,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const cid = data.conversation_id
      setActiveConversation(cid)
      setResponseErrors(Array.isArray(data.errors) ? data.errors : [])
      // Prefer structured `messages` from Phase 1.1 when present.
      if (Array.isArray(data.messages) && data.messages.length > 0) {
        const raw = data.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          created_at: m.created_at || null,
        }))
        setMessages(mergeMessagesWithPending(raw, data.pending_executions))
      } else {
        await openConversation(cid)
      }
      await loadConversations()
      await loadPending()
      await refreshApprovals()
    } catch (e) {
      setMessages((prev) => prev.filter((m) => m.id !== optimisticId))
      setInputValue(text)
      showToast(e.message || 'Chat failed', 'error')
    } finally {
      setIsLoading(false)
    }
  }, [
    inputValue,
    isLoading,
    authFetch,
    activeConversation,
    activeWorkspace?.id,
    currentEnvironment,
    selectedModel,
    openConversation,
    mergeMessagesWithPending,
    loadConversations,
    loadPending,
    refreshApprovals,
    showToast,
  ])

  const approveExec = useCallback(
    async (execId, opts = {}) => {
      try {
        const res = await authFetch(`/api/ai/executions/${encodeURIComponent(execId)}/approve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ approved_by: opts.approvedBy || 'admin' }),
        })
        if (!res.ok) throw new Error(await res.text())
        showToast('Execution approved', 'success')
        setMessages((prev) =>
          prev.map((m) =>
            m.pendingExecution?.id === execId ? { ...m, pendingExecution: null } : m
          )
        )
        await loadPending()
        await refreshApprovals()
        if (opts.reloadConversation && activeConversation) {
          await openConversation(activeConversation)
        }
      } catch (e) {
        showToast(e.message || 'Approve failed', 'error')
      }
    },
    [authFetch, loadPending, refreshApprovals, openConversation, activeConversation, showToast]
  )

  const rejectExec = useCallback(
    async (execId) => {
      try {
        const res = await authFetch(`/api/ai/executions/${encodeURIComponent(execId)}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rejected_by: 'admin', reason: rejectReason || '' }),
        })
        if (!res.ok) throw new Error(await res.text())
        showToast('Execution rejected', 'success')
        setRejectingId(null)
        setRejectReason('')
        setMessages((prev) =>
          prev.map((m) =>
            m.pendingExecution?.id === execId ? { ...m, pendingExecution: null } : m
          )
        )
      await loadPending()
      await refreshApprovals()
    } catch (e) {
      showToast(e.message || 'Reject failed', 'error')
    }
  },
    [authFetch, loadPending, refreshApprovals, rejectReason, showToast]
  )

  const currentModelLabel = useMemo(() => {
    const m = availableModels.find((x) => x.id === selectedModel)
    return m?.label || selectedModel
  }, [availableModels, selectedModel])

  const providerIcon = (provider) => {
    if (provider === 'anthropic') return <Zap className="w-4 h-4 text-amber-400" />
    if (provider === 'openai' || provider === 'openai_compatible') {
      return <Settings className="w-4 h-4 text-emerald-400" />
    }
    return <Cpu className="w-4 h-4 text-violet-400" />
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void sendMessage()
    }
  }

  const quickPrompts = [
    'Show workspace health',
    'List pending alerts',
    'Summarize recent incidents',
    'Check tool connectivity',
    "What's deployed in production?",
  ]

  return (
    <div className="flex flex-col flex-1 min-h-0 -mx-8 -my-8">
      <div className="flex flex-1 min-h-0 max-h-[calc(100vh-9rem)] border-y border-border bg-slate-950/30">
        {/* Left — conversations */}
        <aside
          className={`${
            sidebarOpen ? 'flex' : 'hidden'
          } md:flex w-[240px] shrink-0 flex-col border-r border-border bg-slate-950/50`}
        >
          <div className="flex items-center justify-between gap-2 px-3 py-3 border-b border-border">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Conversations</span>
            <button
              type="button"
              onClick={() => startNewChat()}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-blue-600/90 hover:bg-blue-500 text-white text-xs font-semibold"
            >
              <Plus className="w-3.5 h-3.5" /> New
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {conversations.length === 0 ? (
              <div className="px-2 py-8 text-center text-slate-500 text-sm">
                <p>No conversations yet</p>
                <button
                  type="button"
                  onClick={() => startNewChat()}
                  className="mt-3 text-blue-400 hover:text-blue-300 text-xs font-semibold"
                >
                  Start chatting →
                </button>
              </div>
            ) : (
              conversations.map((c) => {
                const active = activeConversation === c.id
                return (
                  <div
                    key={c.id}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void openConversation(c.id)
                    }}
                    onClick={() => void openConversation(c.id)}
                    className={`group relative flex items-start gap-2 rounded-lg px-2 py-2 text-left cursor-pointer border ${
                      active
                        ? 'bg-blue-600/20 border-blue-500/40'
                        : 'border-transparent hover:bg-slate-800/60'
                    }`}
                  >
                    <MessageSquare className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-slate-200 truncate">{c.title || 'Untitled'}</p>
                      <p className="text-[10px] text-slate-500 flex items-center gap-1 mt-0.5">
                        <Clock className="w-3 h-3" />
                        {formatRelativeTime(c.updated_at)}
                      </p>
                    </div>
                    <button
                      type="button"
                      title="Delete"
                      onClick={(e) => void deleteConversation(c.id, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-950/50 text-slate-400 hover:text-red-300"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )
              })
            )}
          </div>
          <button
            type="button"
            className="md:hidden m-2 text-xs text-slate-500 border border-border rounded-lg py-1"
            onClick={() => setSidebarOpen(false)}
          >
            Hide sidebar
          </button>
        </aside>

        {/* Center — chat */}
        <div className="flex-1 flex flex-col min-w-0 min-h-0">
          <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-border bg-slate-900/40">
            <div className="flex items-center gap-2 min-w-0">
              <button
                type="button"
                className="md:hidden p-1 rounded border border-border text-slate-400"
                onClick={() => setSidebarOpen(true)}
              >
                <MessageSquare className="w-4 h-4" />
              </button>
              <Bot className="w-5 h-5 text-blue-400 shrink-0" />
              <span className="font-semibold text-white truncate">AI Assistant</span>
            </div>
            <div className="relative" ref={modelMenuRef}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  setModelMenuOpen((v) => !v)
                }}
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-slate-900 text-sm text-slate-200 hover:bg-slate-800 max-w-[200px]"
              >
                <span className="truncate">{currentModelLabel}</span>
                <ChevronDown className="w-4 h-4 shrink-0 text-slate-500" />
              </button>
              {modelMenuOpen && (
                <div className="absolute right-0 top-full mt-1 z-50 w-72 rounded-xl border border-border bg-slate-950 shadow-xl py-1 max-h-64 overflow-y-auto">
                  {availableModels.map((m) => (
                    <button
                      key={m.id}
                      type="button"
                      disabled={!m.available}
                      onClick={() => {
                        if (m.available) {
                          setSelectedModel(m.id)
                          setModelMenuOpen(false)
                        }
                      }}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-left text-sm ${
                        m.available
                          ? 'hover:bg-slate-800 text-slate-200'
                          : 'text-slate-600 cursor-not-allowed'
                      } ${selectedModel === m.id ? 'bg-slate-800/80' : ''}`}
                    >
                      {providerIcon(m.provider)}
                      <span className="flex-1 truncate">{m.label}</span>
                      {!m.available && (
                        <span className="text-[10px] text-slate-500 shrink-0">Not configured</span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {responseErrors.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {responseErrors.map((err, i) => (
                  <span
                    key={`${err.code || 'err'}-${i}`}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-amber-500/10 border border-amber-500/30 text-amber-200"
                  >
                    <AlertTriangle className="w-3 h-3 shrink-0" />
                    {err.message || err.code || 'AI warning'}
                    <button
                      type="button"
                      aria-label="Dismiss"
                      onClick={() =>
                        setResponseErrors((prev) => prev.filter((_, idx) => idx !== i))
                      }
                      className="ml-0.5 text-amber-400/70 hover:text-amber-200"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            {messages.length === 0 && !isLoading ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm py-12">
                <Bot className="w-12 h-12 mb-3 opacity-40" />
                <p>Ask about infrastructure, tools, or incidents.</p>
              </div>
            ) : (
              messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
                >
                  <div
                    className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                      m.role === 'user' ? 'bg-blue-600' : 'bg-slate-700'
                    }`}
                  >
                    {m.role === 'user' ? (
                      <User className="w-4 h-4 text-white" />
                    ) : (
                      <Bot className="w-4 h-4 text-slate-200" />
                    )}
                  </div>
                  <div
                    className={`max-w-[85%] flex flex-col gap-1 ${
                      m.role === 'user' ? 'items-end' : 'items-start'
                    }`}
                  >
                    <div
                      className={`rounded-2xl px-4 py-3 ${
                        m.role === 'user'
                          ? 'bg-blue-600 text-white rounded-br-md'
                          : 'bg-slate-800/90 border border-border text-slate-100 rounded-bl-md'
                      }`}
                    >
                      {m.role === 'user' ? (
                        <p className="text-sm whitespace-pre-wrap break-words">{m.content}</p>
                      ) : (
                        <AssistantMarkdown text={m.content} />
                      )}
                      {m.role === 'assistant' && m.pendingExecution && isAdmin && (
                        <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-950/30 p-3 space-y-2">
                          <div className="flex items-center gap-2 text-amber-200 text-xs font-semibold">
                            <AlertTriangle className="w-4 h-4" />
                            Action requires approval
                            {m.pendingExecution.requires_hitl && (
                              <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-[10px] uppercase">
                                HITL
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-slate-300">
                            Tool: <span className="font-mono">{m.pendingExecution.tool_id}</span> | Action:{' '}
                            <span className="font-mono">{m.pendingExecution.action}</span>
                            {m.pendingExecution.status && (
                              <>
                                {' '}
                                | Status:{' '}
                                <span className="font-mono">{m.pendingExecution.status}</span>
                              </>
                            )}
                          </p>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => void approveExec(m.pendingExecution.id)}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
                            >
                              <Check className="w-3.5 h-3.5" /> Approve
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setRejectingId(m.pendingExecution.id)
                                setRejectReason('')
                              }}
                              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-red-900/60 hover:bg-red-800 text-red-100 text-xs font-semibold"
                            >
                              <X className="w-3.5 h-3.5" /> Reject
                            </button>
                          </div>
                          {rejectingId === m.pendingExecution.id && (
                            <div className="flex flex-col gap-2 pt-1">
                              <input
                                value={rejectReason}
                                onChange={(e) => setRejectReason(e.target.value)}
                                placeholder="Reason (optional)"
                                className="text-xs px-2 py-1 rounded bg-slate-900 border border-border text-white"
                              />
                              <button
                                type="button"
                                onClick={() => void rejectExec(m.pendingExecution.id)}
                                className="self-start text-xs text-red-300 underline"
                              >
                                Confirm reject
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    {m.created_at && (
                      <span className="text-[10px] text-slate-500 px-1">
                        {formatRelativeTime(m.created_at)}
                        <span className="mx-1 opacity-40">·</span>
                        {new Date(m.created_at).toLocaleTimeString([], {
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
            {isLoading && (
              <div className="flex items-center gap-2 text-slate-500 text-sm pl-11">
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce"
                    style={{ animationDelay: '0.15s' }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce"
                    style={{ animationDelay: '0.3s' }}
                  />
                </span>
                typing...
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="border-t border-border p-3 bg-slate-900/50">
            <div className="flex gap-2 items-end max-w-4xl mx-auto">
              <textarea
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={onKeyDown}
                disabled={isLoading}
                rows={1}
                placeholder="Ask about your infrastructure..."
                className="flex-1 min-h-[44px] max-h-32 resize-none rounded-xl border border-border bg-slate-950 px-3 py-2.5 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40 disabled:opacity-50"
              />
              <button
                type="button"
                disabled={isLoading || !inputValue.trim()}
                onClick={() => void sendMessage()}
                className="shrink-0 inline-flex items-center justify-center w-11 h-11 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:pointer-events-none text-white"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            <p className="text-[10px] text-slate-500 text-center mt-2 max-w-4xl mx-auto">
              Enter to send · Shift+Enter for newline
            </p>
          </div>
        </div>

        {/* Right — context + HITL (drawer on small screens) */}
        <aside
          className={`flex flex-col w-[300px] shrink-0 border-l border-border bg-slate-950/95 lg:bg-slate-950/40 overflow-y-auto shadow-2xl lg:shadow-none
            fixed inset-y-0 right-0 z-40 transition-transform duration-200 lg:relative lg:z-0 lg:translate-x-0
            ${contextPanel ? 'translate-x-0' : 'translate-x-full lg:translate-x-0 lg:flex'}`}
        >
          <div className="lg:hidden flex justify-end p-2 border-b border-border">
            <button
              type="button"
              onClick={() => setContextPanel(false)}
              className="text-xs text-slate-500"
            >
              Close panel
            </button>
          </div>

          <section className="p-4 border-b border-border space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
              <Play className="w-3.5 h-3.5" /> Active Context
            </h3>
            <ul className="text-sm text-slate-300 space-y-2">
              <li>
                🗂️ Workspace:{' '}
                <span className="text-white font-medium">{activeWorkspace?.name || 'None'}</span>
              </li>
              <li>
                🌍 Environment:{' '}
                <span className="text-white font-medium">{currentEnvironment || '—'}</span>
              </li>
              <li>
                🔧 Tools:{' '}
                <span className="text-white font-medium">{toolCount} connected</span>
              </li>
            </ul>
            <button
              type="button"
              onClick={() => void refreshWorkspaceContext()}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-xs font-semibold text-slate-300 hover:bg-slate-800"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </section>

          <section className="p-4 border-b border-border flex-1 min-h-0 flex flex-col">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-3">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              Pending Approvals
              {pendingExecutions.length > 0 && (
                <span className="ml-auto px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-200 text-[10px] font-bold">
                  {pendingExecutions.length}
                </span>
              )}
            </h3>
            {!isAdmin ? (
              <p className="text-xs text-slate-500">Pending approvals are visible to administrators.</p>
            ) : pendingExecutions.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-slate-500 text-sm text-center">
                <Shield className="w-10 h-10 mb-2 opacity-40" />
                No pending approvals
              </div>
            ) : (
              <div className="space-y-3 overflow-y-auto flex-1 pr-1">
                {pendingExecutions.map((ex) => {
                  const ctx = ex.conversation_context
                  const env = ctx?.environment || '—'
                  const prod = String(env).toLowerCase() === 'production'
                  return (
                    <div
                      key={ex.id}
                      className="rounded-lg border border-border bg-slate-900/60 p-3 space-y-2 text-xs"
                    >
                      <div className="font-semibold text-slate-200">
                        {ex.tool_id} → {ex.action}
                      </div>
                      <span
                        className={`inline-block px-2 py-0.5 rounded-md border text-[10px] font-semibold uppercase ${
                          prod
                            ? 'border-red-500/50 text-red-200 bg-red-950/40'
                            : 'border-slate-600 text-slate-400'
                        }`}
                      >
                        {env}
                      </span>
                      <button
                        type="button"
                        onClick={() => setExpandedParamsId((id) => (id === ex.id ? null : ex.id))}
                        className="text-blue-400 hover:text-blue-300"
                      >
                        {expandedParamsId === ex.id ? 'Hide parameters' : 'Show parameters'}
                      </button>
                      {expandedParamsId === ex.id && (
                        <pre className="text-[10px] bg-slate-950 p-2 rounded overflow-x-auto text-slate-400">
                          {JSON.stringify(ex.parameters || {}, null, 2)}
                        </pre>
                      )}
                      {ctx?.id && (
                        <button
                          type="button"
                          onClick={() => void openConversation(ctx.id)}
                          className="text-blue-400 hover:underline"
                        >
                          Open conversation
                        </button>
                      )}
                      <div className="flex gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => void approveExec(ex.id, { reloadConversation: true })}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-emerald-600 text-white font-semibold"
                        >
                          <Check className="w-3.5 h-3.5" /> Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRejectingId(ex.id)
                            setRejectReason('')
                          }}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-red-900/50 text-red-100 font-semibold"
                        >
                          <X className="w-3.5 h-3.5" /> Reject
                        </button>
                      </div>
                      {rejectingId === ex.id && (
                        <div className="space-y-2 border-t border-border pt-2">
                          <input
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            placeholder="Rejection reason"
                            className="w-full text-xs px-2 py-1 rounded bg-slate-950 border border-border text-white"
                          />
                          <button
                            type="button"
                            onClick={() => void rejectExec(ex.id)}
                            className="text-xs text-red-300 font-semibold"
                          >
                            Confirm reject
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          <section className="p-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-2">
              <StopCircle className="w-3.5 h-3.5 opacity-70" /> Quick Actions
            </h3>
            <div className="flex flex-wrap gap-2">
              {quickPrompts.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setInputValue((prev) => (prev ? `${prev}\n${q}` : q))}
                  className="px-2 py-1.5 rounded-full border border-border bg-slate-900/80 text-[11px] text-slate-300 hover:border-blue-500/50 hover:text-white"
                >
                  {q}
                </button>
              ))}
            </div>
          </section>
        </aside>

        {/* Mobile — open context / HITL drawer */}
        <div className="lg:hidden fixed bottom-20 right-4 z-50 flex flex-col gap-2">
          {!contextPanel && (
            <button
              type="button"
              onClick={() => setContextPanel(true)}
              className="p-3 rounded-full bg-slate-800 border border-border text-slate-200 shadow-lg"
              title="Context & approvals"
            >
              <Shield className="w-5 h-5" />
            </button>
          )}
        </div>
        {contextPanel && (
          <button
            type="button"
            aria-label="Close context panel"
            className="lg:hidden fixed inset-0 z-30 bg-black/50"
            onClick={() => setContextPanel(false)}
          />
        )}
      </div>
    </div>
  )
}

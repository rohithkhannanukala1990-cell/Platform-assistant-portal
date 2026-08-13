/**
 * Floating SRE chat widget. Uses /api/ai/chat (Phase 1.1 structured response).
 * Full-page agent UI lives in AIAssistant.jsx (/ai-assistant).
 */
import { useState, useRef, useEffect } from 'react'
import {
  MessageSquare, X, Send, Bot, User,
  Loader2, AlertCircle, Sparkles, AlertTriangle,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'

const SUGGESTIONS = [
  'How many open incidents do I have?',
  'What is the most critical issue right now?',
  'Show me a summary of the latest incident.',
  'Are there any unread notifications?',
]

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-2.5">
      <div className="flex items-center justify-center w-7 h-7 rounded-full bg-accent/20 border border-accent/30 shrink-0">
        <Bot className="w-3.5 h-3.5 text-accent" />
      </div>
      <div className="flex items-center gap-1.5 px-4 py-3 rounded-2xl rounded-bl-sm bg-card border border-border">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '0ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '150ms' }} />
        <span className="w-1.5 h-1.5 rounded-full bg-slate-500 animate-bounce" style={{ animationDelay: '300ms' }} />
        <span className="ml-1 text-[11px] text-slate-500">typing...</span>
      </div>
    </div>
  )
}

function MessageBubble({ role, content, error, createdAt }) {
  const isUser = role === 'user'
  return (
    <div className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
      <div className={`flex items-end gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
        <div className={`flex items-center justify-center w-7 h-7 rounded-full shrink-0
          ${isUser
            ? 'bg-accent/20 border border-accent/30'
            : error ? 'bg-red-500/20 border border-red-500/30' : 'bg-slate-700 border border-slate-600'
          }`}
        >
          {isUser
            ? <User className="w-3.5 h-3.5 text-accent" />
            : error
              ? <AlertCircle className="w-3.5 h-3.5 text-red-400" />
              : <Bot className="w-3.5 h-3.5 text-slate-300" />
          }
        </div>

        <div className={`max-w-[78%] px-4 py-2.5 text-sm leading-relaxed
          ${isUser
            ? 'bg-accent/15 border border-accent/25 text-slate-100 rounded-2xl rounded-br-sm'
            : error
              ? 'bg-red-500/10 border border-red-500/25 text-red-300 rounded-2xl rounded-bl-sm'
              : 'bg-card border border-border text-slate-200 rounded-2xl rounded-bl-sm'
          }`}
        >
          {content}
        </div>
      </div>
      {createdAt && (
        <span className={`text-[10px] text-slate-600 px-9 ${isUser ? 'text-right' : ''}`}>
          {formatTime(createdAt)}
        </span>
      )}
    </div>
  )
}

export default function ChatBot() {
  const { authFetch } = useAuth()
  const { activeWorkspace, currentEnvironment } = usePortalContext()
  const [open, setOpen] = useState(false)
  const [conversationId, setConversationId] = useState(null)
  const [messages, setMsgs] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: "Hi! I'm your SRE Platform Assistant. I have live context about your incidents, infrastructure, and notifications. Ask me anything about your platform's current state.",
      created_at: new Date().toISOString(),
    },
  ])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [responseErrors, setResponseErrors] = useState([])
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading, responseErrors])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150)
  }, [open])

  async function sendMessage(text) {
    const userText = text ?? input.trim()
    if (!userText || isLoading) return
    setInput('')
    setResponseErrors([])
    const optimisticId = `local-${Date.now()}`
    setMsgs((prev) => [
      ...prev,
      {
        id: optimisticId,
        role: 'user',
        content: userText,
        created_at: new Date().toISOString(),
      },
    ])
    setIsLoading(true)

    try {
      const res = await authFetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userText,
          conversation_id: conversationId || undefined,
          workspace_id: activeWorkspace?.id || undefined,
          environment: currentEnvironment || 'development',
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail ?? 'Backend error')

      if (data.conversation_id) setConversationId(data.conversation_id)

      const errs = Array.isArray(data.errors) ? data.errors : []
      setResponseErrors(errs)

      if (Array.isArray(data.messages) && data.messages.length > 0) {
        setMsgs(
          data.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            created_at: m.created_at || null,
          }))
        )
      } else {
        setMsgs((prev) => [
          ...prev,
          {
            id: data.message_id || `asst-${Date.now()}`,
            role: 'assistant',
            content: data.response || 'No response.',
            created_at: new Date().toISOString(),
          },
        ])
      }
    } catch (err) {
      setMsgs((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: `Error: ${err.message}`,
          error: true,
          created_at: new Date().toISOString(),
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`fixed bottom-6 right-6 z-[45] flex items-center justify-center w-14 h-14 rounded-full shadow-2xl
          border transition-all duration-200 group
          ${open
            ? 'bg-slate-800 border-slate-600 rotate-90'
            : 'bg-accent border-accent/50 hover:bg-green-400 hover:scale-110 glow-green'
          }`}
        title="Platform Assistant"
      >
        {open
          ? <X className="w-5 h-5 text-slate-300" />
          : <MessageSquare className="w-5 h-5 text-black" />
        }
      </button>

      <div
        className={`fixed bottom-24 right-6 z-[45] flex flex-col w-96 rounded-2xl border border-border bg-surface shadow-2xl
          transition-all duration-300 origin-bottom-right
          ${open ? 'opacity-100 scale-100 pointer-events-auto' : 'opacity-0 scale-95 pointer-events-none'}`}
        style={{ height: '540px' }}
      >
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-border bg-sidebar rounded-t-2xl shrink-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-accent/20 border border-accent/30">
            <Sparkles className="w-4 h-4 text-accent" />
          </div>
          <div>
            <p className="text-sm font-bold text-white">Platform Assistant</p>
            <p className="text-[10px] text-slate-500 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse inline-block" />
              Live system context · AI-powered
            </p>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="ml-auto p-1.5 rounded-lg hover:bg-card transition-colors text-slate-500 hover:text-white"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-4">
          {responseErrors.length > 0 && (
            <div className="flex flex-col gap-1.5">
              {responseErrors.map((err, i) => (
                <div
                  key={`${err.code || 'e'}-${i}`}
                  className="flex items-start gap-2 px-3 py-2 rounded-lg border border-amber-500/30 bg-amber-500/10 text-[11px] text-amber-200"
                >
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span className="flex-1 leading-snug">
                    {err.message || err.code || 'Action parsing failed; actions not executed'}
                  </span>
                  <button
                    type="button"
                    aria-label="Dismiss alert"
                    onClick={() =>
                      setResponseErrors((prev) => prev.filter((_, idx) => idx !== i))
                    }
                    className="text-amber-400/70 hover:text-amber-200"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {messages.map((m) => (
            <MessageBubble
              key={m.id || `${m.role}-${m.content?.slice(0, 12)}`}
              role={m.role}
              content={m.content}
              error={m.error}
              createdAt={m.created_at}
            />
          ))}
          {isLoading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {messages.length <= 1 && !isLoading && (
          <div className="px-4 pb-3 flex flex-wrap gap-1.5 shrink-0">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                className="text-[11px] text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-500 rounded-full px-3 py-1 bg-slate-900 transition-colors"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2 px-3 pb-3 pt-2 border-t border-border shrink-0">
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Ask about your platform..."
            className="flex-1 bg-card border border-border rounded-xl px-3 py-2.5 text-sm text-slate-200
              placeholder-slate-600 outline-none focus:border-accent/50 resize-none leading-relaxed
              transition-colors max-h-28 overflow-y-auto"
            style={{ fieldSizing: 'content' }}
            disabled={isLoading}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isLoading}
            className="flex items-center justify-center w-9 h-9 rounded-xl bg-accent hover:bg-green-400
              disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0 mb-0.5"
          >
            {isLoading
              ? <Loader2 className="w-4 h-4 text-black animate-spin" />
              : <Send className="w-4 h-4 text-black" />
            }
          </button>
        </div>
      </div>
    </>
  )
}

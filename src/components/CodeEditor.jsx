import { useState, useCallback } from 'react'
import Editor from '@monaco-editor/react'

const LANGUAGES = ['yaml','json','python','javascript','typescript',
                   'bash','dockerfile','hcl','sql','markdown']

function detectLanguage(filename) {
  if (!filename) return 'yaml'
  const ext = filename.split('.').pop().toLowerCase()
  const map = {
    yml:'yaml', yaml:'yaml', json:'json', py:'python',
    js:'javascript', jsx:'javascript', ts:'typescript', tsx:'typescript',
    sh:'bash', bash:'bash', dockerfile:'dockerfile', tf:'hcl',
    sql:'sql', md:'markdown',
  }
  return map[ext] || 'yaml'
}

export default function CodeEditor() {
  const [code, setCode] = useState('# Start typing…\n')
  const [language, setLanguage] = useState('yaml')
  const [filename, setFilename] = useState('')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleFilenameChange = useCallback((e) => {
    const name = e.target.value
    setFilename(name)
    setLanguage(detectLanguage(name))
  }, [])

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }, [code])

  return (
    <div className={`flex flex-col bg-gray-900 text-white
      ${isFullscreen ? 'fixed inset-0 z-50'
                     : 'h-[calc(100vh-120px)] w-full rounded-xl overflow-hidden'}`}>
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
        <span className="text-gray-400 text-xs font-semibold uppercase tracking-wide">Code Editor</span>
        <div className="flex-1" />
        <input
          type="text"
          placeholder="filename.yaml"
          value={filename}
          onChange={handleFilenameChange}
          className="bg-gray-700 text-white text-sm rounded px-3 py-1 w-44 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
        <select
          value={language}
          onChange={e => setLanguage(e.target.value)}
          className="bg-gray-700 text-white text-sm rounded px-3 py-1 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        >
          {LANGUAGES.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <button
          onClick={handleCopy}
          className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded transition-colors"
        >
          {copied ? '✓ Copied' : 'Copy'}
        </button>
        <button
          onClick={() => setIsFullscreen(f => !f)}
          className="text-xs bg-gray-700 hover:bg-gray-600 text-white px-3 py-1 rounded transition-colors"
        >
          {isFullscreen ? '⊠ Exit' : '⛶ Fullscreen'}
        </button>
      </div>
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          language={language}
          value={code}
          onChange={val => setCode(val || '')}
          theme="vs-dark"
          options={{
            fontSize: 14,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            automaticLayout: true,
            tabSize: 2,
            renderLineHighlight: 'line',
            smoothScrolling: true,
            lineNumbers: 'on',
            folding: true,
          }}
        />
      </div>
    </div>
  )
}

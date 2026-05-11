import { Component } from 'react'
import { AlertTriangle } from 'lucide-react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('Portal Error:', error, errorInfo)
    this.setState({ errorInfo })
  }

  render() {
    if (this.state.hasError) {
      const msg =
        this.state.error?.message ||
        String(this.state.error || 'Unknown error')

      return (
        <div className="bg-gray-900 text-white min-h-screen flex flex-col items-center justify-center px-6">
          <AlertTriangle className="w-20 h-20 text-red-500 mb-6" strokeWidth={1.5} aria-hidden />
          <h1 className="text-2xl font-semibold mb-2">Something went wrong</h1>
          <p className="text-gray-400 mb-6 text-center max-w-md">
            The portal encountered an unexpected error.
          </p>
          <pre className="text-left text-sm text-gray-400 font-mono bg-gray-950 border border-gray-700 rounded-lg p-4 max-w-2xl w-full overflow-auto mb-8">
            {msg}
          </pre>
          <div className="flex gap-4">
            <button
              type="button"
              className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 font-medium transition-colors"
              onClick={() => window.location.reload()}
            >
              Reload Page
            </button>
            <button
              type="button"
              className="px-5 py-2 rounded-lg bg-gray-700 hover:bg-gray-600 font-medium transition-colors"
              onClick={() => {
                window.location.href = '/'
              }}
            >
              Go Home
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

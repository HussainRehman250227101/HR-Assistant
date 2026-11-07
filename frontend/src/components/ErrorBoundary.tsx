import { Component, type ErrorInfo, type ReactNode } from 'react'

/** Keeps a rendering bug on one page from blanking the whole app; no error details reach the UI. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error', error.name, info.componentStack?.split('\n')[1]?.trim())
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <div className="m-8 rounded-lg bg-white p-6 shadow ring-1 ring-rose-200">
        <h1 className="text-lg font-semibold text-rose-800">Something went wrong on this page.</h1>
        <p className="mt-1 text-sm text-slate-600">Your data is safe. Reload the page; if the problem persists, contact the administrator.</p>
        <button className="mt-4 rounded-md bg-indigo-600 px-3 py-2 text-sm text-white" onClick={() => window.location.reload()}>Reload</button>
      </div>
    )
  }
}

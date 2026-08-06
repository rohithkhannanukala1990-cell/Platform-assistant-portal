import { AlertTriangle } from 'lucide-react'

/**
 * Honest banner for UI surfaces that use sample/demo data until a live integration exists.
 */
export default function DemoPreviewBanner({
  title = 'Preview — sample data',
  children,
}) {
  return (
    <div
      data-testid="demo-preview-banner"
      role="status"
      className="flex items-start gap-2.5 px-4 py-3 rounded-xl border border-amber-500/25 bg-amber-500/5"
    >
      <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" aria-hidden />
      <div className="text-xs text-amber-200/90 leading-relaxed">
        <p className="font-semibold text-amber-200">{title}</p>
        <div className="mt-0.5">{children}</div>
      </div>
    </div>
  )
}

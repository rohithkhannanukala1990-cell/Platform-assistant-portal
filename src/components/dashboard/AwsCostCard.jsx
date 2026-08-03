import { useCallback, useEffect, useState } from 'react'
import { CloudCog, RefreshCw } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { usePortalContext } from '../../contexts/PortalContext'
import { Card } from '../ui'

export default function AwsCostCard() {
  const { authFetch } = useAuth()
  const { activeWorkspace } = usePortalContext()
  const workspaceId = activeWorkspace?.id ?? ''

  const [costData, setCostData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshKey, setRefreshKey] = useState(0)

  const fetchCostData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await authFetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: 'aws cost this month breakdown by service',
          context: { workspace_id: workspaceId },
        }),
        silentToast: true,
      })
      if (!res.ok) {
        setCostData(null)
        return
      }
      setCostData(await res.json())
    } catch {
      setCostData(null)
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId])

  useEffect(() => {
    void fetchCostData()
  }, [fetchCostData, refreshKey])

  const total = costData?.details?.total_usd || 0
  const topServices = Array.isArray(costData?.details?.top_services)
    ? costData.details.top_services.slice(0, 5)
    : []

  return (
    <Card
      title="AWS Spend — This Month"
      icon={CloudCog}
      actions={(
        <button
          type="button"
          onClick={() => {
            setCostData(null)
            setRefreshKey((k) => k + 1)
          }}
          className="p-1 rounded text-slate-500 hover:text-white transition-colors"
          title="Refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      )}
    >
      {loading && (
        <div className="space-y-2">
          <div className="h-8 bg-border/60 rounded animate-pulse" />
          <div className="h-4 bg-border/60 rounded w-2/3 animate-pulse" />
          <div className="h-4 bg-border/60 rounded w-1/2 animate-pulse" />
        </div>
      )}

      {!loading && costData && (
        <>
          <div className="text-3xl font-bold text-white mb-4">
            ${total.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
          {topServices.length > 0 && (
            <div className="space-y-2">
              {topServices.map((svc, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="text-slate-400 text-xs w-28 truncate">{svc.service}</span>
                  <div className="flex-1 bg-border/60 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full bg-accent rounded-full"
                      style={{ width: `${Math.min(((svc.usd || 0) / (total || 1)) * 100, 100)}%` }}
                    />
                  </div>
                  <span className="text-slate-300 text-xs w-16 text-right">
                    ${(svc.usd || 0).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {!loading && !costData && (
        <p className="text-slate-500 text-sm">Cost data unavailable</p>
      )}
    </Card>
  )
}

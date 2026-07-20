import { Plus, Package, Search, RefreshCw, BookOpen } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { PermissionGate } from './PermissionGate'
import useTemplates from '../hooks/useTemplates'
import TemplateCard from './templates/TemplateCard'
import TemplateFilter from './templates/TemplateFilter'
import TemplateWorkspace from './templates/TemplateWorkspace'

export default function TemplateGallery() {
  const { role } = useAuth()
  const isAdmin = role === 'Admin'
  const {
    filteredTemplates,
    isLoading,
    searchQuery,
    setSearchQuery,
    activeFilter,
    setActiveFilter,
    categories,
    loadTemplates,
  } = useTemplates()

  return (
    <TemplateWorkspace loadTemplates={loadTemplates} isAdmin={isAdmin}>
      {({ openApply, openPreview, openCreate, openEdit, duplicateTemplate, applyModalNode }) => (
        <div className="max-w-6xl mx-auto w-full space-y-8 pb-16">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
                <BookOpen className="w-7 h-7 text-indigo-400 shrink-0" aria-hidden />
                Template Gallery
              </h1>
              <p className="text-sm text-slate-400 mt-1">Reusable workspace blueprints for your team</p>
            </div>
            {isAdmin ? (
              <PermissionGate resource="templates" action="create">
                <button
                  type="button"
                  onClick={openCreate}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold shrink-0"
                >
                  <Plus className="w-5 h-5" /> New Template
                </button>
              </PermissionGate>
            ) : null}
          </div>

          <TemplateFilter
            activeFilter={activeFilter}
            onChange={setActiveFilter}
            categories={categories}
          />

          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search templates by name, description, or tags…"
              className="w-full pl-10 pr-3 py-2.5 rounded-lg bg-slate-900 border border-border text-sm text-white"
            />
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => void loadTemplates()}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-slate-400 hover:bg-slate-800 text-sm"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>

          {!isLoading && filteredTemplates.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 rounded-xl border border-dashed border-border">
              <Package className="w-14 h-14 text-slate-600 mb-4" aria-hidden />
              <p className="text-slate-400 font-medium">No templates yet</p>
              {isAdmin ? (
                <PermissionGate resource="templates" action="create">
                  <button
                    type="button"
                    onClick={openCreate}
                    className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white font-semibold text-sm"
                  >
                    <Plus className="w-4 h-4" /> Create First Template
                  </button>
                </PermissionGate>
              ) : null}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredTemplates.map((t) => (
                <TemplateCard
                  key={t.id}
                  template={t}
                  isAdmin={isAdmin}
                  onSelect={openApply}
                  onPreview={openPreview}
                  onEdit={openEdit}
                  onDuplicate={duplicateTemplate}
                />
              ))}
            </div>
          )}

          {applyModalNode}
        </div>
      )}
    </TemplateWorkspace>
  )
}

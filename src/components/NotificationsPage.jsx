import { Bell } from 'lucide-react'

export default function NotificationsPage() {
  return (
    <div className="max-w-2xl mx-auto pt-8 px-4 animate-fade-in">
      <div className="flex items-center gap-3 mb-6">
        <Bell className="w-6 h-6 text-indigo-400" />
        <h1 className="text-xl font-bold text-white">Notifications</h1>
      </div>
      <p className="text-slate-400 text-sm">
        No new notifications.
      </p>
    </div>
  )
}

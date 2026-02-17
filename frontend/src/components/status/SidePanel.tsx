import { useState } from 'react'
import { CharacterPanel } from './CharacterPanel'
import { PluginPanel } from '../plugins/PluginPanel'
import { EventPanel } from './EventPanel'
import { WorldStatePanel } from './WorldStatePanel'
import { NotificationPanel } from './NotificationPanel'
import { RuntimeSettingsPanel } from './RuntimeSettingsPanel'
import { useNotificationStore } from '../../stores/notificationStore'
import { useSessionStore } from '../../stores/sessionStore'

type Tab = 'characters' | 'plugins' | 'events' | 'alerts' | 'world' | 'settings'

export function SidePanel() {
  const [activeTab, setActiveTab] = useState<Tab>('characters')
  const currentSessionId = useSessionStore((s) => s.currentSession?.id)
  const unreadAlerts = useNotificationStore(
    (s) => s.notifications.reduce((count, item) => count + (item.unread ? 1 : 0), 0),
  )
  const markAllRead = useNotificationStore((s) => s.markAllRead)

  const tabs: { key: Tab; label: string; hint: string }[] = [
    { key: 'characters', label: 'Characters', hint: '角色状态' },
    { key: 'plugins', label: 'Plugins', hint: '插件能力' },
    { key: 'settings', label: 'Settings', hint: '运行时配置' },
    { key: 'events', label: 'Events', hint: '事件时间线' },
    { key: 'alerts', label: 'Alerts', hint: '通知与告警' },
    { key: 'world', label: 'World', hint: '世界状态' },
  ]
  const currentTab = tabs.find((tab) => tab.key === activeTab) || tabs[0]

  const handleTabClick = (tab: Tab) => {
    setActiveTab(tab)
    if (tab === 'alerts' && currentSessionId) {
      markAllRead(currentSessionId)
    }
  }

  return (
    <div className="flex-1 flex overflow-hidden min-h-0">
      <div className="w-28 shrink-0 border-r border-slate-700 bg-slate-900/40 p-2 space-y-1 overflow-y-auto">
        <p className="px-1 pb-1 text-[10px] uppercase tracking-wide text-slate-500">Panels</p>
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => handleTabClick(tab.key)}
            className={`w-full rounded-lg px-2 py-2 text-left transition-colors ${
              activeTab === tab.key
                ? 'bg-slate-800 text-slate-100 ring-1 ring-emerald-500/40'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="text-xs font-medium">{tab.label}</span>
              {tab.key === 'alerts' && unreadAlerts > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/50 text-amber-300">
                  {unreadAlerts > 99 ? '99+' : unreadAlerts}
                </span>
              )}
            </div>
            <p className="text-[10px] text-slate-500 mt-1 leading-tight">{tab.hint}</p>
          </button>
        ))}
      </div>
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <div className="px-3 py-2 border-b border-slate-700 bg-slate-900/30">
          <p className="text-sm font-medium text-slate-200">{currentTab.label}</p>
          <p className="text-xs text-slate-500 mt-0.5">{currentTab.hint}</p>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {activeTab === 'characters' && <CharacterPanel />}
          {activeTab === 'plugins' && <PluginPanel />}
          {activeTab === 'settings' && <RuntimeSettingsPanel />}
          {activeTab === 'events' && <EventPanel />}
          {activeTab === 'alerts' && <NotificationPanel />}
          {activeTab === 'world' && <WorldStatePanel />}
        </div>
      </div>
    </div>
  )
}

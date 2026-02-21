import { useState } from 'react'
import { CharacterPanel } from './CharacterPanel'
import { PluginPanel } from '../plugins/PluginPanel'
import { EventPanel } from './EventPanel'
import { WorldStatePanel } from './WorldStatePanel'
import { NotificationPanel } from './NotificationPanel'
import { RuntimeSettingsPanel } from './RuntimeSettingsPanel'
import { useNotificationStore } from '../../stores/notificationStore'
import { useSessionStore } from '../../stores/sessionStore'
import { useUiStore } from '../../stores/uiStore'

type Tab = 'characters' | 'events' | 'alerts' | 'world' | 'plugins' | 'settings'

interface TabDef { label: string; hint: string; group: 'game' | 'config' }

const tabDefs: Record<string, TabDef[]> = {
  zh: [
    { label: '角色', hint: '角色状态', group: 'game' },
    { label: '事件', hint: '事件时间线', group: 'game' },
    { label: '通知', hint: '通知与告警', group: 'game' },
    { label: '世界', hint: '世界状态', group: 'game' },
    { label: '插件', hint: '插件能力', group: 'config' },
    { label: '设置', hint: '运行时配置', group: 'config' },
  ],
  en: [
    { label: 'Characters', hint: 'Character status', group: 'game' },
    { label: 'Events', hint: 'Event timeline', group: 'game' },
    { label: 'Alerts', hint: 'Notifications', group: 'game' },
    { label: 'World', hint: 'World state', group: 'game' },
    { label: 'Plugins', hint: 'Plugin capabilities', group: 'config' },
    { label: 'Settings', hint: 'Runtime config', group: 'config' },
  ],
}

const tabKeys: Tab[] = ['characters', 'events', 'alerts', 'world', 'plugins', 'settings']

const groupLabels: Record<string, Record<string, string>> = {
  game: { zh: '游戏', en: 'Game' },
  config: { zh: '配置', en: 'Config' },
}

export function SidePanel() {
  const [activeTab, setActiveTab] = useState<Tab>('characters')
  const currentSessionId = useSessionStore((s) => s.currentSession?.id)
  const unreadAlerts = useNotificationStore(
    (s) => s.notifications.reduce((count, item) => count + (item.unread ? 1 : 0), 0),
  )
  const markAllRead = useNotificationStore((s) => s.markAllRead)
  const language = useUiStore((s) => s.language)
  const defs = tabDefs[language] ?? tabDefs.en

  const tabs = tabKeys.map((key, i) => ({ key, ...defs[i] }))
  const currentTab = tabs.find((tab) => tab.key === activeTab) || tabs[0]

  const handleTabClick = (tab: Tab) => {
    setActiveTab(tab)
    if (tab === 'alerts' && currentSessionId) {
      markAllRead(currentSessionId)
    }
  }

  const gameTabs = tabs.filter((t) => t.group === 'game')
  const configTabs = tabs.filter((t) => t.group === 'config')

  const renderTab = (tab: typeof tabs[0]) => (
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
  )

  return (
    <div className="flex-1 flex overflow-hidden min-h-0">
      <div className="w-28 shrink-0 border-r border-slate-700 bg-slate-900/40 p-2 space-y-1 overflow-y-auto">
        <p className="px-1 pb-1 text-[10px] uppercase tracking-wide text-slate-500">
          {groupLabels.game[language] ?? groupLabels.game.en}
        </p>
        {gameTabs.map(renderTab)}
        <div className="border-t border-slate-700/50 my-1.5" />
        <p className="px-1 pb-1 text-[10px] uppercase tracking-wide text-slate-500">
          {groupLabels.config[language] ?? groupLabels.config.en}
        </p>
        {configTabs.map(renderTab)}
      </div>
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden">
        <div className="px-3 py-2 border-b border-slate-700 bg-slate-900/30">
          <p className="text-sm font-medium text-slate-200">{currentTab.label}</p>
          <p className="text-xs text-slate-500 mt-0.5">{currentTab.hint}</p>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {activeTab === 'characters' && <CharacterPanel />}
          {activeTab === 'events' && <EventPanel />}
          {activeTab === 'alerts' && <NotificationPanel />}
          {activeTab === 'world' && <WorldStatePanel />}
          {activeTab === 'plugins' && <PluginPanel />}
          {activeTab === 'settings' && <RuntimeSettingsPanel />}
        </div>
      </div>
    </div>
  )
}

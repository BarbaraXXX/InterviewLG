import { lazy, Suspense, useState, useRef, useEffect, useCallback } from 'react';
import { Activity, ArrowRight, BarChart3, ChevronDown, FileText, Play, RefreshCw, RotateCcw, ShieldCheck, Sparkles, Users } from 'lucide-react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import {
  adminLogin,
  adminLogout,
  createSession,
  createResume,
  deleteInterviewSession,
  deleteInterviewSessions,
  deleteResume,
  endInterviewSession,
  fetchAdminDailyUsage,
  fetchAdminOverview,
  fetchAdminPresence,
  fetchActiveCodingTask,
  fetchContextUsage,
  fetchDomains,
  fetchInterviewSessionDetail,
  fetchInterviewSessions,
  fetchLastInterviewConfig,
  fetchProfiles,
  fetchResumes,
  getAdminMe,
  getMe,
  login,
  logout,
  pauseInterviewSession,
  register,
  resumeInterviewSession,
  sendPresenceHeartbeat,
  streamChat,
  transcribeSpeech,
  submitCodingTask,
  updateResume,
  type AdminDailyUsage,
  type AdminOverview,
  type AdminPresenceUser,
  type CodingTask,
  type ContextUsage,
  type InterviewMessage,
  type InterviewSessionDetail,
  type InterviewSessionSummary,
  type LastInterviewConfig,
  type Resume,
  type ResumeProject,
} from './api';
import { CODING_LANGUAGE_LABELS } from './codingLanguages';
import MarkdownMessage from './MarkdownMessage';
import MobileBottomNav from './MobileBottomNav';
import {
  getActiveMobileNavigationItem,
  shouldShowMobileNavigation,
  type MobileNavigationItem,
  type MobileNavigationView,
} from './mobileNavigation';
import { RELEASE_NOTES } from './releaseNotes';
import {
  ADMIN_ROUTE_ENTRIES,
  getRouteSessionId,
  resolveAuthenticatedUserView,
  routeToUserView,
  ROUTES,
  userViewToRoute,
} from './routes';
import { APP_VERSION } from './version';

const CodingWorkspace = lazy(() => import('./CodingWorkspace'));

type View = MobileNavigationView;
type ThemeMode = 'light' | 'dark';
type SpeechInputState = 'idle' | 'recording' | 'uploading';

interface Message {
  role: 'user' | 'ai';
  content: string;
  streaming?: boolean;
}

const AUTH_SESSION_KEY = 'interviewlg_active_session';
const HISTORY_NOTICE_DISMISSED_KEY = 'interviewlg_history_notice_dismissed';
const THEME_STORAGE_KEY = 'interviewlg_theme';
const SPEECH_DEVICE_STORAGE_KEY = 'interviewlg_speech_device_id';
const HISTORY_WARNING_THRESHOLD = 45;
const INTERVIEW_END_PHRASE = '本次面试到此结束';
const AUTO_END_DELAY_MS = 10000;
const AUTO_END_NOTICE_MS = 5000;
const MAX_SPEECH_RECORDING_MS = 120000;
const SPEECH_SIGNAL_RMS_THRESHOLD = 0.018;
const SPEECH_MIN_ACTIVE_MS = 250;
const SPEECH_METER_UI_INTERVAL_MS = 100;
const PRESENCE_HEARTBEAT_MS = 90000;
const PRESENCE_HEARTBEAT_MIN_INTERVAL_MS = 60000;
const AUTH_RETRY_DELAYS_MS = [2000, 5000, 10000, 30000];

type BrowserWindowWithAudioContext = Window & typeof globalThis & {
  webkitAudioContext?: typeof AudioContext;
};

function getInitialTheme(): ThemeMode {
  try {
    const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
    if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme;
  } catch {
    // Ignore storage failures and fall back to system preference.
  }

  if (window.matchMedia?.('(prefers-color-scheme: light)').matches) {
    return 'light';
  }
  return 'dark';
}

function persistTheme(theme: ThemeMode): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Theme still applies for the current page if storage is unavailable.
  }
}

function getSavedSpeechDeviceId(): string {
  try {
    return localStorage.getItem(SPEECH_DEVICE_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

function persistSpeechDeviceId(deviceId: string): void {
  try {
    if (deviceId) {
      localStorage.setItem(SPEECH_DEVICE_STORAGE_KEY, deviceId);
    } else {
      localStorage.removeItem(SPEECH_DEVICE_STORAGE_KEY);
    }
  } catch {
    // Device selection still applies for the current page if storage is unavailable.
  }
}

function getSpeechDeviceDisplayName(device: MediaDeviceInfo, index: number): string {
  return device.label || `麦克风 ${index + 1}`;
}

function formatSpeechRecordingTime(seconds: number): string {
  const safeSeconds = Math.max(0, seconds);
  const minutes = Math.floor(safeSeconds / 60);
  const rest = safeSeconds % 60;
  return `${minutes}:${String(rest).padStart(2, '0')}`;
}

function markActiveBrowserSession(): void {
  try {
    sessionStorage.setItem(AUTH_SESSION_KEY, '1');
  } catch {
    // Storage may be unavailable in restricted browser modes; login still works for the current render.
  }
}

function clearActiveBrowserSession(): void {
  try {
    sessionStorage.removeItem(AUTH_SESSION_KEY);
  } catch {
    // Ignore storage failures and continue clearing server-side auth state.
  }
}

function hasDismissedHistoryNotice(): boolean {
  try {
    return sessionStorage.getItem(HISTORY_NOTICE_DISMISSED_KEY) === '1';
  } catch {
    return false;
  }
}

function markHistoryNoticeDismissed(): void {
  try {
    sessionStorage.setItem(HISTORY_NOTICE_DISMISSED_KEY, '1');
  } catch {
    // Storage may be unavailable; the in-memory dismissal state still handles the current render.
  }
}

function clearHistoryNoticeDismissed(): void {
  try {
    sessionStorage.removeItem(HISTORY_NOTICE_DISMISSED_KEY);
  } catch {
    // Ignore storage failures.
  }
}

const DEFAULT_INTERVIEW_TARGET = 'campus_fulltime';

const DIFFICULTY_OPTIONS = [
  { value: 'campus_intern', label: '校招实习', meta: '实习岗位准备', description: '侧重基础知识、编码基本功、学习能力和表达清晰度。' },
  { value: 'campus_fulltime', label: '校招正式岗', meta: '应届正式岗位准备', description: '覆盖基础扎实度、项目理解、工程意识和独立解决问题能力。' },
];

const LEGACY_DIFFICULTY_LABELS: Record<string, string> = {
  junior: '校招实习',
  mid: '校招正式岗',
  senior: '校招正式岗',
};

function normalizeInterviewTarget(value: string): string {
  if (DIFFICULTY_OPTIONS.some((option) => option.value === value)) return value;
  if (value === 'junior') return 'campus_intern';
  if (value === 'mid' || value === 'senior') return 'campus_fulltime';
  return DEFAULT_INTERVIEW_TARGET;
}

function getInterviewTargetLabel(value: string): string {
  return DIFFICULTY_OPTIONS.find((option) => option.value === value)?.label
    || LEGACY_DIFFICULTY_LABELS[value]
    || value;
}

const DEFAULT_DOMAINS = [
  'backend', 'frontend', 'fullstack', 'algorithm',
  'embedded', 'devops', 'data', 'security',
];

const DOMAIN_LABELS: Record<string, string> = {
  backend: '后端开发',
  frontend: '前端开发',
  fullstack: '全栈开发',
  algorithm: '算法',
  embedded: '嵌入式',
  devops: '运维',
  data: '数据',
  security: '安全',
};

const DOMAIN_DESCRIPTIONS: Record<string, string> = {
  backend: '围绕接口设计、数据库、缓存、并发、服务稳定性和系统设计展开。',
  frontend: '覆盖组件设计、状态管理、性能优化、工程化、浏览器机制和用户体验。',
  fullstack: '兼顾前后端协作、接口边界、端到端交付、数据流与工程取舍。',
  algorithm: '聚焦数据结构、复杂度分析、编码表达、边界条件和解题思路。',
  embedded: '关注 C/C++、操作系统、硬件接口、实时性、内存管理和调试能力。',
  devops: '考察 Linux、CI/CD、容器、监控告警、发布回滚和故障定位。',
  data: '涉及 SQL、数据建模、ETL、指标口径、数据质量和分析表达。',
  security: '覆盖 Web 安全、权限模型、漏洞排查、攻防思路和安全工程实践。',
};

const getDomainDescription = (domain: string) =>
  DOMAIN_DESCRIPTIONS[domain] || '将根据你输入的方向生成更贴近该岗位的技术追问。';

const STATUS_LABELS: Record<string, string> = {
  active: '进行中',
  paused: '已中断',
  completed: '已结束',
  expired: '已过期',
};

function formatDateTime(value: string | null): string {
  if (!value) return '未结束';
  const normalized = value.includes('T') ? value : `${value.replace(' ', 'T')}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function toQaPairs(messages: InterviewMessage[]) {
  const pairs: { question: InterviewMessage; answer?: InterviewMessage }[] = [];
  let pendingQuestion: InterviewMessage | null = null;

  for (const message of messages) {
    if (message.role === 'user') {
      if (pendingQuestion) {
        pairs.push({ question: pendingQuestion });
      }
      pendingQuestion = message;
    } else if (pendingQuestion) {
      pairs.push({ question: pendingQuestion, answer: message });
      pendingQuestion = null;
    }
  }

  if (pendingQuestion) {
    pairs.push({ question: pendingQuestion });
  }

  return pairs;
}

type QaPair = ReturnType<typeof toQaPairs>[number];

type HistoryTimelineItem =
  | { type: 'qa'; item: QaPair; qaIndex: number; sortTime: number; order: number }
  | { type: 'coding'; item: CodingTask; taskIndex: number; sortTime: number; order: number };

function timeValue(value: string | null): number {
  if (!value) return 0;
  const normalized = value.includes('T') ? value : `${value.replace(' ', 'T')}Z`;
  const time = new Date(normalized).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function buildHistoryTimeline(qaPairs: QaPair[], codingTasks: CodingTask[]): HistoryTimelineItem[] {
  return [
    ...qaPairs.map((pair, index) => ({
      type: 'qa' as const,
      item: pair,
      qaIndex: index,
      sortTime: timeValue(pair.question.created_at),
      order: index * 2,
    })),
    ...codingTasks.map((task, index) => ({
      type: 'coding' as const,
      item: task,
      taskIndex: index,
      sortTime: timeValue(task.created_at),
      order: index * 2 + 1,
    })),
  ].sort((a, b) => a.sortTime - b.sortTime || a.order - b.order);
}

function toChatMessages(messages: InterviewMessage[]): Message[] {
  return messages.map((message) => ({
    role: message.role,
    content: message.content,
  }));
}

function summarizeText(value: string, maxLength = 96): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) return '未填写';
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized;
}

function resumeMeta(resume: Resume): string {
  const parts = [];
  if (resume.projects.length > 0) parts.push(`${resume.projects.length} 个项目`);
  if (resume.skills.trim()) parts.push('技能特长');
  return parts.length ? parts.join(' / ') : '未填写内容';
}

function projectSummary(projects: ResumeProject[], maxLength = 96): string {
  if (projects.length === 0) return '未填写项目';
  return summarizeText(projects.map((project) => project.name).join(' / '), maxLength);
}

function newResumeProject(): ResumeProject {
  return { name: '', description: '' };
}

function LogoMark() {
  return (
    <div className="logo-mark">
      <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
        <rect width="36" height="36" rx="8" fill="var(--color-accent)" />
        <path d="M10 18L16 12L22 18L16 24Z" fill="white" opacity="0.9" />
        <path d="M16 18L22 12L28 18L22 24Z" fill="white" opacity="0.6" />
      </svg>
    </div>
  );
}

function ThemeToggle({ theme, onToggle }: { theme: ThemeMode; onToggle: () => void }) {
  const isLight = theme === 'light';
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      aria-label={isLight ? '切换到黑夜模式' : '切换到白天模式'}
      title={isLight ? '切换到黑夜模式' : '切换到白天模式'}
    >
      {isLight ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M21 14.2A7.4 7.4 0 0 1 9.8 3a8.2 8.2 0 1 0 11.2 11.2Z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="2" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )}
    </button>
  );
}

function ConsoleTopbar({
  title,
  username,
  theme,
  onToggleTheme,
  onLogout,
  onHome,
}: {
  title: string;
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onLogout: () => void;
  onHome?: () => void;
}) {
  return (
    <header className="console-topbar">
      <div className="brand-lockup">
        <LogoMark />
        {onHome && (
          <button className="topbar-back-button" onClick={onHome} aria-label="返回工作台">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M19 12H5M12 5L5 12L12 19" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>返回工作台</span>
          </button>
        )}
        <span>{title}</span>
      </div>
      <div className="user-badge">
        <span className="system-pill">已登录</span>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        <span className="user-badge-name">{username}</span>
        <button className="logout-link" onClick={onLogout}>退出</button>
      </div>
    </header>
  );
}

function LoginView({ onLogin }: { onLogin: (username: string) => void }) {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const INVITE_CODE_EMPTY_MSG = '请输入邀请码';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (isRegister && !inviteCode.trim()) {
      setError(INVITE_CODE_EMPTY_MSG);
      return;
    }
    setLoading(true);
    try {
      const result = isRegister
        ? await register(username, password, inviteCode)
        : await login(username, password);
      onLogin(result.username);
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="setup-view">
      <div className="auth-shell">
        <section className="auth-command" aria-label="产品介绍">
          <div className="auth-command-top">
            <div className="brand-lockup">
              <div className="logo-mark">
                <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
                  <rect width="36" height="36" rx="8" fill="var(--color-accent)" />
                  <path d="M10 18L16 12L22 18L16 24Z" fill="white" opacity="0.9" />
                  <path d="M16 18L22 12L28 18L22 24Z" fill="white" opacity="0.6" />
                </svg>
              </div>
              <span>Interview Agent</span>
            </div>
            <span className="system-pill">Private Beta</span>
          </div>

          <div className="auth-hero-copy">
            <p className="eyebrow">AI Interview Console</p>
            <h1>把一次技术面试拆成可控的练习流程</h1>
            <p>
              选择技术方向、目标岗位与岗位信息后进入模拟问答。系统会围绕校招场景持续追问，适合面试前做集中演练。
            </p>
          </div>

          <div className="auth-metrics" aria-label="系统能力摘要">
            <div>
              <span>Preset</span>
              <strong>8</strong>
              <small>技术方向</small>
            </div>
            <div>
              <span>Targets</span>
              <strong>2</strong>
              <small>目标岗位</small>
            </div>
            <div>
              <span>Context</span>
              <strong>JD</strong>
              <small>岗位定制</small>
            </div>
          </div>

          <div className="auth-sequence" aria-label="使用流程">
            <div>
              <span>01</span>
              <strong>配置目标</strong>
              <p>确认技术方向、目标岗位和目标 JD。</p>
            </div>
            <div>
              <span>02</span>
              <strong>进入问答</strong>
              <p>用连续追问模拟真实技术面试节奏。</p>
            </div>
            <div>
              <span>03</span>
              <strong>匹配校招场景</strong>
              <p>按实习或正式岗目标匹配不同的考察侧重。</p>
            </div>
          </div>
        </section>

        <section className="auth-card" aria-label={isRegister ? '注册' : '登录'}>
          <div className="panel-heading">
            <p className="eyebrow">{isRegister ? 'Create Account' : 'Welcome Back'}</p>
            <h2>{isRegister ? '创建账号' : '登录账号'}</h2>
            <p>{isRegister ? '输入邀请码后即可开启模拟面试。' : '继续上次的面试准备流程。'}</p>
          </div>

          <div className="auth-switch" aria-label="认证模式">
            <button
              type="button"
              className={!isRegister ? 'active' : ''}
              onClick={() => { setIsRegister(false); setError(''); }}
            >
              登录
            </button>
            <button
              type="button"
              className={isRegister ? 'active' : ''}
              onClick={() => { setIsRegister(true); setError(''); }}
            >
              注册
            </button>
          </div>

          <form className="login-form" onSubmit={handleSubmit}>
            <div className="login-field">
              <label className="section-label" htmlFor="login-username">用户名</label>
              <input
                id="login-username"
                type="text"
                className="custom-input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="输入用户名"
                minLength={2}
                required
              />
            </div>
            <div className="login-field">
              <label className="section-label" htmlFor="login-password">密码</label>
              <input
                id="login-password"
                type="password"
                className="custom-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isRegister ? '至少6位' : '输入密码'}
                minLength={6}
                required
              />
            </div>

            {isRegister && (
              <div className="login-field">
                <label className="section-label" htmlFor="login-invite-code">邀请码</label>
                <input
                  id="login-invite-code"
                  type="text"
                  className="custom-input"
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value)}
                  placeholder="输入邀请码"
                  required
                />
              </div>
            )}

            {error && <div className="login-error" role="alert">{error}</div>}

            <button className="start-button" type="submit" disabled={loading || !username || !password}>
              {loading ? '请稍候...' : isRegister ? '创建账号' : '进入控制台'}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}

function DashboardView({
  username,
  theme,
  onToggleTheme,
  onStartInterview,
  onProfile,
  onHistory,
  onManageHistory,
  onInsights,
  onLogout,
  historyNoticeDismissed,
  onDismissHistoryNotice,
}: {
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onStartInterview: () => void;
  onProfile: () => void;
  onHistory: () => void;
  onManageHistory: () => void;
  onInsights: () => void;
  onLogout: () => void;
  historyNoticeDismissed: boolean;
  onDismissHistoryNotice: () => void;
}) {
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [summaryUnavailable, setSummaryUnavailable] = useState(false);

  useEffect(() => {
    let ignore = false;
    fetchInterviewSessions(100)
      .then((rows) => {
        if (!ignore) {
          setSessions(rows);
          setSummaryUnavailable(false);
        }
      })
      .catch((err) => {
        if (ignore) return;
        if (err instanceof Error && err.message === 'UNAUTHORIZED') {
          onLogout();
        } else {
          setSummaryUnavailable(true);
        }
      });
    return () => {
      ignore = true;
    };
  }, [onLogout]);

  const completedCount = sessions.filter((session) => session.status === 'completed').length;
  const totalMessages = sessions.reduce((sum, session) => sum + session.message_count, 0);
  const latestSession = sessions[0];
  const interruptedSession = sessions.find((session) => session.status === 'paused');
  const latestReleaseNote = RELEASE_NOTES[0];
  const shouldShowHistoryNotice = !summaryUnavailable
    && sessions.length > HISTORY_WARNING_THRESHOLD
    && !historyNoticeDismissed;

  return (
    <div className="setup-view">
      <div className="console-shell dashboard-shell">
        <ConsoleTopbar title="Interview Agent 工作台" username={username} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} />

        <main className="mobile-dashboard" aria-label="移动端工作台">
          <header className="mobile-dashboard-intro">
            <p className="eyebrow">Workspace</p>
            <h1>继续你的面试训练</h1>
            <p>
              {summaryUnavailable
                ? '历史概览暂不可用，你仍然可以正常开始新的模拟面试。'
                : latestSession
                  ? `最近练习：${DOMAIN_LABELS[latestSession.domain] || latestSession.domain} · ${STATUS_LABELS[latestSession.status] || latestSession.status}`
                  : '完成第一次模拟面试后，这里会展示你的训练进度。'}
            </p>
          </header>

          <section className="mobile-dashboard-primary" aria-label="开始面试">
            <span>Next action</span>
            <strong>开始新的模拟面试</strong>
            <p>配置方向、目标岗位和 JD，进入连续追问。</p>
            <button className="start-button" type="button" onClick={onStartInterview}>
              <Play size={18} fill="currentColor" aria-hidden="true" />
              <span>立即开始</span>
            </button>
            {interruptedSession && (
              <button className="mobile-dashboard-resume" type="button" onClick={onHistory}>
                <RotateCcw size={16} aria-hidden="true" />
                <span>继续中断的面试</span>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            )}
          </section>

          <section className="mobile-dashboard-section" aria-labelledby="mobile-training-summary">
            <div className="mobile-dashboard-section-head">
              <h2 id="mobile-training-summary">训练概览</h2>
              <button type="button" onClick={onHistory}>查看全部</button>
            </div>
            <div className="mobile-dashboard-metrics">
              <div><strong>{summaryUnavailable ? '—' : sessions.length}</strong><span>累计面试</span></div>
              <div><strong>{summaryUnavailable ? '—' : completedCount}</strong><span>已经完成</span></div>
              <div><strong>{summaryUnavailable ? '—' : totalMessages}</strong><span>对话消息</span></div>
            </div>
          </section>

          <section className="mobile-dashboard-section" aria-labelledby="mobile-shortcuts">
            <div className="mobile-dashboard-section-head">
              <h2 id="mobile-shortcuts">快捷入口</h2>
            </div>
            <div className="mobile-dashboard-shortcuts">
              <button type="button" onClick={onProfile}>
                <FileText size={20} aria-hidden="true" />
                <span><strong>简历信息</strong><small>维护项目与技能</small></span>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
              <button type="button" onClick={onInsights}>
                <Sparkles size={20} aria-hidden="true" />
                <span><strong>AI 总结</strong><small>查看长期能力变化</small></span>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
          </section>

          {latestReleaseNote && (
            <details className="mobile-dashboard-release">
              <summary>
                <span><small>最近更新 · {APP_VERSION}</small><strong>{latestReleaseNote.title}</strong></span>
                <ChevronDown size={18} aria-hidden="true" />
              </summary>
              <div className="release-list">
                {RELEASE_NOTES.map((note) => (
                  <article className="release-note" key={`${note.date}-${note.title}`}>
                    <time>{note.date}</time>
                    <strong>{note.title}</strong>
                    <ul>{note.items.map((item) => <li key={item}>{item}</li>)}</ul>
                    {note.sections?.map((section) => (
                      <div className="release-note-section" key={section.title}>
                        <span>{section.title}</span>
                        <ul>{section.items.map((item) => <li key={item}>{item}</li>)}</ul>
                      </div>
                    ))}
                  </article>
                ))}
              </div>
            </details>
          )}
        </main>

        <main className="dashboard-grid dashboard-desktop">
          <section className="dashboard-hero" aria-label="工作台概览">
            <div className="dashboard-hero-copy">
              <p className="eyebrow">Workspace</p>
              <h1 className="setup-title">选择下一步训练任务</h1>
              <p className="setup-subtitle">
                从这里进入模拟面试、完善个人信息，或查看后续接入的历史记录与表现总结。当前优先保留核心面试流程，其他能力先作为功能入口预留。
              </p>
            </div>
            <div className="dashboard-primary-action">
              <span>Recommended</span>
              <strong>开始一轮新的模拟面试</strong>
              <p>配置方向、目标岗位和 JD 后进入连续追问。</p>
              <button className="start-button launch-button" onClick={onStartInterview}>开始模拟面试</button>
            </div>
          </section>

          <section className="dashboard-actions" aria-label="功能入口">
            <button className="workspace-action primary" onClick={onStartInterview}>
              <em>01</em>
              <span>开始面试配置</span>
              <strong>模拟技术面试</strong>
              <small>选择技术方向、目标岗位、JD 与面试偏好，进入 AI 面试官对话。</small>
            </button>
            <button className="workspace-action" onClick={onProfile}>
              <em>02</em>
              <span>个人信息</span>
              <strong>完善简历与目标岗位</strong>
              <small>后续用于让问题更贴近你的项目经历、技术栈和投递目标。</small>
            </button>
            <button className="workspace-action" onClick={onHistory}>
              <em>03</em>
              <span>历史记录</span>
              <strong>查看过往面试</strong>
              <small>后续展示每次练习的方向、目标岗位、时间和面试状态。</small>
            </button>
            <button className="workspace-action" onClick={onInsights}>
              <em>04</em>
              <span>AI 总结</span>
              <strong>历史表现分析</strong>
              <small>后续汇总知识覆盖、表达质量、追问表现和改进建议。</small>
            </button>
          </section>

          <aside className="dashboard-status" aria-label="当前状态">
            <div>
              <span>Training</span>
              <strong>{summaryUnavailable ? '暂不可用' : `${sessions.length} 次面试`}</strong>
              <small>
                {summaryUnavailable
                  ? '历史概览加载失败，不影响开始新的面试。'
                  : `已完成 ${completedCount} 次，累计 ${totalMessages} 条对话消息。`}
              </small>
            </div>
            <div>
              <span>Latest</span>
              <strong>
                {latestSession
                  ? `${DOMAIN_LABELS[latestSession.domain] || latestSession.domain} / ${getInterviewTargetLabel(latestSession.difficulty)}`
                  : '暂无记录'}
              </strong>
              <small>
                {latestSession
                  ? `${STATUS_LABELS[latestSession.status] || latestSession.status} · ${formatDateTime(latestSession.created_at)}`
                  : '完成一次模拟面试后，这里会显示最近练习。'}
              </small>
            </div>
            <div>
              <span>Available</span>
              <strong>面试 + 回看 + 题库参考</strong>
              <small>当前可用模拟技术面试、历史 QA 回看和真实面试题参考。</small>
            </div>
          </aside>

          <section className="release-panel" aria-label="版本更新记录">
            <div className="release-panel-head">
              <p className="eyebrow">Updates</p>
              <div className="release-title-row">
                <h2>版本更新记录</h2>
                <span>{APP_VERSION}</span>
              </div>
              <p>这里展示最近部署后的主要功能变化。</p>
            </div>
            <div className="release-list">
              {RELEASE_NOTES.map((note) => (
                <article className="release-note" key={`${note.date}-${note.title}`}>
                  <time>{note.date}</time>
                  <strong>{note.title}</strong>
                  <ul>
                    {note.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  {note.sections?.map((section) => (
                    <div className="release-note-section" key={section.title}>
                      <span>{section.title}</span>
                      <ul>
                        {section.items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </article>
              ))}
            </div>
          </section>
        </main>
      </div>

      {shouldShowHistoryNotice && (
        <div className="modal-backdrop" role="presentation">
          <section className="history-notice-modal" role="dialog" aria-modal="true" aria-labelledby="history-notice-title">
            <p className="eyebrow">Storage Notice</p>
            <h2 id="history-notice-title">历史面试记录即将达到上限</h2>
            <p>
              当前账号已有 {sessions.length} 条历史面试记录。建议及时清理；系统仍允许继续新增记录，
              直到达到 55 条时会自动删除最早的 5 条，将历史记录保留在最近 50 条以内。
            </p>
            <div className="modal-actions">
              <button className="secondary-button" onClick={onDismissHistoryNotice}>我知道了</button>
              <button className="inline-start-button" onClick={onManageHistory}>去管理历史记录</button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function PlaceholderView({
  username,
  theme,
  onToggleTheme,
  title,
  eyebrow,
  description,
  blocks,
  onHome,
  onStartInterview,
  onLogout,
}: {
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  title: string;
  eyebrow: string;
  description: string;
  blocks: { label: string; title: string; description: string }[];
  onHome: () => void;
  onStartInterview: () => void;
  onLogout: () => void;
}) {
  return (
    <div className="setup-view">
      <div className="console-shell placeholder-shell">
        <ConsoleTopbar title={title} username={username} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} onHome={onHome} />
        <main className="placeholder-layout">
          <section className="placeholder-main">
            <p className="eyebrow">{eyebrow}</p>
            <h1 className="setup-title">{title}</h1>
            <p className="setup-subtitle">{description}</p>
            <div className="placeholder-actions">
              <button className="inline-start-button" onClick={onStartInterview}>开始模拟面试</button>
              <button className="secondary-button" onClick={onHome}>返回工作台</button>
            </div>
          </section>
          <section className="placeholder-blocks" aria-label="待接入能力">
            {blocks.map((block) => (
              <article className="placeholder-block" key={block.label}>
                <span>{block.label}</span>
                <strong>{block.title}</strong>
                <p>{block.description}</p>
              </article>
            ))}
          </section>
        </main>
      </div>
    </div>
  );
}

function ResumeManagerView({
  username,
  theme,
  onToggleTheme,
  onHome,
  onStartInterview,
  onLogout,
}: {
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onHome: () => void;
  onStartInterview: () => void;
  onLogout: () => void;
}) {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | 'new' | null>(null);
  const [title, setTitle] = useState('');
  const [projects, setProjects] = useState<ResumeProject[]>([newResumeProject()]);
  const [skills, setSkills] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    let ignore = false;
    fetchResumes()
      .then((rows) => {
        if (!ignore) {
          setResumes(rows);
        }
      })
      .catch((err) => {
        if (ignore) return;
        if (err instanceof Error && err.message === 'UNAUTHORIZED') {
          onLogout();
        } else {
          setError('简历信息加载失败，请稍后重试。');
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoading(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, [onLogout]);

  const resetForm = () => {
    setEditingId(null);
    setTitle('');
    setProjects([newResumeProject()]);
    setSkills('');
    setError('');
  };

  const startCreate = () => {
    if (resumes.length >= 3) {
      setError('每个账号最多保存 3 份简历，请先删除不需要的简历。');
      return;
    }
    setEditingId('new');
    setTitle('');
    setProjects([newResumeProject()]);
    setSkills('');
    setError('');
  };

  const startEdit = (resume: Resume) => {
    setEditingId(resume.id);
    setTitle(resume.title);
    setProjects(resume.projects.length ? resume.projects : [newResumeProject()]);
    setSkills(resume.skills);
    setError('');
  };

  const updateProject = (index: number, patch: Partial<ResumeProject>) => {
    setProjects((prev) => prev.map((project, i) => (
      i === index ? { ...project, ...patch } : project
    )));
  };

  const removeProject = (index: number) => {
    setProjects((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((_, i) => i !== index);
    });
  };

  const canAddProject = projects.length < 5
    && projects.every((project) => project.name.trim() && project.description.trim());

  const addProject = () => {
    if (!canAddProject) return;
    setProjects((prev) => [...prev, newResumeProject()]);
  };

  const saveResume = async () => {
    const trimmedTitle = title.trim();
    const trimmedProjects = projects.map((project) => ({
      name: project.name.trim(),
      description: project.description.trim(),
    }));
    const trimmedSkills = skills.trim();
    if (!trimmedTitle) {
      setError('请填写简历名称。');
      return;
    }
    if (trimmedProjects.some((project) => !project.name || !project.description)) {
      setError('请完整填写每个项目的项目名称和具体描述。');
      return;
    }
    if (trimmedProjects.length < 1) {
      setError('至少需要填写一个项目经验。');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const saved = editingId === 'new'
        ? await createResume(trimmedTitle, trimmedProjects, trimmedSkills)
        : await updateResume(Number(editingId), trimmedTitle, trimmedProjects, trimmedSkills);
      setResumes((prev) => {
        const exists = prev.some((resume) => resume.id === saved.id);
        if (exists) {
          return prev.map((resume) => (resume.id === saved.id ? saved : resume));
        }
        return [saved, ...prev];
      });
      resetForm();
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError(err instanceof Error ? err.message : '保存简历失败，请稍后重试。');
      }
    } finally {
      setSaving(false);
    }
  };

  const removeResume = async (resume: Resume) => {
    if (!window.confirm(`确定删除「${resume.title}」吗？历史面试中已保存的使用记录不会受影响。`)) {
      return;
    }
    setSaving(true);
    setError('');
    try {
      await deleteResume(resume.id);
      setResumes((prev) => prev.filter((item) => item.id !== resume.id));
      if (editingId === resume.id) {
        resetForm();
      }
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError('删除简历失败，请稍后重试。');
      }
    } finally {
      setSaving(false);
    }
  };

  const isEditing = editingId !== null;

  return (
    <div className="setup-view">
      <div className="console-shell profile-shell">
        <ConsoleTopbar title="完善个人信息" username={username} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} onHome={onHome} />
        <main className="resume-layout">
          <section className="resume-main">
            <div className="section-heading">
              <p className="eyebrow">Resume Context</p>
              <h1 className="setup-title">简历信息管理</h1>
              <p className="setup-subtitle">
                每个账号最多保存 3 份纯文本简历，只记录项目经验和技能特长，用于让模拟面试更贴近你的经历。
              </p>
            </div>

            <div className="privacy-notice">
              <strong>隐私提醒</strong>
              <p>
                本站只保存你主动填写的项目经验和技能特长，用于生成模拟面试问题。请不要填写手机号、邮箱、身份证号、住址、账号密码、薪资等敏感信息。
              </p>
            </div>

            <div className="resume-toolbar">
              <span>{resumes.length}/3 份简历</span>
              <button className="inline-start-button" onClick={startCreate} disabled={resumes.length >= 3 || saving}>
                新增简历
              </button>
            </div>

            {error && <div className="login-error" role="alert">{error}</div>}

            <div className="resume-cards" aria-label="已保存简历">
              {loading && <div className="history-empty">正在加载简历信息...</div>}
              {!loading && resumes.length === 0 && (
                <div className="history-empty">
                  <strong>暂无简历信息</strong>
                  <span>补充项目经验和技能特长后，可以在面试配置页选择使用。</span>
                  <button className="inline-start-button" onClick={startCreate}>创建第一份简历</button>
                </div>
              )}
              {!loading && resumes.map((resume) => (
                <article className="resume-card" key={resume.id}>
                  <div>
                    <span>{resumeMeta(resume)}</span>
                    <h2>{resume.title}</h2>
                    <p>{projectSummary(resume.projects)}</p>
                  </div>
                  <div className="resume-card-actions">
                    <button className="secondary-button" onClick={() => startEdit(resume)} disabled={saving}>编辑</button>
                    <button className="danger-button" onClick={() => void removeResume(resume)} disabled={saving}>删除</button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <aside className="resume-editor">
            <div className="section-heading">
              <p className="eyebrow">Editor</p>
              <h2>{isEditing ? '编辑简历' : '选择一份简历进行编辑'}</h2>
              <p>建议只写和面试追问有关的项目、职责、技术栈、难点和成果。</p>
            </div>

            {isEditing ? (
              <div className="resume-form">
                <label>
                  <span>简历名称</span>
                  <input
                    className="custom-input"
                    value={title}
                    maxLength={60}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="例如：后端实习版、C++ 项目版"
                  />
                </label>
                <div className="resume-projects-editor">
                  <div className="resume-projects-head">
                    <span>项目经验</span>
                    <small>{projects.length}/5 个项目</small>
                  </div>
                  {projects.map((project, index) => (
                    <div className="resume-project-block" key={index}>
                      <div className="resume-project-title-row">
                        <strong>项目 {index + 1}</strong>
                        {projects.length > 1 && (
                          <button
                            className="ghost-link"
                            type="button"
                            onClick={() => removeProject(index)}
                          >
                            删除
                          </button>
                        )}
                      </div>
                      <label>
                        <span>项目名称</span>
                        <input
                          className="custom-input"
                          value={project.name}
                          maxLength={80}
                          onChange={(e) => updateProject(index, { name: e.target.value })}
                          placeholder="例如：订单系统、秒杀模块、权限平台"
                        />
                      </label>
                      <label>
                        <span>具体描述</span>
                        <textarea
                          className="custom-input jd-textarea"
                          value={project.description}
                          maxLength={2000}
                          onChange={(e) => updateProject(index, { description: e.target.value })}
                          placeholder="描述项目背景、你的职责、技术方案、难点和可被追问的细节..."
                          rows={5}
                        />
                        <small>{project.description.length}/2000</small>
                      </label>
                    </div>
                  ))}
                  {canAddProject ? (
                    <button
                      className="resume-add-project"
                      type="button"
                      onClick={addProject}
                      aria-label="增加项目经验"
                    >
                      +
                    </button>
                  ) : (
                    projects.length < 5 && (
                      <small className="resume-add-hint">完整填写当前项目后，可继续添加项目经验。</small>
                    )
                  )}
                </div>
                <label>
                  <span>技能特长</span>
                  <textarea
                    className="custom-input jd-textarea"
                    value={skills}
                    maxLength={2000}
                    onChange={(e) => setSkills(e.target.value)}
                    placeholder="例如：Python、FastAPI、Redis、MySQL、并发编程、性能优化..."
                    rows={5}
                  />
                  <small>{skills.length}/2000</small>
                </label>
                <div className="resume-form-actions">
                  <button className="secondary-button" onClick={resetForm} disabled={saving}>取消</button>
                  <button className="inline-start-button" onClick={() => void saveResume()} disabled={saving}>
                    {saving ? '保存中' : '保存简历'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="history-detail-empty">
                <h2>简历会用于面试上下文</h2>
                <p>保存后，在面试配置页选择某份简历，Agent 会围绕项目经验和技能特长做更贴近真实面试的追问。</p>
                <button className="secondary-button" onClick={onStartInterview}>去配置面试</button>
              </div>
            )}
          </aside>
        </main>
      </div>
    </div>
  );
}

function HistoryView({
  username,
  theme,
  onToggleTheme,
  initialManageMode,
  selectedSessionId,
  onHome,
  onStartInterview,
  onSelectSession,
  onClearSelectedSession,
  onResumeInterview,
  onLogout,
}: {
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  initialManageMode: boolean;
  selectedSessionId?: string;
  onHome: () => void;
  onStartInterview: () => void;
  onSelectSession: (sessionId: string) => void;
  onClearSelectedSession: () => void;
  onResumeInterview: (detail: InterviewSessionDetail) => void;
  onLogout: () => void;
}) {
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState(selectedSessionId || '');
  const [detail, setDetail] = useState<InterviewSessionDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [manageMode, setManageMode] = useState(initialManageMode);
  const [checkedIds, setCheckedIds] = useState<string[]>([]);
  const historyMountedRef = useRef(false);
  const loadingListRef = useRef(false);

  const loadSessions = useCallback(async () => {
    if (loadingListRef.current) return;
    loadingListRef.current = true;
    setLoadingList(true);
    setError('');
    try {
      const rows = await fetchInterviewSessions(100);
      if (historyMountedRef.current) {
        setSessions(rows);
      }
    } catch (err) {
      if (!historyMountedRef.current) return;
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError('历史记录加载失败，请稍后重试。');
      }
    } finally {
      loadingListRef.current = false;
      if (historyMountedRef.current) {
        setLoadingList(false);
      }
    }
  }, [onLogout]);

  useEffect(() => {
    historyMountedRef.current = true;
    const timeoutId = window.setTimeout(() => {
      void loadSessions();
    }, 0);
    return () => {
      window.clearTimeout(timeoutId);
      historyMountedRef.current = false;
    };
  }, [loadSessions]);

  const selectSession = useCallback(async (sessionId: string) => {
    if (manageMode) return;
    setSelectedId(sessionId);
    setLoadingDetail(true);
    setDetail(null);
    setError('');
    try {
      const data = await fetchInterviewSessionDetail(sessionId);
      setDetail(data);
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError('面试详情加载失败，请稍后重试。');
      }
    } finally {
      setLoadingDetail(false);
    }
  }, [manageMode, onLogout]);

  useEffect(() => {
    if (!selectedSessionId) return;
    void Promise.resolve().then(() => selectSession(selectedSessionId));
  }, [selectSession, selectedSessionId]);

  const deleteSelectedSession = async () => {
    if (!selectedId) return;
    if (!window.confirm('确定删除这条面试记录吗？删除后无法恢复。')) {
      return;
    }
    setActionLoading(true);
    setError('');
    try {
      await deleteInterviewSession(selectedId);
      setSessions((prev) => prev.filter((session) => session.id !== selectedId));
      setSelectedId('');
      setDetail(null);
      onClearSelectedSession();
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError('删除面试记录失败，请稍后重试。');
      }
    } finally {
      setActionLoading(false);
    }
  };

  const toggleManageMode = () => {
    setManageMode((current) => {
      const next = !current;
      if (current) {
        setCheckedIds([]);
      }
      return next;
    });
  };

  const toggleCheckedSession = (sessionId: string) => {
    setCheckedIds((prev) => (
      prev.includes(sessionId)
        ? prev.filter((id) => id !== sessionId)
        : [...prev, sessionId]
    ));
  };

  const toggleAllSessions = () => {
    setCheckedIds((prev) => (
      prev.length === sessions.length ? [] : sessions.map((session) => session.id)
    ));
  };

  const deleteCheckedSessions = async () => {
    if (checkedIds.length === 0) return;
    if (!window.confirm(`确定删除选中的 ${checkedIds.length} 条面试记录吗？删除后无法恢复。`)) {
      return;
    }
    setActionLoading(true);
    setError('');
    try {
      await deleteInterviewSessions(checkedIds);
      const deletedSet = new Set(checkedIds);
      setSessions((prev) => prev.filter((session) => !deletedSet.has(session.id)));
      if (selectedId && deletedSet.has(selectedId)) {
        setSelectedId('');
        setDetail(null);
        onClearSelectedSession();
      }
      setCheckedIds([]);
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError('批量删除面试记录失败，请稍后重试。');
      }
    } finally {
      setActionLoading(false);
    }
  };

  const resumeSelectedSession = async () => {
    if (!selectedId || detail?.session.status !== 'paused') return;
    setActionLoading(true);
    setError('');
    try {
      const resumed = await resumeInterviewSession(selectedId);
      onResumeInterview(resumed);
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError('继续面试失败，请刷新后重试。');
      }
    } finally {
      setActionLoading(false);
    }
  };

  const activeSession = sessions.find((session) => session.id === selectedId);
  const qaPairs = detail ? toQaPairs(detail.messages) : [];
  const timelineItems = detail ? buildHistoryTimeline(qaPairs, detail.coding_tasks) : [];

  return (
    <div className="setup-view">
      <div className="console-shell history-shell">
        <ConsoleTopbar title="历史面试记录" username={username} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} onHome={onHome} />
        <main className="history-layout">
          <section className="history-list-panel">
            <div className="history-panel-head">
              <div>
                <p className="eyebrow">History</p>
                <h1 className="setup-title">历史面试记录</h1>
                <p className="setup-subtitle">这里只展示面试概要。点击某次记录后，再加载具体 QA 内容；进入管理模式后可批量删除。</p>
              </div>
              <div className="history-head-actions">
                <button className="secondary-button history-refresh-button" onClick={loadSessions} disabled={loadingList}>
                  {loadingList ? '刷新中' : '刷新'}
                </button>
                <button className="secondary-button history-refresh-button" onClick={toggleManageMode}>
                  {manageMode ? '完成' : '管理'}
                </button>
              </div>
            </div>

            {error && <div className="login-error" role="alert">{error}</div>}

            {manageMode && sessions.length > 0 && (
              <div className="history-manage-bar">
                <button className="secondary-button" onClick={toggleAllSessions}>
                  {checkedIds.length === sessions.length ? '取消全选' : '全选'}
                </button>
                <span>已选择 {checkedIds.length} 条</span>
                <button
                  className="danger-button"
                  onClick={() => void deleteCheckedSessions()}
                  disabled={checkedIds.length === 0 || actionLoading}
                >
                  删除选中
                </button>
              </div>
            )}

            <div className="history-records" aria-label="历史面试列表">
              {loadingList && <div className="history-empty">正在加载历史记录...</div>}
              {!loadingList && sessions.length === 0 && (
                <div className="history-empty">
                  <strong>暂无历史面试</strong>
                  <span>完成一次模拟面试后，这里会显示记录。</span>
                  <button className="inline-start-button" onClick={onStartInterview}>开始模拟面试</button>
                </div>
              )}
              {!loadingList && sessions.map((session) => (
                manageMode ? (
                  <label
                    key={session.id}
                    className={`history-record history-record-select ${checkedIds.includes(session.id) ? 'active' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={checkedIds.includes(session.id)}
                      onChange={() => toggleCheckedSession(session.id)}
                    />
                    <span>{STATUS_LABELS[session.status] || session.status}</span>
                    <strong>{DOMAIN_LABELS[session.domain] || session.domain} / {getInterviewTargetLabel(session.difficulty)}</strong>
                    <small>{formatDateTime(session.created_at)} · {session.message_count} 条消息</small>
                  </label>
                ) : (
                  <button
                    key={session.id}
                    className={`history-record ${session.id === selectedId ? 'active' : ''}`}
                    onClick={() => onSelectSession(session.id)}
                    aria-pressed={session.id === selectedId}
                  >
                    <span>{STATUS_LABELS[session.status] || session.status}</span>
                    <strong>{DOMAIN_LABELS[session.domain] || session.domain} / {getInterviewTargetLabel(session.difficulty)}</strong>
                    <small>{formatDateTime(session.created_at)} · {session.message_count} 条消息</small>
                  </button>
                )
              ))}
            </div>
          </section>

          <section className="history-detail-panel" aria-label="面试详情">
            {!selectedId && (
              <div className="history-detail-empty">
                <p className="eyebrow">Detail</p>
                <h2>选择一条记录查看 QA</h2>
                <p>列表只展示概要，具体的提问与回答会在这里按轮次展示。</p>
              </div>
            )}
            {selectedId && loadingDetail && <div className="history-detail-empty">正在加载面试详情...</div>}
            {selectedId && !loadingDetail && detail && (
              <>
                <div className="history-detail-head">
                  <div>
                    <p className="eyebrow">Interview Detail</p>
                    <h2>{DOMAIN_LABELS[detail.session.domain] || detail.session.domain} / {getInterviewTargetLabel(detail.session.difficulty)}</h2>
                    <p>{formatDateTime(detail.session.created_at)} 开始，状态：{STATUS_LABELS[detail.session.status] || detail.session.status}</p>
                    {detail.session.resume_title_snapshot && (
                      <p>本次使用简历：{detail.session.resume_title_snapshot}</p>
                    )}
                  </div>
                  <div className="history-detail-actions">
                    <span className="system-pill">{qaPairs.length} 轮 QA</span>
                    <button
                      className="inline-start-button"
                      onClick={() => void resumeSelectedSession()}
                      disabled={detail.session.status !== 'paused' || actionLoading}
                    >
                      继续面试
                    </button>
                    <button
                      className="danger-button"
                      onClick={() => void deleteSelectedSession()}
                      disabled={actionLoading}
                    >
                      删除记录
                    </button>
                  </div>
                </div>

                <div className="qa-list">
                  {timelineItems.length === 0 && <div className="history-empty">这次面试还没有可回看的内容。</div>}
                  {timelineItems.map((timelineItem) => {
                    if (timelineItem.type === 'coding') {
                      const task = timelineItem.item;
                      return (
                        <article className="history-coding-card" key={`coding-${task.id}`}>
                          <div className="qa-card-head">
                            <span>Task {timelineItem.taskIndex + 1}</span>
                            <small>
                              {task.status === 'submitted'
                                ? `已提交 · ${formatDateTime(task.submitted_at)}`
                                : task.draft_code
                                  ? '未提交 · 已保存草稿'
                                  : '未提交'}
                            </small>
                          </div>
                          <h3>{task.title}</h3>
                          <MarkdownMessage content={task.description} />
                          {task.submitted_code ? (
                            <pre><code>{task.submitted_code}</code></pre>
                          ) : task.draft_code ? (
                            <>
                              <div className="history-empty">这道题还没有提交，下面是已保存的草稿。</div>
                              <pre><code>{task.draft_code}</code></pre>
                            </>
                          ) : (
                            <div className="history-empty">这道题还没有提交代码。</div>
                          )}
                        </article>
                      );
                    }

                    const pair = timelineItem.item;
                    return (
                      <article className="qa-card" key={`qa-${pair.question.seq}-${timelineItem.qaIndex}`}>
                        <div className="qa-card-head">
                          <span>Q{timelineItem.qaIndex + 1}</span>
                          <small>{formatDateTime(pair.question.created_at)}</small>
                        </div>
                        <div className="qa-message user">
                          <strong>我的回答</strong>
                          <MarkdownMessage content={pair.question.content} />
                        </div>
                        <div className="qa-message ai">
                          <strong>AI 面试官</strong>
                          <MarkdownMessage content={pair.answer?.content || '这轮还没有 AI 回复。'} />
                        </div>
                      </article>
                    );
                  })}
                </div>
              </>
            )}
            {activeSession && !detail && !loadingDetail && (
              <div className="history-detail-empty">
                <h2>{DOMAIN_LABELS[activeSession.domain] || activeSession.domain}</h2>
                <p>详情暂未加载，请重新选择该记录。</p>
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  );
}

function SetupView({ onStart, username, theme, onToggleTheme, onLogout, onBack, onProfile }: {
  onStart: (
    domain: string,
    difficulty: string,
    jobDescription: string,
    profileCompany: string,
    profilePosition: string,
    resumeId: number | null,
  ) => void;
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onLogout: () => void;
  onBack: () => void;
  onProfile: () => void;
}) {
  const [domains, setDomains] = useState<string[]>(DEFAULT_DOMAINS);
  const [selectedDomain, setSelectedDomain] = useState('');
  const [customDomain, setCustomDomain] = useState('');
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [selectedResumeId, setSelectedResumeId] = useState<number | null>(null);
  const [resumeLoadError, setResumeLoadError] = useState(false);
  const [difficulty, setDifficulty] = useState(DEFAULT_INTERVIEW_TARGET);
  const [jobDescription, setJobDescription] = useState('');
  const [profiles, setProfiles] = useState<{key: string; company: string; position: string; source_count: number}[]>([]);
  const [selectedProfileIdx, setSelectedProfileIdx] = useState(-1);
  const [customCompany, setCustomCompany] = useState('');
  const [customPosition, setCustomPosition] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingLastConfig, setLoadingLastConfig] = useState(false);
  const [configNotice, setConfigNotice] = useState('');

  useEffect(() => {
    fetchDomains().then(setDomains).catch(() => {});
  }, []);

  useEffect(() => {
    fetchProfiles().then(setProfiles).catch(() => {});
  }, []);

  useEffect(() => {
    fetchResumes()
      .then((rows) => {
        setResumes(rows);
        setResumeLoadError(false);
      })
      .catch((err) => {
        if (err instanceof Error && err.message === 'UNAUTHORIZED') {
          onLogout();
        } else {
          setResumeLoadError(true);
        }
      });
  }, [onLogout]);

  const activeDomain = customDomain || selectedDomain;
  const activeDomainLabel = activeDomain ? (DOMAIN_LABELS[activeDomain] || activeDomain) : '待选择';
  const activeDifficulty = DIFFICULTY_OPTIONS.find((opt) => opt.value === difficulty) || DIFFICULTY_OPTIONS[1];
  const selectedResume = resumes.find((resume) => resume.id === selectedResumeId);
  const [mobileSetupStep, setMobileSetupStep] = useState(0);
  const setupSteps = [
    { key: 'domain', label: '技术方向', summary: activeDomainLabel },
    { key: 'resume', label: '简历选择', summary: selectedResume ? selectedResume.title : '可选' },
    { key: 'target', label: '目标岗位', summary: activeDifficulty.label },
    {
      key: 'context',
      label: '岗位信息',
      summary: jobDescription.trim() || selectedProfileIdx !== -1 ? '已补充' : '可选',
    },
    { key: 'confirm', label: '确认启动', summary: activeDomain ? '可开始' : '待选择' },
  ];
  const currentMobileSetupStep = setupSteps[mobileSetupStep] || setupSteps[0];
  const isConfirmStep = currentMobileSetupStep.key === 'confirm';
  const canContinueMobileSetup = currentMobileSetupStep.key !== 'domain' || Boolean(activeDomain);
  const goPrevMobileSetupStep = () => setMobileSetupStep((step) => Math.max(0, step - 1));
  const goNextMobileSetupStep = () => {
    if (!canContinueMobileSetup) return;
    setMobileSetupStep((step) => Math.min(setupSteps.length - 1, step + 1));
  };

  const applyInterviewConfig = (
    config: LastInterviewConfig,
    availableDomains: string[],
    availableResumes: Resume[],
    availableProfiles: {key: string; company: string; position: string; source_count: number}[],
  ) => {
    const presetDomain = availableDomains.includes(config.domain);
    if (presetDomain) {
      setSelectedDomain(config.domain);
      setCustomDomain('');
    } else {
      setSelectedDomain('');
      setCustomDomain(config.domain);
    }

    setDifficulty(normalizeInterviewTarget(config.difficulty || DEFAULT_INTERVIEW_TARGET));
    setJobDescription(config.job_description || '');

    if (config.resume_id && availableResumes.some((resume) => resume.id === config.resume_id)) {
      setSelectedResumeId(config.resume_id);
    } else {
      setSelectedResumeId(null);
      if (config.resume_id) {
        setConfigNotice('已加载上次配置，但上次使用的简历已不存在，已切换为不使用简历。');
      }
    }

    const profileCompany = config.profile_company || '';
    const profilePosition = config.profile_position || '';
    if (profileCompany && profilePosition) {
      const profileIndex = availableProfiles.findIndex(
        (profile) => profile.company === profileCompany && profile.position === profilePosition,
      );
      if (profileIndex >= 0) {
        setSelectedProfileIdx(profileIndex);
        setCustomCompany('');
        setCustomPosition('');
      } else {
        setSelectedProfileIdx(-2);
        setCustomCompany(profileCompany);
        setCustomPosition(profilePosition);
      }
    } else {
      setSelectedProfileIdx(-1);
      setCustomCompany('');
      setCustomPosition('');
    }

    if (!config.resume_id || availableResumes.some((resume) => resume.id === config.resume_id)) {
      setConfigNotice('已加载上次面试配置。');
    }
  };

  const loadLastConfig = async () => {
    setLoadingLastConfig(true);
    setConfigNotice('');
    try {
      const [config, latestDomains, latestResumes, latestProfiles] = await Promise.all([
        fetchLastInterviewConfig(),
        fetchDomains(),
        fetchResumes(),
        fetchProfiles(),
      ]);
      if (!config) {
        setConfigNotice('还没有可加载的历史配置。完成一次面试配置后，这里会自动保存最近一次配置。');
        return;
      }
      setDomains(latestDomains);
      setResumes(latestResumes);
      setProfiles(latestProfiles);
      setResumeLoadError(false);
      applyInterviewConfig(config, latestDomains, latestResumes, latestProfiles);
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setConfigNotice('加载上次配置失败，请稍后重试。');
      }
    } finally {
      setLoadingLastConfig(false);
    }
  };

  const handleStart = () => {
    if (!activeDomain || !difficulty) return;
    setLoading(true);
    let profileCompany = '';
    let profilePosition = '';
    if (selectedProfileIdx === -2) {
      profileCompany = customCompany;
      profilePosition = customPosition;
    } else if (selectedProfileIdx >= 0 && profiles[selectedProfileIdx]) {
      profileCompany = profiles[selectedProfileIdx].company;
      profilePosition = profiles[selectedProfileIdx].position;
    }
    onStart(activeDomain, normalizeInterviewTarget(difficulty), jobDescription, profileCompany, profilePosition, selectedResumeId);
  };

  return (
    <div className="setup-view">
      <div className="console-shell">
        <ConsoleTopbar title="模拟技术面试" username={username} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} onHome={onBack} />

        <div className={`console-grid setup-step-${currentMobileSetupStep.key}`}>
          <aside className="workflow-rail" aria-label="配置步骤">
            <div className="rail-title">
              <p className="eyebrow">Workflow</p>
              <h2>面试配置流程</h2>
            </div>
            <ol className="rail-steps">
              <li className={activeDomain ? 'complete' : 'active'}>
                <span>01</span>
                <div>
                  <strong>技术方向</strong>
                  <small>{activeDomainLabel}</small>
                </div>
              </li>
              <li className={selectedResume ? 'complete' : activeDomain ? 'active' : ''}>
                <span>02</span>
                <div>
                  <strong>简历选择</strong>
                  <small>{selectedResume ? selectedResume.title : '可选，推荐完善'}</small>
                </div>
              </li>
              <li className={difficulty ? 'complete' : 'active'}>
                <span>03</span>
                <div>
                  <strong>目标岗位</strong>
                  <small>{activeDifficulty.meta}</small>
                </div>
              </li>
              <li className={jobDescription.trim() ? 'complete' : ''}>
                <span>04</span>
                <div>
                  <strong>岗位 JD</strong>
                  <small>{jobDescription.trim() ? '已提供岗位信息' : '可选，推荐提供'}</small>
                </div>
              </li>
              <li className={selectedProfileIdx !== -1 ? 'complete' : ''}>
                <span>05</span>
                <div>
                  <strong>面试偏好</strong>
                  <small>{selectedProfileIdx === -1 ? '默认通用风格' : '已选择偏好'}</small>
                </div>
              </li>
            </ol>
          </aside>

          <main className="config-stage">
            <section className="config-hero">
              <div>
                <p className="eyebrow">Interview Setup</p>
                <h1 className="setup-title">定制你的技术面试场景</h1>
                <p className="setup-subtitle">保留必要输入，减少多余选择。方向决定问题范围，目标岗位决定校招考察侧重，JD 会让问题更贴近真实招聘要求。</p>
              </div>
              <div className="config-status config-status-actions">
                <div>
                  <span>{activeDomain ? 'Ready' : 'Waiting'}</span>
                  <strong>{activeDomain ? '配置可启动' : '请选择技术方向'}</strong>
                </div>
                <button
                  className="secondary-button"
                  onClick={() => void loadLastConfig()}
                  disabled={loadingLastConfig}
                >
                  {loadingLastConfig ? '加载中' : '加载上次配置'}
                </button>
              </div>
            </section>

            {configNotice && <div className="config-notice">{configNotice}</div>}

            <nav className="mobile-setup-stepper" aria-label="面试配置步骤">
              {setupSteps.map((step, index) => (
                <button
                  key={step.key}
                  className={`mobile-setup-step ${index === mobileSetupStep ? 'active' : ''} ${index < mobileSetupStep ? 'complete' : ''}`}
                  type="button"
                  onClick={() => setMobileSetupStep(index)}
                  aria-current={index === mobileSetupStep ? 'step' : undefined}
                >
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <strong>{step.label}</strong>
                  <small>{step.summary}</small>
                </button>
              ))}
            </nav>

            <section className={`config-section mobile-config-step ${currentMobileSetupStep.key === 'domain' ? 'active' : ''}`}>
              <div className="section-heading">
                <label className="section-label">技术方向</label>
                <p>选择最接近目标岗位的方向，面试官会围绕对应能力模型追问。</p>
              </div>
              <div className="selection-grid domain-grid">
                {domains.map((d) => (
                  <button
                    key={d}
                    className={`domain-card ${selectedDomain === d && !customDomain ? 'active' : ''}`}
                    onClick={() => { setSelectedDomain(d); setCustomDomain(''); }}
                    aria-pressed={selectedDomain === d && !customDomain}
                  >
                    <em>{DOMAIN_LABELS[d]?.slice(0, 1) || d.slice(0, 1).toUpperCase()}</em>
                    <span>{DOMAIN_LABELS[d] || d}</span>
                    <small>{getDomainDescription(d)}</small>
                  </button>
                ))}
              </div>
              <div className="custom-domain">
                <input
                  aria-label="自定义技术方向"
                  type="text"
                  className="custom-input"
                  placeholder="或输入自定义方向，例如：Java 后端、AI 工程、测试开发"
                  value={customDomain}
                  onChange={(e) => { setCustomDomain(e.target.value); setSelectedDomain(''); }}
                />
              </div>
            </section>

            <section className={`config-section mobile-config-step ${currentMobileSetupStep.key === 'resume' ? 'active' : ''}`}>
              <div className="section-heading">
                <label className="section-label">简历选择（可选）</label>
                <p>选择一份简历后，本次面试会围绕项目经验和技能特长调整追问重点。</p>
              </div>
              <div className="privacy-notice compact">
                <strong>隐私提醒</strong>
                <p>
                  本站只保存你主动填写的项目经验和技能特长，用于生成模拟面试问题。请不要填写手机号、邮箱、身份证号、住址、账号密码、薪资等敏感信息。
                </p>
              </div>
              {resumeLoadError && <div className="login-error" role="alert">简历信息加载失败，不影响继续配置面试。</div>}
              {resumes.length === 0 ? (
                <div className="resume-empty-inline">
                  <div>
                    <strong>你还没有保存简历</strong>
                    <p>完善简历后，可以让项目深挖和技能追问更贴近你的真实经历。</p>
                  </div>
                  <button className="secondary-button" onClick={onProfile}>去完善简历</button>
                </div>
              ) : (
                <div className="resume-select-grid">
                  <button
                    className={`resume-select-card ${selectedResumeId === null ? 'active' : ''}`}
                    onClick={() => setSelectedResumeId(null)}
                    aria-pressed={selectedResumeId === null}
                  >
                    <span>Default</span>
                    <strong>不使用简历</strong>
                    <small>按技术方向、目标岗位和 JD 生成通用面试问题。</small>
                  </button>
                  {resumes.map((resume) => (
                    <button
                      key={resume.id}
                      className={`resume-select-card ${selectedResumeId === resume.id ? 'active' : ''}`}
                      onClick={() => setSelectedResumeId(resume.id)}
                      aria-pressed={selectedResumeId === resume.id}
                    >
                      <span>{resumeMeta(resume)}</span>
                      <strong>{resume.title}</strong>
                      <small>{projectSummary(resume.projects, 72)}</small>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className={`config-section mobile-config-step ${currentMobileSetupStep.key === 'target' ? 'active' : ''}`}>
              <div className="section-heading">
                <label className="section-label">目标岗位</label>
                <p>选择你正在准备的校招岗位类型。实习更关注基础和学习能力，正式岗更关注项目理解和工程意识。</p>
              </div>
              <div className="difficulty-grid">
                {DIFFICULTY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`difficulty-card ${difficulty === opt.value ? 'active' : ''}`}
                    onClick={() => setDifficulty(opt.value)}
                    aria-pressed={difficulty === opt.value}
                  >
                    <em>{opt.value === 'campus_intern' ? '01' : '02'}</em>
                    <span>{opt.label}</span>
                    <strong>{opt.meta}</strong>
                    <small>{opt.description}</small>
                  </button>
                ))}
              </div>
            </section>

            <div className={`context-grid mobile-config-step ${currentMobileSetupStep.key === 'context' ? 'active' : ''}`}>
              <section className="context-panel">
                <div className="section-heading">
                  <label className="section-label" htmlFor="job-description">岗位JD（可选）</label>
                  <p>
                    JD 是 Job Description，即招聘页面里的岗位职责和任职要求。可从招聘网站、公司官网或内推说明中复制，提供后会用于调整面试侧重点。
                  </p>
                </div>
                <textarea
                  id="job-description"
                  className="custom-input jd-textarea"
                  placeholder="粘贴岗位JD，AI将根据职责、技术栈和任职要求调整问题..."
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  rows={5}
                />
              </section>

              <section className="context-panel">
                <div className="section-heading">
                  <label className="section-label" htmlFor="profile-select">面试偏好（可选）</label>
                  <p>选择公司和岗位画像后，问题会更贴近对应面经风格；也可以保持默认。</p>
                </div>
                <select
                  id="profile-select"
                  className="custom-input profile-select"
                  value={selectedProfileIdx}
                  onChange={(e) => { setSelectedProfileIdx(Number(e.target.value)); setCustomCompany(''); setCustomPosition(''); }}
                >
                  <option value={-1}>无</option>
                  {profiles.map((p, i) => (
                    <option key={p.key} value={i}>
                      {p.company} - {p.position}（{p.source_count}份面经）
                    </option>
                  ))}
                  <option value={-2}>手动输入...</option>
                </select>
                {selectedProfileIdx === -2 && (
                  <div className="custom-profile-inputs">
                    <input
                      aria-label="公司名称"
                      type="text"
                      className="custom-input"
                      placeholder="公司名称"
                      value={customCompany}
                      onChange={(e) => setCustomCompany(e.target.value)}
                    />
                    <input
                      aria-label="岗位名称"
                      type="text"
                      className="custom-input"
                      placeholder="岗位名称"
                      value={customPosition}
                      onChange={(e) => setCustomPosition(e.target.value)}
                    />
                  </div>
                )}
              </section>
            </div>

            <div className="mobile-setup-nav">
              <button
                className="secondary-button"
                type="button"
                onClick={goPrevMobileSetupStep}
                disabled={mobileSetupStep === 0}
              >
                上一步
              </button>
              {!isConfirmStep && (
                <button
                  className="start-button mobile-next-button"
                  type="button"
                  onClick={goNextMobileSetupStep}
                  disabled={!canContinueMobileSetup}
                >
                  下一步
                </button>
              )}
            </div>
          </main>

          <aside className="launch-panel">
            <div className="aside-block">
              <p className="eyebrow">Current</p>
              <h2>启动前确认</h2>
            </div>
            <div className="setup-summary">
              <div>
                <span>方向</span>
                <strong>{activeDomainLabel}</strong>
              </div>
              <div>
                <span>目标岗位</span>
                <strong>{activeDifficulty.label}</strong>
              </div>
              <div>
                <span>简历</span>
                <strong>{selectedResume ? selectedResume.title : '未使用简历'}</strong>
              </div>
              <div>
                <span>岗位信息</span>
                <strong>{jobDescription.trim() ? '已提供 JD' : '未提供 JD'}</strong>
              </div>
            </div>
            <div className="aside-block">
              <h2>选择建议</h2>
              <ul className="setup-guide">
                <li>方向不确定时，优先选择最接近投递岗位主职责的方向。</li>
                <li>准备实习投递选择校招实习，准备应届正式岗位选择校招正式岗。</li>
                <li>有明确招聘链接时建议粘贴 JD，问题会更聚焦。</li>
              </ul>
            </div>
            <button
              className="start-button launch-button"
              disabled={!activeDomain || loading}
              onClick={handleStart}
            >
              {loading ? '正在准备...' : '开始面试'}
            </button>
          </aside>
        </div>
      </div>
    </div>
  );
}

function ContextUsageMeter({ usage }: { usage: ContextUsage }) {
  const percent = Math.max(0, Math.min(999, Math.round((usage.ratio || 0) * 100)));
  const fillPercent = Math.min(percent, 100);
  const title = [
    `上下文占用：${usage.total_tokens} / ${usage.input_budget_tokens} tokens`,
    `窗口：${usage.context_window_tokens}，输出预留：${usage.output_reserve_tokens}`,
    ...usage.sections
      .filter((section) => section.tokens > 0)
      .map((section) => `${section.label}: ${section.tokens}`),
    usage.is_estimate ? '该数值为 tokenizer 近似估算' : '',
  ].filter(Boolean).join('\n');

  return (
    <div className={`context-usage-meter ${usage.status}`} title={title} aria-label={`上下文占用 ${percent}%`}>
      <span className="context-usage-label">上下文</span>
      <div className="context-usage-track" aria-hidden="true">
        <div className="context-usage-fill" style={{ width: `${fillPercent}%` }} />
      </div>
      <span className="context-usage-percent">{percent}%</span>
    </div>
  );
}

function ChatView({
  sessionId,
  domain,
  difficulty,
  initialMessages,
  theme,
  onToggleTheme,
  onPause,
  onEnd,
  onAuthExpired,
}: {
  sessionId: string;
  domain: string;
  difficulty: string;
  initialMessages: Message[];
  theme: ThemeMode;
  onToggleTheme: () => void;
  onPause: () => Promise<void>;
  onEnd: () => Promise<void>;
  onAuthExpired: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>(() => initialMessages);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [codingTask, setCodingTask] = useState<CodingTask | null>(null);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const [autoEndNotice, setAutoEndNotice] = useState('');
  const [autoEnded, setAutoEnded] = useState(false);
  const [speechState, setSpeechState] = useState<SpeechInputState>('idle');
  const [speechError, setSpeechError] = useState('');
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [speechVolume, setSpeechVolume] = useState(0);
  const [hasSpeechSignal, setHasSpeechSignal] = useState(false);
  const [speechDevices, setSpeechDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedSpeechDeviceId, setSelectedSpeechDeviceId] = useState(() => getSavedSpeechDeviceId());
  const [currentSpeechDeviceLabel, setCurrentSpeechDeviceLabel] = useState('');
  const [isRefreshingSpeechDevices, setIsRefreshingSpeechDevices] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const autoEndTimerRef = useRef<number | null>(null);
  const noticeTimerRef = useRef<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingStartedAtRef = useRef(0);
  const recordingTimerRef = useRef<number | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const speechMeterFrameRef = useRef<number | null>(null);
  const speechMaxVolumeRef = useRef(0);
  const speechActiveMsRef = useRef(0);
  const speechMeterLastSampleAtRef = useRef(0);
  const speechMeterLastUiAtRef = useRef(0);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const refreshContextUsage = useCallback(async () => {
    try {
      const usage = await fetchContextUsage(sessionId);
      setContextUsage(usage);
    } catch {
      setContextUsage(null);
    }
  }, [sessionId]);

  useEffect(() => {
    let isActive = true;

    async function loadContextUsage() {
      try {
        const usage = await fetchContextUsage(sessionId);
        if (isActive) {
          setContextUsage(usage);
        }
      } catch {
        if (isActive) {
          setContextUsage(null);
        }
      }
    }

    void loadContextUsage();

    return () => {
      isActive = false;
    };
  }, [sessionId]);

  const refreshSpeechDevices = useCallback(async () => {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    setIsRefreshingSpeechDevices(true);
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const audioInputs = devices.filter((device) => device.kind === 'audioinput');
      setSpeechDevices(audioInputs);
      setSelectedSpeechDeviceId((currentDeviceId) => {
        if (!currentDeviceId || audioInputs.some((device) => device.deviceId === currentDeviceId)) {
          return currentDeviceId;
        }
        persistSpeechDeviceId('');
        return '';
      });
    } catch {
      setSpeechError('无法读取麦克风设备列表，请检查浏览器权限。');
    } finally {
      setIsRefreshingSpeechDevices(false);
    }
  }, []);

  useEffect(() => {
    const mediaDevices = navigator.mediaDevices;
    if (!mediaDevices?.addEventListener) return undefined;
    const handleDeviceChange = () => {
      void refreshSpeechDevices();
    };
    mediaDevices.addEventListener('devicechange', handleDeviceChange);
    return () => {
      mediaDevices.removeEventListener('devicechange', handleDeviceChange);
    };
  }, [refreshSpeechDevices]);

  const cleanupSpeechMeter = useCallback(() => {
    if (speechMeterFrameRef.current !== null) {
      window.cancelAnimationFrame(speechMeterFrameRef.current);
      speechMeterFrameRef.current = null;
    }
    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    if (audioContext && audioContext.state !== 'closed') {
      void audioContext.close().catch(() => undefined);
    }
  }, []);

  useEffect(() => () => {
    if (autoEndTimerRef.current !== null) {
      window.clearTimeout(autoEndTimerRef.current);
    }
    if (noticeTimerRef.current !== null) {
      window.clearTimeout(noticeTimerRef.current);
    }
    if (recordingTimerRef.current !== null) {
      window.clearInterval(recordingTimerRef.current);
    }
    cleanupSpeechMeter();
    mediaRecorderRef.current?.stream.getTracks().forEach((track) => track.stop());
  }, [cleanupSpeechMeter]);

  const refreshCodingTask = useCallback(async () => {
    try {
      const task = await fetchActiveCodingTask(sessionId);
      setCodingTask(task);
    } catch {
      // Keep chat usable even if the coding workspace cannot refresh.
    }
  }, [sessionId]);

  const showAutoEndNotice = useCallback((message: string) => {
    setAutoEndNotice(message);
    if (noticeTimerRef.current !== null) {
      window.clearTimeout(noticeTimerRef.current);
    }
    noticeTimerRef.current = window.setTimeout(() => {
      setAutoEndNotice('');
      noticeTimerRef.current = null;
    }, AUTO_END_NOTICE_MS);
  }, []);

  const scheduleAutoEnd = useCallback((reply: string) => {
    if (!reply.includes(INTERVIEW_END_PHRASE) || autoEnded || autoEndTimerRef.current !== null) return;
    autoEndTimerRef.current = window.setTimeout(() => {
      autoEndTimerRef.current = null;
      void endInterviewSession(sessionId)
        .then(() => {
          setAutoEnded(true);
          showAutoEndNotice('本次面试已自动结束并保存，可继续查看反馈。');
          void refreshContextUsage();
        })
        .catch(() => {
          showAutoEndNotice('自动结束保存失败，请手动点击“结束面试”。');
        });
    }, AUTO_END_DELAY_MS);
  }, [autoEnded, refreshContextUsage, sessionId, showAutoEndNotice]);

  useEffect(() => {
    let ignore = false;
    fetchActiveCodingTask(sessionId)
      .then((task) => {
        if (!ignore) {
          setCodingTask(task);
        }
      })
      .catch(() => undefined);
    return () => {
      ignore = true;
    };
  }, [sessionId]);

  const startAgentStream = useCallback((displayMessage: string, contextMessage: string = '') => {
    const text = displayMessage.trim();
    if (!text || isStreaming || autoEnded) return;

    setInput('');
    let aiMsgIndex = 0;
    let aiContent = '';
    setMessages((prev) => {
      aiMsgIndex = prev.length + 1;
      return [...prev, { role: 'user', content: text }, { role: 'ai', content: '', streaming: true }];
    });
    setIsStreaming(true);

    const controller = streamChat(
      sessionId,
      text,
      (token) => {
        aiContent += token;
        setMessages((prev) =>
          prev.map((m, i) =>
            i === aiMsgIndex ? { ...m, content: m.content + token } : m,
          ),
        );
      },
      () => {
        setMessages((prev) =>
          prev.map((m, i) =>
            i === aiMsgIndex ? { ...m, streaming: false } : m,
          ),
        );
        setIsStreaming(false);
        void refreshCodingTask();
        void refreshContextUsage();
        scheduleAutoEnd(aiContent);
      },
      contextMessage,
      (err) => {
        setMessages((prev) => prev.filter((_, index) => index !== aiMsgIndex));
        setIsStreaming(false);
        if (err.message === 'UNAUTHORIZED') {
          onAuthExpired();
          return;
        }
        setAutoEndNotice('消息发送失败，请稍候重试。');
      },
    );
    abortRef.current = controller;
  }, [autoEnded, isStreaming, onAuthExpired, refreshCodingTask, refreshContextUsage, scheduleAutoEnd, sessionId]);

  const startSpeechMeter = useCallback((stream: MediaStream) => {
    cleanupSpeechMeter();
    speechMaxVolumeRef.current = 0;
    speechActiveMsRef.current = 0;
    speechMeterLastSampleAtRef.current = 0;
    speechMeterLastUiAtRef.current = 0;
    setSpeechVolume(0);
    setHasSpeechSignal(false);

    const AudioContextConstructor = window.AudioContext || (window as BrowserWindowWithAudioContext).webkitAudioContext;
    if (!AudioContextConstructor) return;

    try {
      const audioContext = new AudioContextConstructor();
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      audioContextRef.current = audioContext;
      void audioContext.resume().catch(() => undefined);

      const samples = new Uint8Array(analyser.fftSize);
      const sample = (timestamp: number) => {
        analyser.getByteTimeDomainData(samples);
        let squareSum = 0;
        for (const value of samples) {
          const centered = (value - 128) / 128;
          squareSum += centered * centered;
        }
        const rms = Math.sqrt(squareSum / samples.length);
        const previousSampleAt = speechMeterLastSampleAtRef.current || timestamp;
        const elapsedMs = Math.max(0, timestamp - previousSampleAt);
        speechMeterLastSampleAtRef.current = timestamp;
        speechMaxVolumeRef.current = Math.max(speechMaxVolumeRef.current, rms);
        if (rms >= SPEECH_SIGNAL_RMS_THRESHOLD) {
          speechActiveMsRef.current += elapsedMs;
        }

        if (timestamp - speechMeterLastUiAtRef.current >= SPEECH_METER_UI_INTERVAL_MS) {
          speechMeterLastUiAtRef.current = timestamp;
          setSpeechVolume(Math.min(100, Math.round(rms * 520)));
          setHasSpeechSignal(speechActiveMsRef.current >= SPEECH_MIN_ACTIVE_MS);
        }
        speechMeterFrameRef.current = window.requestAnimationFrame(sample);
      };

      speechMeterFrameRef.current = window.requestAnimationFrame(sample);
    } catch {
      cleanupSpeechMeter();
    }
  }, [cleanupSpeechMeter]);

  const finalizeSpeechRecording = useCallback(async () => {
    if (recordingTimerRef.current !== null) {
      window.clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    const recorder = mediaRecorderRef.current;
    const chunks = audioChunksRef.current;
    const activeSpeechMs = speechActiveMsRef.current;
    const maxVolume = speechMaxVolumeRef.current;
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
    cleanupSpeechMeter();
    recorder?.stream.getTracks().forEach((track) => track.stop());

    const durationMs = recordingStartedAtRef.current > 0 ? Date.now() - recordingStartedAtRef.current : 0;
    recordingStartedAtRef.current = 0;
    setRecordingSeconds(0);
    setSpeechVolume(0);
    setHasSpeechSignal(false);

    if (chunks.length === 0) {
      setSpeechState('idle');
      setSpeechError('没有录到有效语音，请重试。');
      return;
    }

    if (durationMs >= 1200 && (activeSpeechMs < SPEECH_MIN_ACTIVE_MS || maxVolume < SPEECH_SIGNAL_RMS_THRESHOLD)) {
      setSpeechState('idle');
      setSpeechError('没有检测到麦克风声音，请检查浏览器输入设备或系统麦克风音量。');
      return;
    }

    const audioType = recorder?.mimeType || chunks[0]?.type || 'audio/webm';
    const audioBlob = new Blob(chunks, { type: audioType });
    setSpeechState('uploading');
    setSpeechError('');
    try {
      const result = await transcribeSpeech(audioBlob, durationMs);
      const transcript = result.text.trim();
      if (!transcript) {
        setSpeechError('没有识别到有效文本，请重试或手动输入。');
        return;
      }
      setInput((prev) => {
        const current = prev.trimEnd();
        return current ? `${current}\n${transcript}` : transcript;
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : '语音转写失败';
      if (message === 'UNAUTHORIZED') {
        setSpeechError('登录状态已失效，请重新登录后再使用语音输入。');
      } else if (message.includes('not configured') || message.includes('SPEECH_API_KEY')) {
        setSpeechError('语音转写服务尚未配置，请先使用键盘输入。');
      } else {
        setSpeechError('语音转写失败，请重试或手动输入。');
      }
    } finally {
      setSpeechState('idle');
    }
  }, [cleanupSpeechMeter]);

  const stopSpeechRecording = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (!recorder) return;
    if (recorder.state === 'recording') {
      recorder.requestData();
      recorder.stop();
    }
  }, []);

  const startSpeechRecording = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia || !('MediaRecorder' in window)) {
      setSpeechError('当前浏览器不支持录音，请使用新版 Chrome、Edge 或 Safari。');
      return;
    }
    setSpeechError('');
    try {
      const audioConstraints: MediaTrackConstraints = selectedSpeechDeviceId
        ? {
            deviceId: { exact: selectedSpeechDeviceId },
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          }
        : {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          };
      const stream = await navigator.mediaDevices.getUserMedia({ audio: audioConstraints });
      const preferredMimeType = [
        'audio/webm;codecs=opus',
        'audio/webm',
        'audio/mp4',
      ].find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = new MediaRecorder(stream, preferredMimeType ? { mimeType: preferredMimeType } : undefined);
      const [audioTrack] = stream.getAudioTracks();
      if (!audioTrack || audioTrack.readyState === 'ended') {
        stream.getTracks().forEach((track) => track.stop());
        setSpeechState('idle');
        setSpeechError('没有可用的麦克风输入，请检查浏览器输入设备。');
        return;
      }
      const selectedDevice = speechDevices.find((device) => device.deviceId === selectedSpeechDeviceId);
      setCurrentSpeechDeviceLabel(audioTrack.label || selectedDevice?.label || (selectedSpeechDeviceId ? '已选择的麦克风' : '浏览器默认麦克风'));
      audioTrack.onmute = () => {
        setSpeechError('麦克风输入暂时没有声音，请检查系统输入设备。');
      };
      audioTrack.onunmute = () => {
        setSpeechError('');
      };
      audioTrack.onended = () => {
        setSpeechError('麦克风输入已断开，请重新开始录音。');
        stopSpeechRecording();
      };
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      recordingStartedAtRef.current = Date.now();
      startSpeechMeter(stream);

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      recorder.onerror = () => {
        setSpeechError('录音失败，请检查浏览器麦克风权限。');
        stopSpeechRecording();
      };
      recorder.onstop = () => {
        void finalizeSpeechRecording();
      };

      recorder.start();
      setSpeechState('recording');
      setRecordingSeconds(0);
      void refreshSpeechDevices();
      recordingTimerRef.current = window.setInterval(() => {
        const elapsedMs = Date.now() - recordingStartedAtRef.current;
        setRecordingSeconds(Math.floor(elapsedMs / 1000));
        if (elapsedMs >= MAX_SPEECH_RECORDING_MS) {
          stopSpeechRecording();
        }
      }, 500);
    } catch {
      setSpeechState('idle');
      setSpeechError(selectedSpeechDeviceId
        ? '无法使用所选麦克风，请刷新设备列表或改选其他输入设备。'
        : '无法访问麦克风，请检查浏览器权限后重试。');
      void refreshSpeechDevices();
    }
  }, [finalizeSpeechRecording, refreshSpeechDevices, selectedSpeechDeviceId, speechDevices, startSpeechMeter, stopSpeechRecording]);

  const handleSpeechToggle = () => {
    if (speechState === 'recording') {
      stopSpeechRecording();
      return;
    }
    if (speechState === 'idle') {
      void startSpeechRecording();
    }
  };

  const handleSpeechDeviceChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const deviceId = event.target.value;
    setSelectedSpeechDeviceId(deviceId);
    persistSpeechDeviceId(deviceId);
    setSpeechError('');
  };

  const handleSend = () => {
    startAgentStream(input);
  };

  const handleCodingSubmit = async (task: CodingTask, language: string, code: string) => {
    const result = await submitCodingTask(task.id, language, code);
    setCodingTask(null);
    const languageLabel = CODING_LANGUAGE_LABELS[language] || language;
    startAgentStream(`已提交代码题：${task.title}（${languageLabel}）`, result.contextMessage);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    const nativeEvent = e.nativeEvent as KeyboardEvent;
    if (isComposing || nativeEvent.isComposing || nativeEvent.keyCode === 229) {
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleEnd = () => {
    if (autoEndTimerRef.current !== null) {
      window.clearTimeout(autoEndTimerRef.current);
      autoEndTimerRef.current = null;
    }
    abortRef.current?.abort();
    void onEnd();
  };

  const handlePause = () => {
    if (autoEndTimerRef.current !== null) {
      window.clearTimeout(autoEndTimerRef.current);
      autoEndTimerRef.current = null;
    }
    abortRef.current?.abort();
    void onPause();
  };

  const diffLabel = getInterviewTargetLabel(difficulty);
  const selectedSpeechDeviceName = selectedSpeechDeviceId
    ? speechDevices.find((device) => device.deviceId === selectedSpeechDeviceId)?.label || '已选择的麦克风'
    : '浏览器默认麦克风';
  const speechHintText = speechError ||
    (speechState === 'uploading'
      ? '正在转写语音，完成后会填入输入框。'
      : '可使用语音转写为文本，发送前请检查内容；请勿输入身份证号、手机号等敏感信息。');
  const speechSignalText = speechError || (hasSpeechSignal
    ? '已检测到麦克风输入'
    : recordingSeconds >= 2
      ? '未检测到明显声音，请检查麦克风或系统输入设备'
      : '请对准麦克风正常说话');
  const speechSignalClassName = speechError ? 'speech-signal-error' : hasSpeechSignal ? 'speech-signal-ok' : 'speech-signal-waiting';

  return (
    <div className={`chat-view ${codingTask ? 'with-coding' : ''}`}>
      <header className="chat-header">
        <div className="chat-header-info">
          <div className="chat-header-dot" />
          <span className="chat-header-domain">{DOMAIN_LABELS[domain] || domain}</span>
          <span className="chat-header-sep">/</span>
          <span className="chat-header-diff">{diffLabel}</span>
        </div>
        <div className="chat-header-actions">
          {contextUsage && <ContextUsageMeter usage={contextUsage} />}
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
          <button className="pause-button" onClick={handlePause}>
            中断面试
          </button>
          <button className="end-button" onClick={handleEnd}>
            结束面试
          </button>
        </div>
      </header>

      <div className="chat-body">
        <section className="chat-panel" aria-label="面试对话">
          {autoEndNotice && <div className="chat-toast" role="status">{autoEndNotice}</div>}
          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-empty">
                <p>面试官正在准备开场，请稍候。</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`message-row ${msg.role === 'user' ? 'user' : 'ai'}`}>
                {msg.role === 'ai' && (
                  <div className="ai-avatar">
                    <svg width="20" height="20" viewBox="0 0 36 36" fill="none">
                      <rect width="36" height="36" rx="8" fill="var(--color-accent)" />
                      <path d="M10 18L16 12L22 18L16 24Z" fill="white" opacity="0.9" />
                      <path d="M16 18L22 12L28 18L22 24Z" fill="white" opacity="0.6" />
                    </svg>
                  </div>
                )}
                <div className={`message-bubble ${msg.role}`}>
                  <MarkdownMessage content={msg.content} />
                  {msg.streaming && <span className="cursor-blink" />}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-bar">
            <button
              aria-label={speechState === 'recording' ? '停止录音' : '语音输入'}
              className={`voice-button ${speechState}`}
              onClick={handleSpeechToggle}
              disabled={speechState === 'uploading' || ((isStreaming || autoEnded) && speechState !== 'recording')}
              title={speechState === 'recording' ? '停止录音并转写' : '语音输入'}
              type="button"
            >
              {speechState === 'recording' ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <rect x="7" y="7" width="10" height="10" rx="2" />
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                  <line x1="12" y1="19" x2="12" y2="22" />
                </svg>
              )}
            </button>
            <textarea
              aria-label="面试回答"
              className="chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onCompositionStart={() => setIsComposing(true)}
              onCompositionEnd={() => setIsComposing(false)}
              onKeyDown={handleKeyDown}
              placeholder="输入你的回答..."
              rows={1}
              disabled={isStreaming || autoEnded}
            />
            <button
              aria-label="发送回答"
              className="send-button"
              onClick={handleSend}
              disabled={!input.trim() || isStreaming || autoEnded || speechState === 'uploading'}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
          <div className="speech-device-row">
            <label htmlFor="speech-device-select">麦克风</label>
            <div className="speech-device-control">
              <select
                id="speech-device-select"
                className="speech-device-select"
                value={selectedSpeechDeviceId}
                onChange={handleSpeechDeviceChange}
                onFocus={() => void refreshSpeechDevices()}
                disabled={speechState !== 'idle' || isStreaming || autoEnded}
                aria-label="选择麦克风输入设备"
              >
                <option value="">浏览器默认麦克风</option>
                {speechDevices.map((device, index) => (
                  <option key={device.deviceId || `speech-device-${index}`} value={device.deviceId}>
                    {getSpeechDeviceDisplayName(device, index)}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="speech-device-refresh"
                onClick={() => void refreshSpeechDevices()}
                disabled={speechState !== 'idle' || isRefreshingSpeechDevices}
                title="刷新麦克风列表"
                aria-label="刷新麦克风列表"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 12a9 9 0 0 1-15.3 6.4" />
                  <path d="M3 12A9 9 0 0 1 18.3 5.6" />
                  <path d="M18 2v4h-4" />
                  <path d="M6 22v-4h4" />
                </svg>
              </button>
            </div>
          </div>
          <div className={`speech-input-hint ${speechError ? 'error' : ''} ${speechState === 'recording' ? 'recording' : ''}`} role="status">
            {speechState === 'recording' ? (
              <div className="speech-meter-panel">
                <div className="speech-meter-header">
                  <span>正在录音 {formatSpeechRecordingTime(recordingSeconds)}</span>
                  <span className={speechSignalClassName}>{speechSignalText}</span>
                </div>
                <div className="speech-meter-track" aria-label="麦克风输入音量">
                  <div className="speech-meter-fill" style={{ width: `${speechVolume}%` }} />
                </div>
                <div className="speech-meter-footer">
                  当前麦克风：{currentSpeechDeviceLabel || selectedSpeechDeviceName}。再次点击麦克风停止并转写。
                </div>
              </div>
            ) : (
              speechHintText
            )}
          </div>
        </section>
        {codingTask && (
          <Suspense fallback={<aside className="coding-workspace coding-loading">正在加载手撕平台...</aside>}>
            <CodingWorkspace
              key={`${codingTask.id}-${codingTask.status}`}
              task={codingTask}
              theme={theme}
              onSubmit={handleCodingSubmit}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}

function LoadingView({
  message,
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="setup-view">
      <div className="loading-panel">
        <div className="logo-mark">
          <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
            <rect width="36" height="36" rx="8" fill="var(--color-accent)" />
            <path d="M10 18L16 12L22 18L16 24Z" fill="white" opacity="0.9" />
            <path d="M16 18L22 12L28 18L22 24Z" fill="white" opacity="0.6" />
          </svg>
        </div>
        <div>
          <h1>正在连接面试系统</h1>
          <p>{message || '正在校验登录状态，请稍候。'}</p>
          {onRetry && (
            <div className="loading-actions">
              <button className="secondary-button" type="button" onClick={onRetry}>
                重新校验
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const ADMIN_METRIC_LABELS: Record<string, string> = {
  login_success: '登录成功',
  session_created: '新增面试',
  chat_turn: '对话轮次',
  speech_transcribed: '语音转写',
  coding_submitted: '手撕提交',
  session_completed: '完成面试',
  session_paused: '中断面试',
};

function AdminLoginView({
  theme,
  onToggleTheme,
  onLogin,
}: {
  theme: ThemeMode;
  onToggleTheme: () => void;
  onLogin: (username: string) => void;
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      const result = await adminLogin(username, password);
      onLogin(result.username);
    } catch (err) {
      setError(err instanceof Error ? err.message : '管理员登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="admin-auth-shell">
      <section className="admin-auth-intro">
        <LogoMark />
        <p className="eyebrow">Admin Console</p>
        <h1>Interview Agent 监控后台</h1>
        <p>独立管理员入口，只展示在线状态和聚合使用情况，不展示用户面试内容、简历正文或代码全文。</p>
      </section>
      <section className="admin-auth-card" aria-label="管理员登录">
        <div className="admin-auth-card-head">
          <div>
            <p className="eyebrow">Secure Access</p>
            <h2>管理员登录</h2>
          </div>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
        <form className="login-form" onSubmit={handleSubmit}>
          <div className="login-field">
            <label className="section-label" htmlFor="admin-username">管理员账号</label>
            <input
              id="admin-username"
              type="text"
              className="custom-input"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="login-field">
            <label className="section-label" htmlFor="admin-password">密码</label>
            <input
              id="admin-password"
              type="password"
              className="custom-input"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          {error && <div className="login-error" role="alert">{error}</div>}
          <button className="start-button" type="submit" disabled={loading || !username || !password}>
            {loading ? '验证中...' : '进入监控后台'}
          </button>
        </form>
      </section>
    </div>
  );
}

function AdminDashboardView({
  username,
  theme,
  onToggleTheme,
  onLogout,
}: {
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  onLogout: () => void;
}) {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [presence, setPresence] = useState<AdminPresenceUser[]>([]);
  const [usage, setUsage] = useState<AdminDailyUsage[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const applyAdminData = useCallback((
    overviewData: AdminOverview,
    presenceData: AdminPresenceUser[],
    usageData: AdminDailyUsage[],
  ) => {
    setOverview(overviewData);
    setPresence(presenceData);
    setUsage(usageData);
    setError('');
  }, []);

  const loadAdminData = useCallback(async () => {
    setLoading(true);
    try {
      const [overviewData, presenceData, usageData] = await Promise.all([
        fetchAdminOverview(),
        fetchAdminPresence(),
        fetchAdminDailyUsage(7),
      ]);
      applyAdminData(overviewData, presenceData, usageData);
    } catch (err) {
      if (err instanceof Error && err.message === 'ADMIN_UNAUTHORIZED') {
        onLogout();
      } else {
        setError('监控数据加载失败，请稍后刷新。');
      }
    } finally {
      setLoading(false);
    }
  }, [applyAdminData, onLogout]);

  useEffect(() => {
    let ignore = false;
    Promise.all([fetchAdminOverview(), fetchAdminPresence(), fetchAdminDailyUsage(7)])
      .then(([overviewData, presenceData, usageData]) => {
        if (!ignore) applyAdminData(overviewData, presenceData, usageData);
      })
      .catch((err) => {
        if (ignore) return;
        if (err instanceof Error && err.message === 'ADMIN_UNAUTHORIZED') {
          onLogout();
        } else {
          setError('监控数据加载失败，请稍后刷新。');
        }
      });
    return () => {
      ignore = true;
    };
  }, [applyAdminData, onLogout]);

  const today = overview?.today || {};
  const maxDailyChat = Math.max(1, ...usage.map((day) => day.metrics.chat_turn || 0));

  return (
    <div className="setup-view admin-monitor-view">
      <div className="console-shell admin-monitor-shell">
        <header className="console-topbar admin-topbar">
          <div className="brand-lockup">
            <LogoMark />
            <span>Interview Agent 管理后台</span>
          </div>
          <div className="user-badge">
            <span className="system-pill">Admin</span>
            <ThemeToggle theme={theme} onToggle={onToggleTheme} />
            <span className="user-badge-name">{username}</span>
            <button className="logout-link" onClick={onLogout}>退出</button>
          </div>
        </header>

        <main className="admin-monitor-grid">
          <section className="admin-hero">
            <div>
              <p className="eyebrow">Operations</p>
              <h1>站点使用情况概览</h1>
              <p>用于部署前检查和日常观察，只展示低敏聚合信息。</p>
            </div>
            <button className="secondary-button admin-refresh-button" onClick={() => void loadAdminData()} disabled={loading}>
              <RefreshCw size={16} aria-hidden="true" />
              <span>{loading ? '刷新中' : '刷新'}</span>
            </button>
          </section>

          {error && <div className="login-error admin-error" role="alert">{error}</div>}

          <section className="admin-metric-grid" aria-label="关键指标">
            <article className="admin-metric-card">
              <Users size={20} aria-hidden="true" />
              <span>当前在线</span>
              <strong>{overview?.online_users ?? '-'}</strong>
              <small>5 分钟内 heartbeat</small>
            </article>
            <article className="admin-metric-card">
              <Activity size={20} aria-hidden="true" />
              <span>最近活跃</span>
              <strong>{overview?.recent_users ?? '-'}</strong>
              <small>15 分钟内活动用户</small>
            </article>
            <article className="admin-metric-card">
              <ShieldCheck size={20} aria-hidden="true" />
              <span>进行中面试</span>
              <strong>{overview?.active_sessions ?? '-'}</strong>
              <small>active 状态会话</small>
            </article>
            <article className="admin-metric-card">
              <BarChart3 size={20} aria-hidden="true" />
              <span>今日对话</span>
              <strong>{today.chat_turn ?? 0}</strong>
              <small>用户发送轮次</small>
            </article>
          </section>

          <section className="admin-panel admin-presence-panel" aria-label="在线用户">
            <div className="admin-panel-head">
              <div>
                <p className="eyebrow">Presence</p>
                <h2>在线与最近活跃</h2>
              </div>
              <span>{presence.length} 人</span>
            </div>
            <div className="admin-presence-list">
              {presence.length === 0 && <div className="history-empty">暂无最近活跃用户。</div>}
              {presence.map((user) => (
                <article className="admin-presence-row" key={user.user_id}>
                  <div>
                    <strong>{user.username}</strong>
                    <small>{user.current_view || 'unknown'}{user.active_session_id ? ` · ${user.active_session_id.slice(0, 8)}` : ''}</small>
                  </div>
                  <span className={`admin-presence-status ${user.status}`}>{user.status === 'online' ? '在线' : '最近活跃'}</span>
                  <time>{formatDateTime(user.last_seen_at)}</time>
                </article>
              ))}
            </div>
          </section>

          <section className="admin-panel admin-usage-panel" aria-label="今日使用统计">
            <div className="admin-panel-head">
              <div>
                <p className="eyebrow">Today</p>
                <h2>今日使用统计</h2>
              </div>
            </div>
            <div className="admin-usage-grid">
              {Object.entries(ADMIN_METRIC_LABELS).map(([metric, label]) => (
                <div className="admin-usage-item" key={metric}>
                  <span>{label}</span>
                  <strong>{today[metric] ?? 0}</strong>
                </div>
              ))}
            </div>
          </section>

          <section className="admin-panel admin-trend-panel" aria-label="最近七天趋势">
            <div className="admin-panel-head">
              <div>
                <p className="eyebrow">7 Days</p>
                <h2>最近七天对话趋势</h2>
              </div>
            </div>
            <div className="admin-trend-list">
              {usage.map((day) => {
                const chatTurns = day.metrics.chat_turn || 0;
                return (
                  <div className="admin-trend-row" key={day.date}>
                    <time>{day.date.slice(5)}</time>
                    <div className="admin-trend-track" aria-hidden="true">
                      <span style={{ width: `${Math.max(4, Math.round((chatTurns / maxDailyChat) * 100))}%` }} />
                    </div>
                    <strong>{chatTurns}</strong>
                  </div>
                );
              })}
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

function AdminApp() {
  const location = useLocation();
  const navigate = useNavigate();
  const [theme, setTheme] = useState<ThemeMode>(() => getInitialTheme());
  const [username, setUsername] = useState('');
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState('');
  const [authRetryNonce, setAuthRetryNonce] = useState(0);

  useEffect(() => {
    persistTheme(theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  };

  useEffect(() => {
    let ignore = false;
    void getAdminMe()
      .then((me) => {
        if (ignore) return;
        setAuthError('');
        if (me) {
          setUsername(me.username);
          if (location.pathname === ROUTES.adminLogin) {
            navigate(ROUTES.admin, { replace: true });
          }
        } else {
          setUsername('');
          if (location.pathname !== ROUTES.adminLogin) {
            navigate(ROUTES.adminLogin, { replace: true });
          }
        }
      })
      .catch(() => {
        if (!ignore) setAuthError('管理员登录状态校验暂时失败，请稍候重试。');
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [authRetryNonce, location.pathname, navigate]);

  const handleLogin = (adminUsername: string) => {
    setUsername(adminUsername);
    navigate(ROUTES.admin, { replace: true });
  };

  const handleLogout = useCallback(async () => {
    await adminLogout().catch(() => undefined);
    setUsername('');
    navigate(ROUTES.adminLogin, { replace: true });
  }, [navigate]);

  if (loading || authError) {
    return (
      <LoadingView
        message={authError || undefined}
        onRetry={authError ? () => {
          setAuthError('');
          setLoading(true);
          setAuthRetryNonce((current) => current + 1);
        } : undefined}
      />
    );
  }
  if (!username || location.pathname === ROUTES.adminLogin) {
    return <AdminLoginView theme={theme} onToggleTheme={toggleTheme} onLogin={handleLogin} />;
  }
  return <AdminDashboardView username={username} theme={theme} onToggleTheme={toggleTheme} onLogout={handleLogout} />;
}

function UserApp() {
  const location = useLocation();
  const navigate = useNavigate();
  const latestPathRef = useRef(location.pathname);
  const authRetryTimerRef = useRef<number | null>(null);
  const authFailureCountRef = useRef(0);
  const lastHeartbeatAtRef = useRef(0);
  const logoutInFlightRef = useRef(false);
  const [view, setView] = useState<View>('loading');
  const [theme, setTheme] = useState<ThemeMode>(() => getInitialTheme());
  const [sessionId, setSessionId] = useState('');
  const [domain, setDomain] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [username, setUsername] = useState('');
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [historyNoticeDismissed, setHistoryNoticeDismissed] = useState(() => hasDismissedHistoryNotice());
  const [historyManageModeDefault, setHistoryManageModeDefault] = useState(false);
  const [resourceLoadError, setResourceLoadError] = useState('');
  const [authRetryNonce, setAuthRetryNonce] = useState(0);
  const [authRetryMessage, setAuthRetryMessage] = useState('');
  const interviewRouteSessionId = getRouteSessionId(location.pathname, 'interview');
  const historyRouteSessionId = getRouteSessionId(location.pathname, 'history');

  useEffect(() => {
    persistTheme(theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  };

  useEffect(() => {
    latestPathRef.current = location.pathname;
  }, [location.pathname]);

  const navigateToView = useCallback((nextView: View, options?: { replace?: boolean }) => {
    const route = userViewToRoute(nextView);
    if (route && location.pathname !== route) {
      latestPathRef.current = route;
      navigate(route, { replace: options?.replace });
    }
    setView(nextView);
  }, [location.pathname, navigate]);

  const retryAuthCheck = useCallback(() => {
    if (authRetryTimerRef.current !== null) {
      window.clearTimeout(authRetryTimerRef.current);
      authRetryTimerRef.current = null;
    }
    setAuthRetryMessage('');
    setResourceLoadError('');
    setView('loading');
    setAuthRetryNonce((current) => current + 1);
  }, []);

  const handleAuthExpired = useCallback(() => {
    if (authRetryTimerRef.current !== null) {
      window.clearTimeout(authRetryTimerRef.current);
      authRetryTimerRef.current = null;
    }
    clearActiveBrowserSession();
    setUsername('');
    setHistoryNoticeDismissed(false);
    setHistoryManageModeDefault(false);
    setAuthRetryMessage('');
    setResourceLoadError('登录状态已过期，请重新登录。');
    setView('login');
    if (latestPathRef.current !== ROUTES.login) {
      latestPathRef.current = ROUTES.login;
      navigate(ROUTES.login, { replace: true });
    }
  }, [navigate]);

  useEffect(() => {
    let ignore = false;
    void getMe()
      .then((me) => {
        if (ignore) return;
        authFailureCountRef.current = 0;
        setAuthRetryMessage('');
        if (me) {
          markActiveBrowserSession();
          setResourceLoadError('');
          setUsername(me.username);
          setHistoryNoticeDismissed(hasDismissedHistoryNotice());
          const latestPath = latestPathRef.current;
          const requestedView = routeToUserView(latestPath);
          const nextView = requestedView && requestedView !== 'login' ? requestedView : 'dashboard';
          setView(nextView);
          const nextRoute = userViewToRoute(nextView) ?? ROUTES.dashboard;
          const shouldKeepResourceRoute = Boolean(
            getRouteSessionId(latestPath, 'interview') || getRouteSessionId(latestPath, 'history'),
          );
          if (!shouldKeepResourceRoute && latestPath !== nextRoute) {
            navigate(nextRoute, { replace: true });
          }
        } else {
          clearActiveBrowserSession();
          setUsername('');
          setResourceLoadError('');
          setView('login');
          if (latestPathRef.current !== ROUTES.login) {
            latestPathRef.current = ROUTES.login;
            navigate(ROUTES.login, { replace: true });
          }
        }
      })
      .catch(() => {
        if (ignore) return;
        const failureCount = authFailureCountRef.current;
        const delay = AUTH_RETRY_DELAYS_MS[Math.min(failureCount, AUTH_RETRY_DELAYS_MS.length - 1)];
        authFailureCountRef.current = failureCount + 1;
        const retrySeconds = Math.ceil(delay / 1000);
        const message = `登录状态校验暂时失败，系统将在 ${retrySeconds} 秒后自动重试。`;
        setAuthRetryMessage(message);
        setResourceLoadError(message);
        setView('loading');
        if (authRetryTimerRef.current !== null) {
          window.clearTimeout(authRetryTimerRef.current);
        }
        authRetryTimerRef.current = window.setTimeout(() => {
          authRetryTimerRef.current = null;
          setAuthRetryNonce((current) => current + 1);
        }, delay);
      });

    return () => {
      ignore = true;
    };
  }, [authRetryNonce, navigate]);

  useEffect(() => () => {
    if (authRetryTimerRef.current !== null) {
      window.clearTimeout(authRetryTimerRef.current);
    }
  }, []);

  useEffect(() => {
    const heartbeatView = username ? resolveAuthenticatedUserView(location.pathname, view) : view;
    if (
      !username
      || location.pathname === ROUTES.login
      || heartbeatView === 'loading'
      || heartbeatView === 'login'
    ) return;

    const sendHeartbeat = () => {
      if (location.pathname === ROUTES.login) return;
      if (document.visibilityState === 'hidden') return;
      const now = Date.now();
      if (now - lastHeartbeatAtRef.current < PRESENCE_HEARTBEAT_MIN_INTERVAL_MS) return;
      lastHeartbeatAtRef.current = now;
      void sendPresenceHeartbeat(heartbeatView, heartbeatView === 'chat' ? sessionId : '')
        .catch((err) => {
          if (err instanceof Error && err.message === 'UNAUTHORIZED') {
            handleAuthExpired();
          }
        });
    };

    sendHeartbeat();
    const intervalId = window.setInterval(sendHeartbeat, PRESENCE_HEARTBEAT_MS);
    document.addEventListener('visibilitychange', sendHeartbeat);
    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', sendHeartbeat);
    };
  }, [handleAuthExpired, location.pathname, sessionId, username, view]);

  const handleLogin = (user: string) => {
    markActiveBrowserSession();
    clearHistoryNoticeDismissed();
    setResourceLoadError('');
    setAuthRetryMessage('');
    setUsername(user);
    setHistoryNoticeDismissed(false);
    setHistoryManageModeDefault(false);
    navigateToView('dashboard', { replace: true });
  };

  const handleLogout = useCallback(async () => {
    if (logoutInFlightRef.current) return;
    logoutInFlightRef.current = true;
    clearActiveBrowserSession();
    clearHistoryNoticeDismissed();
    try {
      await logout().catch(() => undefined);
      setUsername('');
      setHistoryNoticeDismissed(false);
      setHistoryManageModeDefault(false);
      setAuthRetryMessage('');
      navigateToView('login', { replace: true });
    } finally {
      logoutInFlightRef.current = false;
    }
  }, [navigateToView]);

  useEffect(() => {
    if (!username || !interviewRouteSessionId) return;
    if (sessionId === interviewRouteSessionId && domain && difficulty) return;

    let ignore = false;
    void Promise.resolve()
      .then(() => {
        if (!ignore) setResourceLoadError('');
        return fetchInterviewSessionDetail(interviewRouteSessionId);
      })
      .then(async (detail) => {
        if (detail.session.status === 'completed') {
          navigate(ROUTES.historyDetail(interviewRouteSessionId), { replace: true });
          return null;
        }
        if (detail.session.status === 'paused') {
          return resumeInterviewSession(interviewRouteSessionId);
        }
        return detail;
      })
      .then((detail) => {
        if (ignore || !detail) return;
        setSessionId(detail.session.id);
        setDomain(detail.session.domain);
        setDifficulty(detail.session.difficulty);
        setChatMessages(toChatMessages(detail.messages));
        setView('chat');
      })
      .catch((err) => {
        if (ignore) return;
        if (err instanceof Error && err.message === 'UNAUTHORIZED') {
          void handleLogout();
        } else {
          setResourceLoadError('面试会话加载失败，请从历史记录重新进入。');
        }
      });

    return () => {
      ignore = true;
    };
  }, [difficulty, domain, handleLogout, interviewRouteSessionId, navigate, sessionId, username]);

  const handleStart = async (
    d: string,
    diff: string,
    jd: string,
    profileCompany: string,
    profilePosition: string,
    resumeId: number | null,
  ) => {
    try {
      const created = await createSession(d, diff, jd, profileCompany, profilePosition, resumeId);
      setSessionId(created.sessionId);
      setDomain(d);
      setDifficulty(diff);
      setChatMessages(toChatMessages(created.messages));
      latestPathRef.current = ROUTES.interview(created.sessionId);
      navigate(ROUTES.interview(created.sessionId));
      setView('chat');
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        handleLogout();
      } else {
        alert('创建会话失败，请检查后端服务是否启动');
      }
    }
  };

  const handleEnd = async () => {
    if (sessionId) {
      await endInterviewSession(sessionId).catch(() => undefined);
    }
    navigateToView('dashboard');
    setSessionId('');
    setChatMessages([]);
  };

  const handlePause = async () => {
    try {
      if (sessionId) {
        await pauseInterviewSession(sessionId);
      }
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        await handleLogout();
      } else {
        alert('中断面试失败，请稍后重试');
      }
      return;
    }
    navigateToView('dashboard');
    setSessionId('');
    setChatMessages([]);
  };

  const handleResume = (detail: InterviewSessionDetail) => {
    setSessionId(detail.session.id);
    setDomain(detail.session.domain);
    setDifficulty(detail.session.difficulty);
    setChatMessages(toChatMessages(detail.messages));
    latestPathRef.current = ROUTES.interview(detail.session.id);
    navigate(ROUTES.interview(detail.session.id));
    setView('chat');
  };

  const goHome = () => {
    setSessionId('');
    setChatMessages([]);
    setHistoryManageModeDefault(false);
    navigateToView('dashboard');
  };

  const openHistory = () => {
    setHistoryManageModeDefault(false);
    navigateToView('history');
  };

  const openHistoryDetail = (selectedSessionId: string) => {
    setHistoryManageModeDefault(false);
    const route = ROUTES.historyDetail(selectedSessionId);
    latestPathRef.current = route;
    navigate(route);
  };

  const clearHistoryDetail = () => {
    latestPathRef.current = ROUTES.history;
    navigate(ROUTES.history, { replace: true });
  };

  const openHistoryManagement = () => {
    markHistoryNoticeDismissed();
    setHistoryNoticeDismissed(true);
    setHistoryManageModeDefault(true);
    navigateToView('history');
  };

  const dismissHistoryNotice = () => {
    markHistoryNoticeDismissed();
    setHistoryNoticeDismissed(true);
  };

  const routeView = username ? routeToUserView(location.pathname) : null;
  const activeView = username ? resolveAuthenticatedUserView(location.pathname, view) : view;
  const isLoadingInterviewRoute = activeView === 'chat'
    && Boolean(interviewRouteSessionId)
    && (sessionId !== interviewRouteSessionId || !domain || !difficulty);
  const showMobileNavigation = shouldShowMobileNavigation(activeView);
  const activeMobileNavigationItem = getActiveMobileNavigationItem(activeView);

  const handleMobileNavigation = (item: MobileNavigationItem) => {
    if (item === 'dashboard') {
      goHome();
    } else if (item === 'history') {
      openHistory();
    } else {
      navigateToView(item);
    }
  };

  return (
    <div className={`app-shell ${showMobileNavigation ? 'has-mobile-navigation' : ''}`}>
      {username && view !== 'loading' && view !== 'chat' && routeView === 'login' && (
        <Navigate to={ROUTES.dashboard} replace />
      )}
      {activeView === 'loading' && (
        <LoadingView
          message={authRetryMessage || undefined}
          onRetry={authRetryMessage ? retryAuthCheck : undefined}
        />
      )}
      {activeView === 'login' && <LoginView onLogin={handleLogin} />}
      {resourceLoadError && activeView !== 'login' && activeView !== 'loading' && (
        <div className="login-error route-load-error" role="alert">{resourceLoadError}</div>
      )}
      {activeView === 'dashboard' && (
        <DashboardView
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          onStartInterview={() => navigateToView('setup')}
          onProfile={() => navigateToView('profile')}
          onHistory={openHistory}
          onManageHistory={openHistoryManagement}
          onInsights={() => navigateToView('insights')}
          onLogout={handleLogout}
          historyNoticeDismissed={historyNoticeDismissed}
          onDismissHistoryNotice={dismissHistoryNotice}
        />
      )}
      {activeView === 'setup' && (
        <SetupView
          onStart={handleStart}
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          onLogout={handleLogout}
          onBack={goHome}
          onProfile={() => navigateToView('profile')}
        />
      )}
      {activeView === 'chat' && isLoadingInterviewRoute && <LoadingView />}
      {activeView === 'chat' && !isLoadingInterviewRoute && (
        <ChatView
          key={sessionId}
          sessionId={sessionId}
          domain={domain}
          difficulty={difficulty}
          initialMessages={chatMessages}
          theme={theme}
          onToggleTheme={toggleTheme}
          onPause={handlePause}
          onEnd={handleEnd}
          onAuthExpired={handleAuthExpired}
        />
      )}
      {activeView === 'profile' && (
        <ResumeManagerView
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          onHome={goHome}
          onStartInterview={() => navigateToView('setup')}
          onLogout={handleLogout}
        />
      )}
      {activeView === 'history' && (
        <HistoryView
          key={historyRouteSessionId || 'history'}
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          initialManageMode={historyManageModeDefault}
          selectedSessionId={historyRouteSessionId || undefined}
          onHome={goHome}
          onStartInterview={() => navigateToView('setup')}
          onSelectSession={openHistoryDetail}
          onClearSelectedSession={clearHistoryDetail}
          onResumeInterview={handleResume}
          onLogout={handleLogout}
        />
      )}
      {activeView === 'insights' && (
        <PlaceholderView
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          title="AI 表现总结"
          eyebrow="Insights"
          description="这个页面先作为历史表现分析入口预留。后续接入后，将基于多轮面试记录总结知识覆盖、表达质量和提升建议。"
          blocks={[
            { label: 'Coverage', title: '知识覆盖', description: '分析常见技术主题的掌握情况和薄弱区域。' },
            { label: 'Depth', title: '追问表现', description: '总结面对深入追问时的稳定性、完整度和边界意识。' },
            { label: 'Action', title: '改进建议', description: '输出下一阶段更适合训练的问题类型和复习重点。' },
          ]}
          onHome={goHome}
          onStartInterview={() => navigateToView('setup')}
          onLogout={handleLogout}
        />
      )}
      {showMobileNavigation && (
        <MobileBottomNav
          activeItem={activeMobileNavigationItem}
          onNavigate={handleMobileNavigation}
        />
      )}
      <footer className={`site-footer ${showMobileNavigation ? 'with-mobile-navigation' : ''}`}>
        <span className="app-version">Interview Agent {APP_VERSION}</span>
        <a className="beian-link" href="https://beian.miit.gov.cn" target="_blank" rel="noopener noreferrer">
          浙ICP备2026035635号
        </a>
        <a
          className="beian-link police-beian"
          href="https://beian.mps.gov.cn/#/query/webSearch?code=33019202003045"
          target="_blank"
          rel="noopener noreferrer"
        >
          <img src="/beian-police.png" alt="" aria-hidden="true" />
          <span>浙公网安备33019202003045号</span>
        </a>
      </footer>
    </div>
  );
}

function App() {
  return (
    <Routes>
      {ADMIN_ROUTE_ENTRIES.map((route) => (
        <Route key={route.path} path={route.path} element={<AdminApp />} />
      ))}
      <Route path="*" element={<UserApp />} />
    </Routes>
  );
}

export default App;

import { lazy, Suspense, useState, useRef, useEffect, useCallback } from 'react';
import {
  createSession,
  createResume,
  deleteInterviewSession,
  deleteInterviewSessions,
  deleteResume,
  endInterviewSession,
  fetchActiveCodingTask,
  fetchDomains,
  fetchInterviewSessionDetail,
  fetchInterviewSessions,
  fetchLastInterviewConfig,
  fetchProfiles,
  fetchResumes,
  getMe,
  login,
  logout,
  pauseInterviewSession,
  register,
  resumeInterviewSession,
  streamChat,
  submitCodingTask,
  updateResume,
  type CodingTask,
  type InterviewMessage,
  type InterviewSessionDetail,
  type InterviewSessionSummary,
  type LastInterviewConfig,
  type Resume,
  type ResumeProject,
} from './api';
import { CODING_LANGUAGE_LABELS } from './codingLanguages';
import { RELEASE_NOTES } from './releaseNotes';
import { APP_VERSION } from './version';

const CodingWorkspace = lazy(() => import('./CodingWorkspace'));

type View = 'loading' | 'login' | 'dashboard' | 'setup' | 'chat' | 'profile' | 'history' | 'insights';
type ThemeMode = 'light' | 'dark';

interface Message {
  role: 'user' | 'ai';
  content: string;
  streaming?: boolean;
}

const AUTH_SESSION_KEY = 'interviewlg_active_session';
const HISTORY_NOTICE_DISMISSED_KEY = 'interviewlg_history_notice_dismissed';
const THEME_STORAGE_KEY = 'interviewlg_theme';
const HISTORY_WARNING_THRESHOLD = 45;

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

function hasActiveBrowserSession(): boolean {
  try {
    return sessionStorage.getItem(AUTH_SESSION_KEY) === '1';
  } catch {
    return false;
  }
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

const DIFFICULTY_OPTIONS = [
  { value: 'junior', label: '初级', meta: '实习至 1 年经验', description: '侧重基础概念、常见业务实现、代码可读性与排错思路。' },
  { value: 'mid', label: '中级', meta: '1 至 3 年经验', description: '加入工程实践、模块设计、性能取舍和线上问题处理。' },
  { value: 'senior', label: '高级', meta: '3 年以上经验', description: '强调系统设计、技术决策、复杂场景拆解和跨团队协作。' },
];

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
        <span>{title}</span>
      </div>
      <div className="user-badge">
        <span className="system-pill">已登录</span>
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        <span className="user-badge-name">{username}</span>
        {onHome && <button className="ghost-link" onClick={onHome}>工作台</button>}
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
              选择方向、难度与岗位信息后进入模拟问答。系统会围绕目标岗位持续追问，适合面试前做集中演练。
            </p>
          </div>

          <div className="auth-metrics" aria-label="系统能力摘要">
            <div>
              <span>Preset</span>
              <strong>8</strong>
              <small>技术方向</small>
            </div>
            <div>
              <span>Levels</span>
              <strong>3</strong>
              <small>面试难度</small>
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
              <p>确认技术方向、岗位难度和目标 JD。</p>
            </div>
            <div>
              <span>02</span>
              <strong>进入问答</strong>
              <p>用连续追问模拟真实技术面试节奏。</p>
            </div>
            <div>
              <span>03</span>
              <strong>调整强度</strong>
              <p>按当前准备阶段切换初级、中级或高级难度。</p>
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
  const shouldShowHistoryNotice = !summaryUnavailable
    && sessions.length > HISTORY_WARNING_THRESHOLD
    && !historyNoticeDismissed;

  return (
    <div className="setup-view">
      <div className="console-shell dashboard-shell">
        <ConsoleTopbar title="Interview Agent 工作台" username={username} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} />

        <main className="dashboard-grid">
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
              <p>配置方向、难度和 JD 后进入连续追问。</p>
              <button className="start-button launch-button" onClick={onStartInterview}>开始模拟面试</button>
            </div>
          </section>

          <section className="dashboard-actions" aria-label="功能入口">
            <button className="workspace-action primary" onClick={onStartInterview}>
              <em>01</em>
              <span>开始面试配置</span>
              <strong>模拟技术面试</strong>
              <small>选择技术方向、难度、JD 与面试偏好，进入 AI 面试官对话。</small>
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
              <small>后续展示每次练习的方向、难度、时间和面试状态。</small>
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
                  ? `${DOMAIN_LABELS[latestSession.domain] || latestSession.domain} / ${DIFFICULTY_OPTIONS.find((d) => d.value === latestSession.difficulty)?.label || latestSession.difficulty}`
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
  onHome,
  onStartInterview,
  onResumeInterview,
  onLogout,
}: {
  username: string;
  theme: ThemeMode;
  onToggleTheme: () => void;
  initialManageMode: boolean;
  onHome: () => void;
  onStartInterview: () => void;
  onResumeInterview: (detail: InterviewSessionDetail) => void;
  onLogout: () => void;
}) {
  const [sessions, setSessions] = useState<InterviewSessionSummary[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<InterviewSessionDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState('');
  const [manageMode, setManageMode] = useState(initialManageMode);
  const [checkedIds, setCheckedIds] = useState<string[]>([]);

  const loadSessions = useCallback(async () => {
    setLoadingList(true);
    setError('');
    try {
      const rows = await fetchInterviewSessions(100);
      setSessions(rows);
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        onLogout();
      } else {
        setError('历史记录加载失败，请稍后重试。');
      }
    } finally {
      setLoadingList(false);
    }
  }, [onLogout]);

  useEffect(() => {
    let ignore = false;
    fetchInterviewSessions(100)
      .then((rows) => {
        if (!ignore) {
          setSessions(rows);
        }
      })
      .catch((err) => {
        if (ignore) return;
        if (err instanceof Error && err.message === 'UNAUTHORIZED') {
          onLogout();
        } else {
          setError('历史记录加载失败，请稍后重试。');
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoadingList(false);
        }
      });
    return () => {
      ignore = true;
    };
  }, [onLogout]);

  const selectSession = async (sessionId: string) => {
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
  };

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
                    <strong>{DOMAIN_LABELS[session.domain] || session.domain} / {DIFFICULTY_OPTIONS.find((d) => d.value === session.difficulty)?.label || session.difficulty}</strong>
                    <small>{formatDateTime(session.created_at)} · {session.message_count} 条消息</small>
                  </label>
                ) : (
                  <button
                    key={session.id}
                    className={`history-record ${session.id === selectedId ? 'active' : ''}`}
                    onClick={() => void selectSession(session.id)}
                    aria-pressed={session.id === selectedId}
                  >
                    <span>{STATUS_LABELS[session.status] || session.status}</span>
                    <strong>{DOMAIN_LABELS[session.domain] || session.domain} / {DIFFICULTY_OPTIONS.find((d) => d.value === session.difficulty)?.label || session.difficulty}</strong>
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
                    <h2>{DOMAIN_LABELS[detail.session.domain] || detail.session.domain} / {DIFFICULTY_OPTIONS.find((d) => d.value === detail.session.difficulty)?.label || detail.session.difficulty}</h2>
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

                {detail.coding_tasks.length > 0 && (
                  <section className="history-coding-section" aria-label="本场代码题">
                    <div className="section-heading">
                      <p className="eyebrow">Coding Tasks</p>
                      <h2>本场代码题</h2>
                    </div>
                    <div className="history-coding-list">
                      {detail.coding_tasks.map((task, index) => (
                        <article className="history-coding-card" key={task.id}>
                          <div className="qa-card-head">
                            <span>Task {index + 1}</span>
                            <small>{task.status === 'submitted' ? `已提交 · ${formatDateTime(task.submitted_at)}` : '未提交'}</small>
                          </div>
                          <h3>{task.title}</h3>
                          <p>{task.description}</p>
                          {task.submitted_code ? (
                            <pre><code>{task.submitted_code}</code></pre>
                          ) : (
                            <div className="history-empty">这道题还没有提交代码。</div>
                          )}
                        </article>
                      ))}
                    </div>
                  </section>
                )}

                <div className="qa-list">
                  {qaPairs.length === 0 && <div className="history-empty">这次面试还没有可回看的 QA。</div>}
                  {qaPairs.map((pair, index) => (
                    <article className="qa-card" key={`${pair.question.seq}-${index}`}>
                      <div className="qa-card-head">
                        <span>Q{index + 1}</span>
                        <small>{formatDateTime(pair.question.created_at)}</small>
                      </div>
                      <div className="qa-message user">
                        <strong>我的回答</strong>
                        <p>{pair.question.content}</p>
                      </div>
                      <div className="qa-message ai">
                        <strong>AI 面试官</strong>
                        <p>{pair.answer?.content || '这轮还没有 AI 回复。'}</p>
                      </div>
                    </article>
                  ))}
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
  const [difficulty, setDifficulty] = useState('mid');
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

    setDifficulty(config.difficulty || 'mid');
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
    onStart(activeDomain, difficulty, jobDescription, profileCompany, profilePosition, selectedResumeId);
  };

  return (
    <div className="setup-view">
      <div className="console-shell">
        <ConsoleTopbar title="模拟技术面试" username={username} theme={theme} onToggleTheme={onToggleTheme} onLogout={onLogout} onHome={onBack} />

        <div className="console-grid">
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
                  <strong>面试难度</strong>
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
                <p className="setup-subtitle">保留必要输入，减少多余选择。方向决定问题范围，难度决定追问深度，JD 会让问题更贴近真实招聘要求。</p>
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

            <section className="config-section">
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

            <section className="config-section">
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
                    <small>按技术方向、难度和 JD 生成通用面试问题。</small>
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

            <section className="config-section">
              <div className="section-heading">
                <label className="section-label">面试难度</label>
                <p>按你的目标岗位和经验年限选择，难度越高越强调方案取舍和追问深度。</p>
              </div>
              <div className="difficulty-grid">
                {DIFFICULTY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    className={`difficulty-card ${difficulty === opt.value ? 'active' : ''}`}
                    onClick={() => setDifficulty(opt.value)}
                    aria-pressed={difficulty === opt.value}
                  >
                    <em>{opt.value === 'junior' ? '01' : opt.value === 'mid' ? '02' : '03'}</em>
                    <span>{opt.label}</span>
                    <strong>{opt.meta}</strong>
                    <small>{opt.description}</small>
                  </button>
                ))}
              </div>
            </section>

            <div className="context-grid">
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
                <span>难度</span>
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
                <li>校招、实习或 1 年内经验建议从初级开始。</li>
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

function ChatView({
  sessionId,
  domain,
  difficulty,
  initialMessages,
  theme,
  onToggleTheme,
  onPause,
  onEnd,
}: {
  sessionId: string;
  domain: string;
  difficulty: string;
  initialMessages: Message[];
  theme: ThemeMode;
  onToggleTheme: () => void;
  onPause: () => Promise<void>;
  onEnd: () => Promise<void>;
}) {
  const [messages, setMessages] = useState<Message[]>(() => initialMessages);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isComposing, setIsComposing] = useState(false);
  const [codingTask, setCodingTask] = useState<CodingTask | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const refreshCodingTask = useCallback(async () => {
    try {
      const task = await fetchActiveCodingTask(sessionId);
      if (task) {
        setCodingTask(task);
      }
    } catch {
      // Keep chat usable even if the coding workspace cannot refresh.
    }
  }, [sessionId]);

  useEffect(() => {
    let ignore = false;
    fetchActiveCodingTask(sessionId)
      .then((task) => {
        if (!ignore && task) {
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
    if (!text || isStreaming) return;

    setInput('');
    let aiMsgIndex = 0;
    setMessages((prev) => {
      aiMsgIndex = prev.length + 1;
      return [...prev, { role: 'user', content: text }, { role: 'ai', content: '', streaming: true }];
    });
    setIsStreaming(true);

    const controller = streamChat(
      sessionId,
      text,
      (token) => {
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
      },
      contextMessage,
    );
    abortRef.current = controller;
  }, [isStreaming, refreshCodingTask, sessionId]);

  const handleSend = () => {
    startAgentStream(input);
  };

  const handleCodingSubmit = async (task: CodingTask, language: string, code: string) => {
    const result = await submitCodingTask(task.id, language, code);
    setCodingTask(result.task);
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
    abortRef.current?.abort();
    void onEnd();
  };

  const handlePause = () => {
    abortRef.current?.abort();
    void onPause();
  };

  const diffLabel = DIFFICULTY_OPTIONS.find((d) => d.value === difficulty)?.label || difficulty;

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
          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="chat-empty">
                <p>面试即将开始，请先自我介绍吧</p>
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
                  {msg.content}
                  {msg.streaming && <span className="cursor-blink" />}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="chat-input-bar">
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
              disabled={isStreaming}
            />
            <button
              aria-label="发送回答"
              className="send-button"
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
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

function LoadingView() {
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
          <p>如果后端暂时不可用，将自动进入登录页。</p>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [view, setView] = useState<View>(() => (hasActiveBrowserSession() ? 'loading' : 'login'));
  const [theme, setTheme] = useState<ThemeMode>(() => getInitialTheme());
  const [sessionId, setSessionId] = useState('');
  const [domain, setDomain] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [username, setUsername] = useState('');
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [historyNoticeDismissed, setHistoryNoticeDismissed] = useState(() => hasDismissedHistoryNotice());
  const [historyManageModeDefault, setHistoryManageModeDefault] = useState(false);

  useEffect(() => {
    persistTheme(theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((current) => (current === 'dark' ? 'light' : 'dark'));
  };

  useEffect(() => {
    if (!hasActiveBrowserSession()) {
      void logout().catch(() => undefined);
      return;
    }

    void getMe()
      .then((me) => {
        if (me) {
          setUsername(me.username);
          setHistoryNoticeDismissed(hasDismissedHistoryNotice());
          setView('dashboard');
        } else {
          clearActiveBrowserSession();
          setView('login');
        }
      })
      .catch(() => {
        clearActiveBrowserSession();
        setView('login');
      });
  }, []);

  const handleLogin = (user: string) => {
    markActiveBrowserSession();
    clearHistoryNoticeDismissed();
    setUsername(user);
    setHistoryNoticeDismissed(false);
    setHistoryManageModeDefault(false);
    setView('dashboard');
  };

  const handleLogout = async () => {
    clearActiveBrowserSession();
    clearHistoryNoticeDismissed();
    await logout().catch(() => undefined);
    setUsername('');
    setHistoryNoticeDismissed(false);
    setHistoryManageModeDefault(false);
    setView('login');
  };

  const handleStart = async (
    d: string,
    diff: string,
    jd: string,
    profileCompany: string,
    profilePosition: string,
    resumeId: number | null,
  ) => {
    try {
      const sid = await createSession(d, diff, jd, profileCompany, profilePosition, resumeId);
      setSessionId(sid);
      setDomain(d);
      setDifficulty(diff);
      setChatMessages([]);
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
    setView('dashboard');
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
    setView('dashboard');
    setSessionId('');
    setChatMessages([]);
  };

  const handleResume = (detail: InterviewSessionDetail) => {
    setSessionId(detail.session.id);
    setDomain(detail.session.domain);
    setDifficulty(detail.session.difficulty);
    setChatMessages(toChatMessages(detail.messages));
    setView('chat');
  };

  const goHome = () => {
    setSessionId('');
    setChatMessages([]);
    setHistoryManageModeDefault(false);
    setView('dashboard');
  };

  const openHistory = () => {
    setHistoryManageModeDefault(false);
    setView('history');
  };

  const openHistoryManagement = () => {
    markHistoryNoticeDismissed();
    setHistoryNoticeDismissed(true);
    setHistoryManageModeDefault(true);
    setView('history');
  };

  const dismissHistoryNotice = () => {
    markHistoryNoticeDismissed();
    setHistoryNoticeDismissed(true);
  };

  return (
    <>
      {view === 'loading' && <LoadingView />}
      {view === 'login' && <LoginView onLogin={handleLogin} />}
      {view === 'dashboard' && (
        <DashboardView
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          onStartInterview={() => setView('setup')}
          onProfile={() => setView('profile')}
          onHistory={openHistory}
          onManageHistory={openHistoryManagement}
          onInsights={() => setView('insights')}
          onLogout={handleLogout}
          historyNoticeDismissed={historyNoticeDismissed}
          onDismissHistoryNotice={dismissHistoryNotice}
        />
      )}
      {view === 'setup' && (
        <SetupView
          onStart={handleStart}
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          onLogout={handleLogout}
          onBack={goHome}
          onProfile={() => setView('profile')}
        />
      )}
      {view === 'chat' && (
        <ChatView
          sessionId={sessionId}
          domain={domain}
          difficulty={difficulty}
          initialMessages={chatMessages}
          theme={theme}
          onToggleTheme={toggleTheme}
          onPause={handlePause}
          onEnd={handleEnd}
        />
      )}
      {view === 'profile' && (
        <ResumeManagerView
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          onHome={goHome}
          onStartInterview={() => setView('setup')}
          onLogout={handleLogout}
        />
      )}
      {view === 'history' && (
        <HistoryView
          username={username}
          theme={theme}
          onToggleTheme={toggleTheme}
          initialManageMode={historyManageModeDefault}
          onHome={goHome}
          onStartInterview={() => setView('setup')}
          onResumeInterview={handleResume}
          onLogout={handleLogout}
        />
      )}
      {view === 'insights' && (
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
          onStartInterview={() => setView('setup')}
          onLogout={handleLogout}
        />
      )}
      <footer className="site-footer">
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
    </>
  );
}

export default App;

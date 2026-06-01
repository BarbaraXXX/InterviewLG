import { useState, useRef, useEffect, useCallback } from 'react';
import { fetchDomains, createSession, fetchProfiles, streamChat, getMe, logout, login, register } from './api';

type View = 'loading' | 'login' | 'setup' | 'chat';

interface Message {
  role: 'user' | 'ai';
  content: string;
  streaming?: boolean;
}

const AUTH_SESSION_KEY = 'interviewlg_active_session';

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

function SetupView({ onStart, username, onLogout }: {
  onStart: (domain: string, difficulty: string, jobDescription: string, profileCompany: string, profilePosition: string) => void;
  username: string;
  onLogout: () => void;
}) {
  const [domains, setDomains] = useState<string[]>(DEFAULT_DOMAINS);
  const [selectedDomain, setSelectedDomain] = useState('');
  const [customDomain, setCustomDomain] = useState('');
  const [difficulty, setDifficulty] = useState('mid');
  const [jobDescription, setJobDescription] = useState('');
  const [profiles, setProfiles] = useState<{key: string; company: string; position: string; source_count: number}[]>([]);
  const [selectedProfileIdx, setSelectedProfileIdx] = useState(-1);
  const [customCompany, setCustomCompany] = useState('');
  const [customPosition, setCustomPosition] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchDomains().then(setDomains).catch(() => {});
  }, []);

  useEffect(() => {
    fetchProfiles().then(setProfiles).catch(() => {});
  }, []);

  const activeDomain = customDomain || selectedDomain;
  const activeDomainLabel = activeDomain ? (DOMAIN_LABELS[activeDomain] || activeDomain) : '待选择';
  const activeDifficulty = DIFFICULTY_OPTIONS.find((opt) => opt.value === difficulty) || DIFFICULTY_OPTIONS[1];

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
    onStart(activeDomain, difficulty, jobDescription, profileCompany, profilePosition);
  };

  return (
    <div className="setup-view">
      <div className="console-shell">
        <header className="console-topbar">
          <div className="brand-lockup">
            <div className="logo-mark">
              <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
                <rect width="36" height="36" rx="8" fill="var(--color-accent)" />
                <path d="M10 18L16 12L22 18L16 24Z" fill="white" opacity="0.9" />
                <path d="M16 18L22 12L28 18L22 24Z" fill="white" opacity="0.6" />
              </svg>
            </div>
            <span>模拟技术面试</span>
          </div>
          <div className="user-badge">
            <span className="system-pill">已登录</span>
            <span className="user-badge-name">{username}</span>
            <button className="logout-link" onClick={onLogout}>退出</button>
          </div>
        </header>

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
              <li className={difficulty ? 'complete' : 'active'}>
                <span>02</span>
                <div>
                  <strong>面试难度</strong>
                  <small>{activeDifficulty.meta}</small>
                </div>
              </li>
              <li className={jobDescription.trim() ? 'complete' : ''}>
                <span>03</span>
                <div>
                  <strong>岗位 JD</strong>
                  <small>{jobDescription.trim() ? '已提供岗位信息' : '可选，推荐提供'}</small>
                </div>
              </li>
              <li className={selectedProfileIdx !== -1 ? 'complete' : ''}>
                <span>04</span>
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
              <div className="config-status">
                <span>{activeDomain ? 'Ready' : 'Waiting'}</span>
                <strong>{activeDomain ? '配置可启动' : '请选择技术方向'}</strong>
              </div>
            </section>

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
  onEnd,
}: {
  sessionId: string;
  domain: string;
  difficulty: string;
  onEnd: () => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: text }]);

    const aiMsgIndex = messages.length + 1;
    setMessages((prev) => [...prev, { role: 'ai', content: '', streaming: true }]);
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
      },
    );
    abortRef.current = controller;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleEnd = () => {
    abortRef.current?.abort();
    onEnd();
  };

  const diffLabel = DIFFICULTY_OPTIONS.find((d) => d.value === difficulty)?.label || difficulty;

  return (
    <div className="chat-view">
      <header className="chat-header">
        <div className="chat-header-info">
          <div className="chat-header-dot" />
          <span className="chat-header-domain">{DOMAIN_LABELS[domain] || domain}</span>
          <span className="chat-header-sep">/</span>
          <span className="chat-header-diff">{diffLabel}</span>
        </div>
        <button className="end-button" onClick={handleEnd}>
          结束面试
        </button>
      </header>

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
  const [sessionId, setSessionId] = useState('');
  const [domain, setDomain] = useState('');
  const [difficulty, setDifficulty] = useState('');
  const [username, setUsername] = useState('');

  useEffect(() => {
    if (!hasActiveBrowserSession()) {
      void logout().catch(() => undefined);
      return;
    }

    void getMe()
      .then((me) => {
        if (me) {
          setUsername(me.username);
          setView('setup');
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
    setUsername(user);
    setView('setup');
  };

  const handleLogout = async () => {
    clearActiveBrowserSession();
    await logout().catch(() => undefined);
    setUsername('');
    setView('login');
  };

  const handleStart = async (d: string, diff: string, jd: string, profileCompany: string, profilePosition: string) => {
    try {
      const sid = await createSession(d, diff, jd, profileCompany, profilePosition);
      setSessionId(sid);
      setDomain(d);
      setDifficulty(diff);
      setView('chat');
    } catch (err) {
      if (err instanceof Error && err.message === 'UNAUTHORIZED') {
        handleLogout();
      } else {
        alert('创建会话失败，请检查后端服务是否启动');
      }
    }
  };

  const handleEnd = () => {
    setView('setup');
    setSessionId('');
  };

  return (
    <>
      {view === 'loading' && <LoadingView />}
      {view === 'login' && <LoginView onLogin={handleLogin} />}
      {view === 'setup' && <SetupView onStart={handleStart} username={username} onLogout={handleLogout} />}
      {view === 'chat' && <ChatView sessionId={sessionId} domain={domain} difficulty={difficulty} onEnd={handleEnd} />}
      <footer className="site-footer">
        <a href="https://beian.miit.gov.cn" target="_blank" rel="noopener noreferrer">
          浙ICP备2026035635号
        </a>
      </footer>
    </>
  );
}

export default App;

import type { ReactNode } from 'react'

import { BrandMark } from '../../components/brand'
import { ThemeToggle } from '../../components/theme'
import styles from './LandingPage.module.css'
import { LANDING_CONTENT, resolveLandingNavigation, type LandingTheme } from './landingContent'

export interface LandingPageProps {
  isAuthenticated?: boolean
  theme?: LandingTheme
  onThemeToggle?: () => void
  appVersion?: string
}

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
      <path
        d="M4 10h11M11 6l4 4-4 4"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function FeatureIcon({ featureKey }: { featureKey: string }) {
  const common = {
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }

  if (featureKey === 'context') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" {...common}>
        <path d="M7 3.5h7l4 4v13H7z" />
        <path d="M14 3.5v4h4M9.8 12h5.4M9.8 15.5h4" />
      </svg>
    )
  }

  if (featureKey === 'strategy') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" {...common}>
        <circle cx="12" cy="12" r="8.5" />
        <circle cx="12" cy="12" r="4.5" />
        <path d="m14.8 9.2 4.7-4.7M16.2 4.5h3.3v3.3" />
      </svg>
    )
  }

  if (featureKey === 'coding') {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" {...common}>
        <path d="m8.5 7-5 5 5 5M15.5 7l5 5-5 5M13.5 4.5l-3 15" />
      </svg>
    )
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" {...common}>
      <path d="M5 5.5h14v15H5z" />
      <path d="M8 3.5v4M16 3.5v4M8.5 11h7M8.5 14.5h5" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
      <path
        d="m4.5 10.5 3.3 3.3 7.7-7.7"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function SectionHeading({
  description,
  eyebrow,
  id,
  title,
}: {
  description: string
  eyebrow: string
  id: string
  title: string
}) {
  return (
    <header className={styles.sectionHeading}>
      <p className={styles.eyebrow}>{eyebrow}</p>
      <h2 id={id}>{title}</h2>
      <p>{description}</p>
    </header>
  )
}

function InterviewPreview() {
  return (
    <figure className={styles.previewFigure} aria-labelledby="landing-preview-caption">
      <div className={styles.previewHalo} aria-hidden="true" />
      <div className={styles.previewCard}>
        <div className={styles.previewTopbar}>
          <div className={styles.previewBrand}>
            <span className={styles.previewSignal} />
            <strong>后端开发</strong>
            <span>/ 校招正式岗</span>
          </div>
          <span className={styles.previewPlan}>标准 · 10 题 · 标准型</span>
        </div>

        <div className={styles.previewProgress}>
          <div>
            <span>当前阶段</span>
            <strong>项目深挖</strong>
          </div>
          <div
            className={styles.previewProgressTrack}
            role="progressbar"
            aria-label="界面示意：已完成 3 / 10 题"
            aria-valuemin={0}
            aria-valuemax={10}
            aria-valuenow={3}
          >
            <span style={{ width: '30%' }} />
          </div>
          <strong className={styles.previewProgressCount}>3 / 10</strong>
        </div>

        <div className={styles.previewBody}>
          <aside className={styles.previewRail} aria-label="模拟面试阶段示意">
            <span className={styles.previewRailComplete}>开场</span>
            <span className={styles.previewRailActive}>项目</span>
            <span>技术</span>
            <span>编码</span>
            <span>总结</span>
          </aside>

          <div className={styles.previewConversation}>
            <article className={styles.previewMessage}>
              <div className={styles.previewAvatar} aria-hidden="true">
                <BrandMark variant="compact" size="sm" accessibleLabel="问砺" />
              </div>
              <div>
                <span>AI 面试官</span>
                <p>你提到使用 Redis 缓存热点数据。缓存击穿时，你会怎样保证数据库不被瞬时流量压垮？</p>
              </div>
            </article>

            <article className={`${styles.previewMessage} ${styles.previewMessageUser}`}>
              <div>
                <span>我的回答</span>
                <p>我会先区分热点 Key 和普通 Key，再结合互斥锁与逻辑过期来做取舍……</p>
              </div>
            </article>

            <div className={styles.previewFocus}>
              <span>本次重点</span>
              <strong>项目深挖</strong>
              <strong>系统设计</strong>
            </div>
          </div>
        </div>
      </div>
      <figcaption id="landing-preview-caption">界面示意，实际问题会根据本场配置与回答变化。</figcaption>
    </figure>
  )
}

function TierVisual({ count }: { count: number }) {
  const cells = Array.from({ length: count }, (_, index) => index)
  return (
    <div className={styles.tierVisual} aria-hidden="true">
      {cells.map((cell) => (
        <span key={cell} />
      ))}
    </div>
  )
}

function BoundaryMark({ children }: { children: ReactNode }) {
  return (
    <span className={styles.boundaryMark} aria-hidden="true">
      {children}
    </span>
  )
}

export function LandingPage({ isAuthenticated = false, theme = 'dark', onThemeToggle, appVersion }: LandingPageProps) {
  const navigation = resolveLandingNavigation(isAuthenticated)

  return (
    <div className={styles.page} data-theme={theme}>
      <a className={styles.skipLink} href="#landing-main">
        跳到主要内容
      </a>

      <header className={styles.navShell}>
        <nav className={styles.nav} aria-label="公开首页导航">
          <a className={styles.brand} href="/" aria-label="问砺首页">
            <BrandMark variant="wordmark" size="md" accessibleLabel="问砺，AI 技术面试训练" />
          </a>

          <div className={styles.navLinks}>
            {LANDING_CONTENT.navigation.map((item) => (
              <a key={item.href} href={item.href}>
                {item.label}
              </a>
            ))}
          </div>

          <div className={styles.navActions}>
            {onThemeToggle && <ThemeToggle className={styles.themeButton} onToggle={onThemeToggle} theme={theme} />}
            {!isAuthenticated && (
              <a className={styles.accountLink} href={navigation.accountHref}>
                {navigation.accountLabel}
              </a>
            )}
            <a className={styles.navCta} href={navigation.primaryHref}>
              <span>{isAuthenticated ? '进入工作台' : '开始练习'}</span>
              <ArrowIcon />
            </a>
          </div>
        </nav>
      </header>

      <main id="landing-main">
        <section className={styles.hero} aria-labelledby="landing-hero-title">
          <div className={styles.heroBackdrop} aria-hidden="true">
            <span />
            <span />
            <span />
          </div>

          <div className={styles.heroCopy}>
            <p className={styles.heroEyebrow}>
              <span aria-hidden="true" />
              {LANDING_CONTENT.hero.eyebrow}
            </p>
            <h1 id="landing-hero-title">{LANDING_CONTENT.hero.title}</h1>
            <p className={styles.heroDescription}>{LANDING_CONTENT.hero.description}</p>
            <div className={styles.heroActions}>
              <a className={styles.primaryCta} href={navigation.primaryHref}>
                <span>{navigation.primaryLabel}</span>
                <ArrowIcon />
              </a>
              <a className={styles.secondaryCta} href={LANDING_CONTENT.hero.secondaryAction.href}>
                {LANDING_CONTENT.hero.secondaryAction.label}
              </a>
            </div>
            <p className={styles.heroNote}>{LANDING_CONTENT.hero.note}</p>
          </div>

          <InterviewPreview />
        </section>

        <section className={styles.workflowSection} id="workflow" aria-labelledby="workflow-title">
          <SectionHeading
            eyebrow={LANDING_CONTENT.workflow.eyebrow}
            id="workflow-title"
            title={LANDING_CONTENT.workflow.title}
            description={LANDING_CONTENT.workflow.description}
          />
          <div className={styles.workflowGrid}>
            {LANDING_CONTENT.workflow.steps.map((step) => (
              <article className={styles.workflowCard} key={step.number}>
                <span className={styles.workflowNumber}>{step.number}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.tierSection} id="tiers" aria-labelledby="tier-title">
          <header className={styles.tierHeading}>
            <div>
              <p className={styles.eyebrow}>练习挡位</p>
              <h2 id="tier-title">不用时长衡量一场模拟</h2>
            </div>
            <p>{LANDING_CONTENT.tiersIntro}</p>
          </header>

          <div className={styles.tierGrid}>
            {LANDING_CONTENT.tiers.map((tier) => {
              const isRecommended = 'badge' in tier
              return (
                <article
                  className={`${styles.tierCard} ${isRecommended ? styles.tierRecommended : ''}`}
                  key={tier.name}
                >
                  <div className={styles.tierCardTop}>
                    <div>
                      <span>{tier.name}</span>
                      <strong>
                        {tier.questionCount}
                        <small>题</small>
                      </strong>
                    </div>
                    {isRecommended && <em>{tier.badge}</em>}
                  </div>
                  <TierVisual count={tier.questionCount} />
                  <p>{tier.description}</p>
                  <div className={styles.tierCoding} data-enabled={tier.includesCoding}>
                    <CheckIcon />
                    <span>{tier.codingLabel}</span>
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        <section className={styles.capabilitiesSection} id="capabilities" aria-labelledby="capabilities-title">
          <SectionHeading
            eyebrow="核心能力"
            id="capabilities-title"
            title="让每一个问题，都服务于这场练习"
            description="问题从你的目标出发，在明确的节奏内向深处追问，最后留下可以回看的完整过程。"
          />

          <div className={styles.capabilityGrid}>
            {LANDING_CONTENT.capabilities.map((capability, index) => (
              <article
                className={`${styles.capabilityCard} ${index === 0 || index === 3 ? styles.capabilityWide : ''}`}
                key={capability.key}
              >
                <div className={styles.capabilityIcon}>
                  <FeatureIcon featureKey={capability.key} />
                </div>
                <p className={styles.cardEyebrow}>{capability.eyebrow}</p>
                <h3>{capability.title}</h3>
                <p>{capability.description}</p>
                <span className={styles.capabilityProof}>{capability.proof}</span>
              </article>
            ))}
          </div>

          <div className={styles.boundaryPanel}>
            <header>
              <p className={styles.eyebrow}>真实边界</p>
              <h2>说清楚现在能做什么，也说清楚还不能做什么</h2>
            </header>
            <div className={styles.boundaryGrid}>
              {LANDING_CONTENT.boundaries.map((boundary, index) => (
                <article key={boundary.title}>
                  <BoundaryMark>{String(index + 1).padStart(2, '0')}</BoundaryMark>
                  <div>
                    <h3>{boundary.title}</h3>
                    <p>{boundary.description}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className={styles.privacySection} id="privacy" aria-labelledby="privacy-title">
          <div className={styles.privacyIntro}>
            <p className={styles.privacyEyebrow}>{LANDING_CONTENT.privacy.eyebrow}</p>
            <h2 id="privacy-title">{LANDING_CONTENT.privacy.title}</h2>
            <p>{LANDING_CONTENT.privacy.description}</p>
            <div className={styles.privacyVisual} aria-hidden="true">
              <div className={styles.privacyOrbit}>
                <span />
                <span />
                <span />
              </div>
              <svg viewBox="0 0 64 64" fill="none">
                <path
                  d="M32 5 53 13v16c0 14-8.5 24.5-21 30C19.5 53.5 11 43 11 29V13l21-8Z"
                  stroke="currentColor"
                  strokeWidth="2.4"
                />
                <rect x="23" y="28" width="18" height="14" rx="4" stroke="currentColor" strokeWidth="2.4" />
                <path d="M27 28v-4a5 5 0 0 1 10 0v4" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
                <circle cx="32" cy="35" r="1.8" fill="currentColor" />
              </svg>
            </div>
          </div>

          <div className={styles.privacyGrid}>
            {LANDING_CONTENT.privacy.items.map((item, index) => (
              <article key={item.title}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <h3>{item.title}</h3>
                <p>{item.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.faqSection} id="faq" aria-labelledby="faq-title">
          <header className={styles.faqHeading}>
            <p className={styles.eyebrow}>常见问题</p>
            <h2 id="faq-title">开始前，你可能还想知道</h2>
          </header>
          <div className={styles.faqList}>
            {LANDING_CONTENT.faq.map((item, index) => (
              <details key={item.question} open={index === 0}>
                <summary>
                  <span>{item.question}</span>
                  <i aria-hidden="true" />
                </summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>

        <section className={styles.closingSection} aria-labelledby="closing-title">
          <div className={styles.closingPattern} aria-hidden="true" />
          <div>
            <p className={styles.closingEyebrow}>{LANDING_CONTENT.closing.eyebrow}</p>
            <h2 id="closing-title">{LANDING_CONTENT.closing.title}</h2>
            <p>{LANDING_CONTENT.closing.description}</p>
          </div>
          <div className={styles.closingActions}>
            <a className={styles.closingCta} href={navigation.primaryHref}>
              <span>{navigation.primaryLabel}</span>
              <ArrowIcon />
            </a>
            <small>{LANDING_CONTENT.closing.note}</small>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerBrand}>
          <BrandMark variant="wordmark" size="md" accessibleLabel="问砺，AI 技术面试训练" />
        </div>
        <nav aria-label="页脚导航">
          <a href="#workflow">怎么练</a>
          <a href="#privacy">数据使用说明</a>
          {appVersion && <span>{appVersion}</span>}
        </nav>
        <div className={styles.legalLinks}>
          <a href="https://beian.miit.gov.cn" target="_blank" rel="noopener noreferrer">
            浙 ICP 备 2026035635 号
          </a>
          <a
            href="https://beian.mps.gov.cn/#/query/webSearch?code=33019202003045"
            target="_blank"
            rel="noopener noreferrer"
          >
            浙公网安备 33019202003045 号
          </a>
        </div>
      </footer>
    </div>
  )
}

export default LandingPage

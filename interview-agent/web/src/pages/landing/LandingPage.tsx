import { useRef, type ReactNode } from 'react'

import { BrandMark } from '../../components/brand'
import { ThemeToggle } from '../../components/theme'
import styles from './LandingPage.module.css'
import { LANDING_CONTENT, resolveLandingNavigation, type LandingTheme } from './landingContent'
import { useLandingReveal } from './landingMotion'

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
  chapter,
  description,
  eyebrow,
  id,
  title,
}: {
  chapter: string
  description: string
  eyebrow: string
  id: string
  title: string
}) {
  return (
    <header className={styles.sectionHeading} data-reveal>
      <div className={styles.sectionMeta}>
        <span>{chapter}</span>
        <p className={styles.eyebrow}>{eyebrow}</p>
      </div>
      <h2 id={id}>{title}</h2>
      <p>{description}</p>
    </header>
  )
}

function InterviewPreview() {
  return (
    <figure className={styles.previewFigure} aria-labelledby="landing-preview-caption">
      <div className={styles.previewCard}>
        <div className={styles.previewTopbar}>
          <div className={styles.previewBrand}>
            <span className={styles.previewSignal} />
            <strong>模拟进行中</strong>
            <span>后端开发 · 校招正式岗</span>
          </div>
          <span className={styles.previewPlan}>标准 · 10 题 · 标准型</span>
        </div>

        <div className={styles.previewJourney}>
          <svg className={styles.previewTrace} viewBox="0 0 620 390" fill="none" aria-hidden="true">
            <path className={styles.previewTraceBase} d="M72 70C190 70 162 168 292 168S390 286 548 286" />
            <path
              className={styles.previewTraceActive}
              pathLength="1"
              d="M72 70C190 70 162 168 292 168S390 286 548 286"
            />
            <circle cx="72" cy="70" r="6" />
            <circle cx="292" cy="168" r="6" />
            <circle cx="548" cy="286" r="6" />
          </svg>

          <div className={`${styles.journeyCard} ${styles.journeyQuestion}`}>
            <div className={styles.journeyCardMeta}>
              <span>01</span>
              <strong>项目事实</strong>
            </div>
            <div className={styles.previewAvatar} aria-hidden="true">
              <BrandMark variant="compact" size="sm" accessibleLabel="问砺" />
            </div>
            <div>
              <small>AI 面试官</small>
              <p>你提到使用 Redis 缓存热点数据，为什么选择这个方案？</p>
            </div>
          </div>

          <div className={`${styles.journeyCard} ${styles.journeyAnswer}`}>
            <div className={styles.journeyCardMeta}>
              <span>02</span>
              <strong>你的回答</strong>
            </div>
            <p>我会先区分热点 Key 和普通 Key，再结合互斥锁与逻辑过期做取舍……</p>
          </div>

          <div className={`${styles.journeyCard} ${styles.journeyFollowup}`}>
            <div className={styles.journeyCardMeta}>
              <span>03</span>
              <strong>继续追问</strong>
            </div>
            <p>缓存失效的瞬间，怎样保证数据库不被流量压垮？</p>
            <div className={styles.previewThinking} aria-hidden="true">
              <i />
              <i />
              <i />
              <span>沿回答继续向深处</span>
            </div>
          </div>
        </div>

        <div className={styles.previewFooter}>
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
          <div className={styles.previewFocus}>
            <span>本次重点</span>
            <strong>项目深挖</strong>
            <strong>系统设计</strong>
          </div>
        </div>
      </div>
      <figcaption id="landing-preview-caption">界面示意，实际问题会根据本场配置与回答变化。</figcaption>
    </figure>
  )
}

function TierRail() {
  return (
    <section className={styles.tierRail} id="tiers" aria-labelledby="tier-rail-title">
      <h4 className={styles.visuallyHidden} id="tier-rail-title">
        练习挡位
      </h4>
      <ul>
        {LANDING_CONTENT.tiers.map((tier) => {
          const isRecommended = 'badge' in tier
          return (
            <li className={isRecommended ? styles.tierRailRecommended : ''} key={tier.name}>
              <strong>{String(tier.questionCount).padStart(2, '0')}</strong>
              <div>
                <span>{tier.name}</span>
                {isRecommended && <em>{tier.badge}</em>}
                <p>{tier.description}</p>
              </div>
              <small data-enabled={tier.includesCoding}>
                <CheckIcon />
                {tier.codingLabel}
              </small>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function BoundaryMark({ children }: { children: ReactNode }) {
  return (
    <span className={styles.boundaryMark} aria-hidden="true">
      {children}
    </span>
  )
}

function ContextFlowVisual() {
  return (
    <div className={`${styles.storyVisual} ${styles.contextFlow}`} aria-hidden="true">
      <div className={styles.contextInputs}>
        <span>项目经历</span>
        <span>岗位 JD</span>
        <span>本轮回答</span>
      </div>
      <svg viewBox="0 0 420 210" fill="none">
        <path d="M68 42C140 42 133 105 213 105M68 105h145M68 168c72 0 65-63 145-63M213 105h128" />
        <circle cx="213" cy="105" r="6" />
      </svg>
      <div className={styles.contextOutput}>
        <small>下一次追问</small>
        <strong>这个选择解决了什么问题？</strong>
      </div>
    </div>
  )
}

function StrategyScaleVisual() {
  return (
    <div className={`${styles.storyVisual} ${styles.strategyScale}`} aria-hidden="true">
      <div className={styles.strategyLabels}>
        <span>引导型</span>
        <strong>标准型</strong>
        <span>压力型</span>
      </div>
      <div className={styles.strategyTrack}>
        <i />
        <i />
        <i />
      </div>
      <div className={styles.strategyFocus}>
        <small>最多两个训练重点</small>
        <span>项目深挖</span>
        <span>系统设计</span>
      </div>
    </div>
  )
}

function CodingStageVisual() {
  return (
    <div className={`${styles.storyVisual} ${styles.codingStage}`} aria-hidden="true">
      <div className={styles.codingTopbar}>
        <span>
          <i />
          <i />
          <i />
        </span>
        <strong>Python</strong>
        <small>草稿已保存</small>
      </div>
      <pre>
        <code>
          <span>def</span> protect_cache(key):{`\n`} lock = acquire(key){`\n`} <span>if</span> lock:{`\n`}{' '}
          <span>return</span> rebuild(key)
        </code>
      </pre>
      <div className={styles.codingActions}>
        <span>保存草稿</span>
        <strong>提交并讲解</strong>
      </div>
    </div>
  )
}

function HistoryThreadVisual() {
  return (
    <div className={`${styles.storyVisual} ${styles.historyThread}`} aria-hidden="true">
      <ol>
        <li>
          <span>Q1</span>
          <div>
            <strong>项目背景</strong>
            <small>完整问答已保存</small>
          </div>
        </li>
        <li>
          <span>Q2</span>
          <div>
            <strong>技术取舍</strong>
            <small>沿上一次回答继续</small>
          </div>
        </li>
        <li>
          <span>Code</span>
          <div>
            <strong>代码表达</strong>
            <small>草稿与提交均可回看</small>
          </div>
        </li>
      </ol>
      <p>中断的练习可以稍后继续</p>
    </div>
  )
}

function CapabilityVisual({ featureKey }: { featureKey: string }) {
  if (featureKey === 'context') return <ContextFlowVisual />
  if (featureKey === 'strategy') return <StrategyScaleVisual />
  if (featureKey === 'coding') return <CodingStageVisual />
  return <HistoryThreadVisual />
}

export function LandingPage({ isAuthenticated = false, theme = 'dark', onThemeToggle, appVersion }: LandingPageProps) {
  const navigation = resolveLandingNavigation(isAuthenticated)
  const pageRef = useRef<HTMLDivElement>(null)
  useLandingReveal(pageRef)

  return (
    <div ref={pageRef} className={styles.page} data-theme={theme}>
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
            <span />
          </div>

          <div className={styles.heroCopy}>
            <p className={styles.heroEyebrow}>
              <span aria-hidden="true" />
              {LANDING_CONTENT.hero.eyebrow}
            </p>
            <h1 id="landing-hero-title" aria-label={LANDING_CONTENT.hero.title}>
              <span>把掌握的知识，</span>
              <span>练成面试现场</span>
              <span>
                <em>能说清楚</em>的回答
              </span>
            </h1>
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

          <a className={styles.heroScrollCue} href="#workflow">
            <span>看一场练习如何展开</span>
            <i aria-hidden="true" />
          </a>
        </section>

        <section className={styles.workflowSection} id="workflow" aria-labelledby="workflow-title">
          <div className={styles.workflowChapter}>
            <SectionHeading
              chapter="01"
              eyebrow={LANDING_CONTENT.workflow.eyebrow}
              id="workflow-title"
              title={LANDING_CONTENT.workflow.title}
              description={LANDING_CONTENT.workflow.description}
            />
            <aside className={styles.workflowStatement} data-reveal>
              <span>练习边界</span>
              <strong>给思考留出空间，给追问划清边界。</strong>
              <p>用问题数推进，而不是用倒计时衡量表现。</p>
            </aside>
          </div>
          <ol className={styles.journeyTimeline}>
            {LANDING_CONTENT.workflow.steps.map((step, index) => (
              <li key={step.number} data-reveal data-reveal-index={index}>
                <span className={styles.journeyNumber}>{step.number}</span>
                <div className={styles.journeyCopy}>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                  {index === 2 && <TierRail />}
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className={styles.capabilitiesSection} id="capabilities" aria-labelledby="capabilities-title">
          <SectionHeading
            chapter="02"
            eyebrow="核心能力"
            id="capabilities-title"
            title="问题如何变成一次真实练习"
            description="从目标上下文到连续追问、代码表达与完整回看，每一段都有不同的作用。"
          />

          <div className={styles.storyActs}>
            {LANDING_CONTENT.capabilities.map((capability, index) => {
              const scopeBoundary =
                capability.key === 'coding'
                  ? LANDING_CONTENT.boundaries[0]
                  : capability.key === 'history'
                    ? LANDING_CONTENT.boundaries[1]
                    : null
              return (
                <article
                  className={`${styles.storyAct} ${index % 2 === 1 ? styles.storyActReverse : ''}`}
                  key={capability.key}
                  data-reveal
                >
                  <div className={styles.storyCopy}>
                    <div className={styles.storyIcon}>
                      <FeatureIcon featureKey={capability.key} />
                    </div>
                    <p className={styles.cardEyebrow}>{capability.eyebrow}</p>
                    <h3>{capability.title}</h3>
                    <p>{capability.description}</p>
                    <span className={styles.storyProof}>{capability.proof}</span>
                    {scopeBoundary && (
                      <aside className={styles.scopeNote}>
                        <BoundaryMark>边界</BoundaryMark>
                        <div>
                          <strong>{scopeBoundary.title}</strong>
                          <p>{scopeBoundary.description}</p>
                        </div>
                      </aside>
                    )}
                  </div>
                  <CapabilityVisual featureKey={capability.key} />
                </article>
              )
            })}
          </div>

          <aside className={styles.aiDisclaimer} data-reveal>
            <BoundaryMark>AI</BoundaryMark>
            <div>
              <strong>{LANDING_CONTENT.boundaries[2].title}</strong>
              <p>{LANDING_CONTENT.boundaries[2].description}</p>
            </div>
          </aside>
        </section>

        <section className={styles.privacySection} id="privacy" aria-labelledby="privacy-title">
          <div className={styles.privacyIntro} data-reveal>
            <div className={styles.sectionMeta}>
              <span>03</span>
              <p className={styles.privacyEyebrow}>{LANDING_CONTENT.privacy.eyebrow}</p>
            </div>
            <h2 id="privacy-title">{LANDING_CONTENT.privacy.title}</h2>
            <p>{LANDING_CONTENT.privacy.description}</p>
            <svg className={styles.privacyShield} viewBox="0 0 64 64" fill="none" aria-hidden="true">
              <path d="M32 5 53 13v16c0 14-8.5 24.5-21 30C19.5 53.5 11 43 11 29V13l21-8Z" />
              <path d="M23 32h18M27 32v-7a5 5 0 0 1 10 0v7M32 39v4" />
            </svg>
          </div>

          <dl className={styles.privacyList}>
            {LANDING_CONTENT.privacy.items.map((item, index) => (
              <div key={item.title} data-reveal data-reveal-index={index}>
                <dt>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <strong>{item.title}</strong>
                </dt>
                <dd>{item.description}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className={styles.faqSection} id="faq" aria-labelledby="faq-title">
          <header className={styles.faqHeading} data-reveal>
            <div className={styles.sectionMeta}>
              <span>04</span>
              <p className={styles.eyebrow}>常见问题</p>
            </div>
            <h2 id="faq-title">开始前，你可能还想知道</h2>
          </header>
          <div className={styles.faqList}>
            {LANDING_CONTENT.faq.map((item, index) => (
              <details key={item.question} open={index === 0} data-reveal data-reveal-index={index}>
                <summary>
                  <span>{item.question}</span>
                  <i aria-hidden="true" />
                </summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>

        <section className={styles.closingSection} aria-labelledby="closing-title" data-reveal>
          <svg className={styles.closingTrace} viewBox="0 0 520 220" fill="none" aria-hidden="true">
            <path d="M18 172C128 172 92 48 228 48s104 124 274 124" />
            <circle cx="18" cy="172" r="5" />
            <circle cx="228" cy="48" r="5" />
            <circle cx="502" cy="172" r="5" />
          </svg>
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

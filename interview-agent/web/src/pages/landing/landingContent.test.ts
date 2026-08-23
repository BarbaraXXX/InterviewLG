import assert from 'node:assert/strict'
import test from 'node:test'

import { LANDING_CONTENT, resolveLandingNavigation } from './landingContent.ts'

test('uses the approved brand and narrative hero copy', () => {
  assert.equal(LANDING_CONTENT.brand.name, '问砺')
  assert.equal(LANDING_CONTENT.brand.tagline, 'AI 技术面试训练')
  assert.equal(LANDING_CONTENT.hero.title, '把掌握的知识，练成面试现场能说清楚的回答')
  assert.equal(
    LANDING_CONTENT.hero.description,
    '问砺通过连续对话模拟技术面试中的思考与表达过程。它会沿着你的项目经历、技术选择和每一次回答继续追问，让练习不止停留在“知道”，而是逐渐形成能够讲清原理、说明取舍、应对深入追问的表达能力。',
  )
  assert.doesNotMatch(LANDING_CONTENT.hero.description, /用户|好评|通过率|精准评分/)
})

test('describes question tiers as a count budget with honest coding availability', () => {
  assert.deepEqual(
    LANDING_CONTENT.tiers.map(({ questionCount, includesCoding }) => ({ questionCount, includesCoding })),
    [
      { questionCount: 6, includesCoding: false },
      { questionCount: 10, includesCoding: true },
      { questionCount: 15, includesCoding: true },
    ],
  )
  assert.match(LANDING_CONTENT.tiersIntro, /问题数/)
  assert.match(LANDING_CONTENT.tiersIntro, /暂停和思考不会消耗题量/)
})

test('keeps current product boundaries explicit', () => {
  const boundaryText = LANDING_CONTENT.boundaries.map((item) => item.description).join('\n')

  assert.match(boundaryText, /不提供在线编译或测试结果/)
  assert.match(boundaryText, /尚未上线正式的证据化能力报告/)
  assert.match(boundaryText, /不代表招聘方评价或录用结论/)
})

test('explains optional context and third-party model processing', () => {
  const privacyText = LANDING_CONTENT.privacy.items.map((item) => item.description).join('\n')

  assert.match(LANDING_CONTENT.privacy.description, /简历和 JD 都是可选项/)
  assert.match(privacyText, /模型服务/)
  assert.match(privacyText, /删除/)
  assert.match(privacyText, /点击发送/)
})

test('resolves public and authenticated navigation without invented destinations', () => {
  assert.deepEqual(resolveLandingNavigation(false), {
    accountLabel: '登录',
    accountHref: '/login',
    primaryLabel: '开始模拟面试',
    primaryHref: '/login?next=%2Fsetup',
  })
  assert.deepEqual(resolveLandingNavigation(true), {
    accountLabel: '进入工作台',
    accountHref: '/dashboard',
    primaryLabel: '进入工作台',
    primaryHref: '/dashboard',
  })
})

test('keeps the landing story in the agreed section order', () => {
  assert.deepEqual(
    LANDING_CONTENT.sections.map((section) => section.id),
    ['workflow', 'tiers', 'capabilities', 'privacy', 'faq'],
  )
  assert.equal(LANDING_CONTENT.faq.length, 4)
})

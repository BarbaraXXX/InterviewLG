export type LandingTheme = 'light' | 'dark'

export interface LandingNavigation {
  accountLabel: string
  accountHref: '/login' | '/dashboard'
  primaryLabel: string
  primaryHref: '/login?next=%2Fsetup' | '/dashboard'
}

export function resolveLandingNavigation(isAuthenticated: boolean): LandingNavigation {
  if (isAuthenticated) {
    return {
      accountLabel: '进入工作台',
      accountHref: '/dashboard',
      primaryLabel: '进入工作台',
      primaryHref: '/dashboard',
    }
  }

  return {
    accountLabel: '登录',
    accountHref: '/login',
    primaryLabel: '开始模拟面试',
    primaryHref: '/login?next=%2Fsetup',
  }
}

export const LANDING_CONTENT = {
  brand: {
    name: '问砺',
    tagline: 'AI 技术面试训练',
  },
  navigation: [
    { label: '怎么练', href: '#workflow' },
    { label: '练习挡位', href: '#tiers' },
    { label: '核心能力', href: '#capabilities' },
    { label: '数据与隐私', href: '#privacy' },
  ],
  hero: {
    eyebrow: '面向校招技术岗位 · 邀请制内测',
    title: '把掌握的知识，练成面试现场能说清楚的回答',
    description:
      '问砺通过连续对话模拟技术面试中的思考与表达过程。它会沿着你的项目经历、技术选择和每一次回答继续追问，让练习不止停留在“知道”，而是逐渐形成能够讲清原理、说明取舍、应对深入追问的表达能力。',
    secondaryAction: {
      label: '看看怎么练',
      href: '#workflow',
    },
    note: '已有账号可直接登录，新用户需要邀请码。',
  },
  sections: [
    { id: 'workflow', label: '怎么练' },
    { id: 'tiers', label: '练习挡位' },
    { id: 'capabilities', label: '核心能力' },
    { id: 'privacy', label: '数据与隐私' },
    { id: 'faq', label: '常见问题' },
  ],
  workflow: {
    eyebrow: '怎么练',
    title: '从目标配置，到一场有边界的模拟',
    description: '这里不靠倒计时催促你。每场练习按问题数推进，暂停和思考不会消耗题量。',
    steps: [
      {
        number: '01',
        title: '选择目标',
        description: '选择后端、前端、算法等预设方向，或填写自定义方向，再确认校招实习或正式岗目标。',
      },
      {
        number: '02',
        title: '补充上下文',
        description: '按需选择纯文本简历、粘贴岗位 JD，或选择已有面试偏好；这些信息都可以跳过。',
      },
      {
        number: '03',
        title: '决定练习节奏',
        description: '在精简 6 题、标准 10 题、深入 15 题中选择一档，再设置引导、标准或压力型追问。',
      },
      {
        number: '04',
        title: '对话、编码与回看',
        description: 'AI 面试官逐题追问。标准与深入档会进入手撕代码；结束后可回看完整问答与提交内容。',
      },
    ],
  },
  tiersIntro: '用问题数控制练习边界，而不是用时长衡量表现。暂停和思考不会消耗题量。',
  tiers: [
    {
      name: '精简',
      questionCount: 6,
      includesCoding: false,
      codingLabel: '不含手撕代码',
      description: '适合快速热身，聚焦项目与核心技术问题。',
    },
    {
      name: '标准',
      questionCount: 10,
      includesCoding: true,
      codingLabel: '包含手撕代码',
      description: '覆盖项目、技术与编码，适合日常完整练习。',
      badge: '首次使用建议',
    },
    {
      name: '深入',
      questionCount: 15,
      includesCoding: true,
      codingLabel: '包含手撕代码',
      description: '留出更多追问空间，检验项目理解和知识深度。',
    },
  ],
  capabilities: [
    {
      key: 'context',
      eyebrow: '目标上下文',
      title: '围绕你的项目和投递目标追问',
      description:
        '简历和 JD 都是可选项。提供后，系统会把项目经历、技术栈和岗位要求加入本场上下文；题库存在足够相关的内容时，再作为问题参考。',
      proof: '不使用简历或 JD 也可以开始。',
    },
    {
      key: 'strategy',
      eyebrow: '追问策略',
      title: '强度和重点，由你在开始前确定',
      description:
        '引导型会在卡顿时提供适度线索；标准型平衡深度和沟通体验；压力型减少提示。还可以从项目深挖、技术基础、系统设计、编码能力和表达思路中最多选择两个重点。',
      proof: '未选择重点时，会按岗位做综合覆盖。',
    },
    {
      key: 'coding',
      eyebrow: '代码表达',
      title: '从技术问答进入手撕，不跳出面试语境',
      description:
        '标准和深入档包含代码题，支持 Python、Java、C++、JavaScript、TypeScript 等语言，可保存草稿、提交代码并继续讲解思路。',
      proof: '当前重点是书写、提交与讨论。',
    },
    {
      key: 'history',
      eyebrow: '练习轨迹',
      title: '练完不是消失，而是留下可回看的对话',
      description: '历史记录保留本场配置、完整问答、代码草稿与提交内容；中断的面试可以稍后继续。',
      proof: '当前版本聚焦过程回看，不伪装成精确评分。',
    },
  ],
  boundaries: [
    {
      title: '代码环节的边界',
      description: '当前不提供在线编译或测试结果，代码提交用于后续讲解和追问。',
    },
    {
      title: '回看不等于证书',
      description: '当前可回看完整问答和代码记录，尚未上线正式的证据化能力报告。',
    },
    {
      title: 'AI 是练习搭档',
      description: 'AI 生成内容可能存在遗漏或错误，不代表招聘方评价或录用结论。',
    },
  ],
  privacy: {
    eyebrow: '数据与隐私',
    title: '你决定提供多少上下文',
    description:
      '简历和 JD 都是可选项。简历只需录入与面试相关的项目经验和技能；请不要填写手机号、邮箱、证件号、住址、账号密码、薪资等敏感信息。',
    items: [
      {
        title: '内容可选',
        description: '不填写简历、JD 或面试偏好，也可以开始一场通用练习。',
      },
      {
        title: '记录可管理',
        description: '你可以删除已保存简历和面试记录；删除简历不会自动改写先前创建的历史会话。',
      },
      {
        title: '语音先确认',
        description: '语音会先转换为可编辑文本，只有你点击发送后才会进入面试对话。',
      },
      {
        title: '模型处理提示',
        description: '问题生成、JD 处理和语音转写会调用部署方配置的模型服务，请勿提交敏感个人信息。',
      },
    ],
  },
  faq: [
    {
      question: '面试按多长时间结束？',
      answer: '不按时间计。每场以 6、10 或 15 个有效问题作为练习边界，思考和暂停不计题数。',
    },
    {
      question: '必须上传完整简历吗？',
      answer: '不需要。当前只支持主动填写纯文本项目经验和技能，也可以完全不使用简历。',
    },
    {
      question: '精简档包含手撕代码吗？',
      answer: '不包含。标准和深入档固定包含代码环节。',
    },
    {
      question: '现在会给出正式能力评分吗？',
      answer: '当前版本提供完整问答和代码记录回看，正式的证据化能力报告尚未上线。',
    },
  ],
  closing: {
    eyebrow: '开始一场练习',
    title: '从选择一个技术方向开始',
    description: '简历和 JD 都可以稍后补充。首次使用建议选择“标准 10 题 + 标准型”，体验项目、技术和代码环节。',
    note: '当前为邀请制内测，新用户注册需要邀请码。',
  },
} as const

export interface ReleaseNote {
  date: string;
  title: string;
  items: string[];
}

export const RELEASE_NOTES: ReleaseNote[] = [
  {
    date: '2026-06-04',
    title: '历史面试记录回看',
    items: [
      '新增历史面试列表，登录后可查看自己的过往面试。',
      '支持点击单次记录查看完整 QA 内容。',
      '结束面试后会保留历史记录，方便后续复盘。',
    ],
  },
  {
    date: '2026-06-03',
    title: '工作台与功能入口',
    items: [
      '登录后进入统一工作台，不再直接跳转面试配置。',
      '预留个人信息、历史记录和 AI 表现总结入口。',
      '优化面试配置页返回工作台的流程。',
    ],
  },
  {
    date: '2026-06-02',
    title: '真实面试题 RAG 接入',
    items: [
      '接入真实面试 QA 题库检索。',
      'Agent 会参考相近问题生成更贴近真实场景的追问。',
      '优化向量数据库导入和检索流程。',
    ],
  },
];

import 'katex/dist/katex.min.css';

import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';

function normalizeMarkdownText(content: string): string {
  return content
    .replace(/\\\[([\s\S]+?)\\\]/g, (_match, body: string) => `$$\n${body.trim()}\n$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_match, body: string) => `$${body.trim()}$`)
    .replace(/\\([`*_{}[\]()#+\-.!>|])/g, '$1')
    .replace(/(^|[^\n])```([A-Za-z0-9+#-]*)\s+([^`\n]+?)```/g, (_match, prefix: string, language: string, body: string) => {
      const label = language ? `${language} ` : '';
      return `${prefix}\`${label}${body.trim()}\``;
    });
}

export default function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="markdown-content">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {normalizeMarkdownText(content)}
      </ReactMarkdown>
    </div>
  );
}

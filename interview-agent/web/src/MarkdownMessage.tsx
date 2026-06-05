import ReactMarkdown from 'react-markdown';
import remarkBreaks from 'remark-breaks';

function normalizeMarkdownText(content: string): string {
  return content
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
        remarkPlugins={[remarkBreaks]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
        }}
      >
        {normalizeMarkdownText(content)}
      </ReactMarkdown>
    </div>
  );
}

import { useState } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { cpp } from '@codemirror/lang-cpp';
import { java } from '@codemirror/lang-java';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';
import { oneDark } from '@codemirror/theme-one-dark';

import { CODING_LANGUAGE_LABELS, CODING_LANGUAGE_OPTIONS } from './codingLanguages';
import type { CodingTask } from './api';

type ThemeMode = 'light' | 'dark';

function codingLanguageExtensions(language: string) {
  if (language === 'python') return [python()];
  if (language === 'javascript') return [javascript()];
  if (language === 'typescript') return [javascript({ typescript: true })];
  if (language === 'java') return [java()];
  if (language === 'cpp') return [cpp()];
  return [];
}

export default function CodingWorkspace({
  task,
  theme,
  onSubmit,
}: {
  task: CodingTask;
  theme: ThemeMode;
  onSubmit: (task: CodingTask, language: string, code: string) => Promise<void>;
}) {
  const [language, setLanguage] = useState(task.submitted_language || task.language || 'python');
  const [code, setCode] = useState(task.submitted_code || task.starter_code || '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const isSubmitted = task.status === 'submitted';

  const handleSubmitCode = async () => {
    if (!code.trim() || submitting || isSubmitted) return;
    setSubmitting(true);
    setError('');
    try {
      await onSubmit(task, language, code);
    } catch (err) {
      setError(err instanceof Error ? err.message : '提交失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <aside className="coding-workspace" aria-label="手撕代码题">
      <div className="coding-task-head">
        <div>
          <p className="eyebrow">Coding Task</p>
          <h2>{task.title}</h2>
        </div>
        <span className={`coding-status ${isSubmitted ? 'submitted' : 'active'}`}>
          {isSubmitted ? '已提交' : '进行中'}
        </span>
      </div>

      <div className="coding-task-body">
        <section className="coding-problem">
          <h3>题目描述</h3>
          <p>{task.description}</p>
          {task.constraints.length > 0 && (
            <div>
              <h3>约束</h3>
              <ul>
                {task.constraints.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {task.examples.length > 0 && (
            <div>
              <h3>示例</h3>
              <div className="coding-examples">
                {task.examples.map((example, index) => (
                  <div className="coding-example" key={`${example.input}-${index}`}>
                    <strong>示例 {index + 1}</strong>
                    {example.input && <p>输入：{example.input}</p>}
                    {example.output && <p>输出：{example.output}</p>}
                    {example.explanation && <p>说明：{example.explanation}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>

        <section className="coding-editor-panel">
          <div className="coding-editor-toolbar">
            <label>
              <span>语言</span>
              <select
                className="custom-input profile-select"
                value={language}
                disabled={isSubmitted}
                onChange={(e) => setLanguage(e.target.value)}
              >
                {CODING_LANGUAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <button
              className="secondary-button"
              onClick={() => setCode(task.starter_code || '')}
              disabled={isSubmitted || submitting}
            >
              重置模板
            </button>
          </div>
          <CodeMirror
            value={code}
            height="360px"
            theme={theme === 'dark' ? oneDark : 'light'}
            extensions={codingLanguageExtensions(language)}
            editable={!isSubmitted}
            basicSetup={{
              lineNumbers: true,
              foldGutter: false,
              highlightActiveLine: true,
              autocompletion: false,
            }}
            onChange={(value) => setCode(value)}
          />
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="coding-submit-row">
            <span>{isSubmitted ? `提交语言：${CODING_LANGUAGE_LABELS[language] || language}` : '真实面试模式：不提供运行验证'}</span>
            <button
              className="inline-start-button"
              onClick={() => void handleSubmitCode()}
              disabled={isSubmitted || submitting || !code.trim()}
            >
              {isSubmitted ? '已提交' : submitting ? '提交中...' : '提交代码'}
            </button>
          </div>
        </section>
      </div>
    </aside>
  );
}

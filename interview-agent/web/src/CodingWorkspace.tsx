import { useCallback, useEffect, useMemo, useState } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { cpp } from '@codemirror/lang-cpp';
import { java } from '@codemirror/lang-java';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';
import { oneDark } from '@codemirror/theme-one-dark';

import { CODING_LANGUAGE_LABELS, CODING_LANGUAGE_OPTIONS } from './codingLanguages';
import MarkdownMessage from './MarkdownMessage';
import { saveCodingTaskDraft, type CodingTask } from './api';

type ThemeMode = 'light' | 'dark';

const DRAFT_AUTOSAVE_DELAY_MS = 30000;

function codingLanguageExtensions(language: string) {
  if (language === 'python') return [python()];
  if (language === 'javascript') return [javascript()];
  if (language === 'typescript') return [javascript({ typescript: true })];
  if (language === 'java') return [java()];
  if (language === 'cpp') return [cpp()];
  return [];
}

function starterCodeForLanguage(task: CodingTask, language: string): string {
  const starterCodeMap = task.starter_code_map || {};
  if (starterCodeMap[language]) return starterCodeMap[language];
  if (Object.keys(starterCodeMap).length === 0) return task.starter_code || '';
  return language === task.language ? task.starter_code || '' : '';
}

function isStarterTemplate(task: CodingTask, code: string): boolean {
  if (!code.trim()) return true;
  const templates = new Set(Object.values(task.starter_code_map || {}).filter(Boolean));
  if (task.starter_code) templates.add(task.starter_code);
  return templates.has(code);
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
  const isSubmitted = task.status === 'submitted';
  const isRevision = !isSubmitted && task.revision_count > 0;
  const initialLanguage = isSubmitted
    ? task.submitted_language || task.draft_language || task.language || 'python'
    : task.draft_language || task.submitted_language || task.language || 'python';
  const initialCode = isSubmitted
    ? task.submitted_code || task.draft_code || starterCodeForLanguage(task, initialLanguage)
    : task.draft_code || task.submitted_code || starterCodeForLanguage(task, initialLanguage);
  const [language, setLanguage] = useState(initialLanguage);
  const [code, setCode] = useState(initialCode);
  const [submitting, setSubmitting] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [draftStatus, setDraftStatus] = useState(task.draft_code ? '已恢复草稿' : '');
  const [error, setError] = useState('');
  const [savedDraftKey, setSavedDraftKey] = useState(`${initialLanguage}\n${initialCode}`);
  const draftKey = useMemo(() => `${language}\n${code}`, [code, language]);

  const handleLanguageChange = (nextLanguage: string) => {
    const shouldReplaceTemplate = isStarterTemplate(task, code);
    setLanguage(nextLanguage);
    if (shouldReplaceTemplate) {
      setCode(starterCodeForLanguage(task, nextLanguage));
    }
  };

  const saveDraft = useCallback(async (silent = false) => {
    if (isSubmitted || savingDraft || draftKey === savedDraftKey) return;
    setSavingDraft(true);
    if (!silent) setDraftStatus('');
    setError('');
    try {
      const saved = await saveCodingTaskDraft(task.id, language, code);
      setSavedDraftKey(`${saved.draft_language || language}\n${saved.draft_code || ''}`);
      setDraftStatus(silent ? '草稿已自动保存' : '草稿已保存');
    } catch (err) {
      if (!silent) {
        setError(err instanceof Error ? err.message : '保存草稿失败，请稍后重试');
      }
    } finally {
      setSavingDraft(false);
    }
  }, [code, draftKey, isSubmitted, language, savedDraftKey, savingDraft, task.id]);

  useEffect(() => {
    if (isSubmitted || draftKey === savedDraftKey) return undefined;
    const timer = window.setTimeout(() => {
      void saveDraft(true);
    }, DRAFT_AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [draftKey, isSubmitted, saveDraft, savedDraftKey]);

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
          {isSubmitted ? '已提交' : isRevision ? '修订中' : '进行中'}
        </span>
      </div>

      <div className="coding-task-body">
        <section className="coding-problem">
          <h3>题目描述</h3>
          <MarkdownMessage content={task.description} />
          {isRevision && task.revision_instruction && (
            <div className="coding-revision-note">
              <strong>修订要求</strong>
              <MarkdownMessage content={task.revision_instruction} />
            </div>
          )}
          {task.constraints.length > 0 && (
            <div>
              <h3>约束</h3>
              <ul>
                {task.constraints.map((item) => (
                  <li key={item}><MarkdownMessage content={item} /></li>
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
                    {example.input && <MarkdownMessage content={`输入：${example.input}`} />}
                    {example.output && <MarkdownMessage content={`输出：${example.output}`} />}
                    {example.explanation && <MarkdownMessage content={`说明：${example.explanation}`} />}
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
                onChange={(e) => handleLanguageChange(e.target.value)}
              >
                {CODING_LANGUAGE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <button
              className="secondary-button"
              onClick={() => setCode(starterCodeForLanguage(task, language))}
              disabled={isSubmitted || submitting || savingDraft}
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
            <span>
              {isSubmitted
                ? `提交语言：${CODING_LANGUAGE_LABELS[language] || language}`
                : draftStatus || '真实面试模式：不提供运行验证'}
            </span>
            <div className="coding-submit-actions">
              <button
                className="secondary-button"
                onClick={() => void saveDraft(false)}
                disabled={isSubmitted || submitting || savingDraft || draftKey === savedDraftKey}
              >
                {savingDraft ? '保存中' : '保存草稿'}
              </button>
              <button
                className="inline-start-button"
                onClick={() => void handleSubmitCode()}
                disabled={isSubmitted || submitting || !code.trim()}
              >
                {isSubmitted ? '已提交' : submitting ? '提交中...' : '提交代码'}
              </button>
            </div>
          </div>
        </section>
      </div>
    </aside>
  );
}

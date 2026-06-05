export const CODING_LANGUAGE_OPTIONS = [
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'typescript', label: 'TypeScript' },
  { value: 'java', label: 'Java' },
  { value: 'cpp', label: 'C++' },
  { value: 'go', label: 'Go' },
];

export const CODING_LANGUAGE_LABELS = Object.fromEntries(
  CODING_LANGUAGE_OPTIONS.map((item) => [item.value, item.label]),
);

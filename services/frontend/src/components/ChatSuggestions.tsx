import React, { useEffect, useId, useRef, useState } from 'react';
import { ArrowUpRight, ChevronDown, ChevronUp } from 'lucide-react';
import {
  PORTFOLIO_GROUPS, PORTFOLIO_QUESTIONS, QUESTION_TABS, STARTER_QUESTIONS, TOPIC_QUESTIONS,
  type ChatQuestion, type PortfolioGroupId, type QuestionTabId,
} from '../chatQuestions';

interface QuestionProps {
  disabled: boolean;
  onSelect: (prompt: string) => void;
}

const focusStyle = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 focus-visible:ring-inset';

export function ChatStarters({ disabled, onSelect }: QuestionProps) {
  return (
    <div className="ml-0 sm:ml-[52px]">
      <p className="mb-2 text-xs text-slate-400">Start with a question</p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {STARTER_QUESTIONS.map((question) => (
          <button
            key={question.id}
            type="button"
            onClick={() => onSelect(question.prompt)}
            disabled={disabled}
            title={question.prompt}
            className={`flex min-h-11 items-center justify-between gap-2 rounded-xl border border-slate-600/70 bg-slate-800/60 px-3 py-2.5 text-left text-xs font-medium text-slate-200 transition-colors hover:border-indigo-400/60 hover:bg-slate-700/70 disabled:cursor-not-allowed disabled:opacity-50 ${focusStyle}`}
          >
            {question.label}
            <ArrowUpRight size={14} className="shrink-0 text-indigo-300" aria-hidden="true" />
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ChatSuggestions({ disabled, onSelect }: QuestionProps) {
  const [activeTab, setActiveTab] = useState<QuestionTabId>('overview');
  const [portfolioGroup, setPortfolioGroup] = useState<PortfolioGroupId>('personal');
  const [isExpanded, setIsExpanded] = useState(false);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelScrollRef = useRef<HTMLDivElement>(null);
  const id = useId();
  const panelId = `${id}-questions`;
  const activeTopic = QUESTION_TABS.find((tab) => tab.id === activeTab)!;
  const questions: ChatQuestion[] = activeTab === 'portfolio'
    ? PORTFOLIO_QUESTIONS[portfolioGroup] : TOPIC_QUESTIONS[activeTab];

  useEffect(() => {
    if (disabled) setIsExpanded(false);
  }, [disabled]);

  useEffect(() => {
    if (panelScrollRef.current) panelScrollRef.current.scrollTop = 0;
  }, [activeTab, portfolioGroup, isExpanded]);

  const selectQuestion = (question: ChatQuestion) => {
    setIsExpanded(false);
    toggleRef.current?.focus();
    onSelect(question.prompt);
  };

  const handleTabKey = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    let nextIndex: number;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % QUESTION_TABS.length;
    else if (event.key === 'ArrowLeft') nextIndex = (index + QUESTION_TABS.length - 1) % QUESTION_TABS.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = QUESTION_TABS.length - 1;
    else return;
    event.preventDefault();
    setActiveTab(QUESTION_TABS[nextIndex].id);
    setIsExpanded(true);
    tabRefs.current[nextIndex]?.focus();
    tabRefs.current[nextIndex]?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  };

  return (
    <div className="shrink-0 border-t border-slate-700 bg-slate-800/70 px-3 py-2 sm:px-4">
      <div className="flex items-center gap-1">
        <div role="tablist" aria-label="Question topics" className="flex min-w-0 flex-1 gap-1 overflow-x-auto py-1">
          {QUESTION_TABS.map((tab, index) => (
            <button
              key={tab.id}
              ref={(element) => { tabRefs.current[index] = element; }}
              type="button"
              role="tab"
              id={`${id}-${tab.id}`}
              aria-controls={panelId}
              aria-selected={activeTab === tab.id}
              tabIndex={activeTab === tab.id ? 0 : -1}
              onKeyDown={(event) => handleTabKey(event, index)}
              onClick={() => { setActiveTab(tab.id); setIsExpanded(true); }}
              className={`min-h-9 shrink-0 rounded-lg px-3 py-2 text-xs font-medium transition-colors ${focusStyle} ${activeTab === tab.id ? 'bg-slate-700 text-indigo-200' : 'text-slate-400 hover:bg-slate-700/50 hover:text-slate-100'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button
          ref={toggleRef}
          type="button"
          aria-label={isExpanded ? 'Hide suggested questions' : 'Show suggested questions'}
          aria-expanded={isExpanded}
          aria-controls={panelId}
          onClick={() => setIsExpanded((expanded) => !expanded)}
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-700 hover:text-slate-100 ${focusStyle}`}
        >
          {isExpanded ? <ChevronDown size={17} aria-hidden="true" /> : <ChevronUp size={17} aria-hidden="true" />}
        </button>
      </div>
      <div id={panelId} role="tabpanel" aria-labelledby={`${id}-${activeTab}`} hidden={!isExpanded}>
        <p className="px-1 pb-2 pt-1 text-xs text-slate-400">{activeTopic.description}</p>
        {activeTab === 'portfolio' && (
          <div role="group" aria-label="Portfolio categories" className="mb-2 flex flex-wrap gap-1.5">
            {PORTFOLIO_GROUPS.map((group) => (
              <button
                key={group.id}
                type="button"
                aria-pressed={portfolioGroup === group.id}
                onClick={() => setPortfolioGroup(group.id)}
                className={`min-h-9 rounded-full border px-3 py-1.5 text-xs ${focusStyle} ${portfolioGroup === group.id ? 'border-indigo-400/60 bg-indigo-500/10 text-indigo-200' : 'border-slate-600 text-slate-400 hover:text-slate-200'}`}
              >
                {group.label}
              </button>
            ))}
          </div>
        )}
        <div ref={panelScrollRef} className="max-h-[min(240px,28dvh)] overflow-y-auto overscroll-contain pb-1">
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {questions.length === 0 && <p className="px-1 py-2 text-xs text-slate-400">No items have been added to this topic yet.</p>}
            {questions.map((question) => (
              <button
                key={question.id}
                type="button"
                disabled={disabled}
                onClick={() => selectQuestion(question)}
                className={`group rounded-lg border border-slate-700 bg-slate-900/30 px-3 py-2.5 text-left transition-colors hover:border-slate-500 hover:bg-slate-700/50 disabled:cursor-not-allowed disabled:opacity-50 ${focusStyle}`}
              >
                <span className="flex items-center justify-between gap-2 text-xs font-medium text-slate-200">
                  {question.label}
                  <ArrowUpRight size={13} className="shrink-0 text-slate-500 group-hover:text-indigo-300" aria-hidden="true" />
                </span>
                <span className="mt-1 block text-xs leading-relaxed text-slate-400">{question.prompt}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

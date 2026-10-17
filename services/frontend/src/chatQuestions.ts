import { RESUME_DATA } from './constants';
export interface ChatQuestion { id: string; label: string; prompt: string }
export const STARTER_QUESTIONS: ChatQuestion[] = [
  { id: 'intro', label: 'A quick introduction', prompt: 'Give me a brief introduction to your background and current work.' },
  { id: 'experience', label: 'Your experience', prompt: 'Which experiences best represent your work, and what did you personally contribute?' },
  { id: 'projects', label: 'Explore your projects', prompt: 'Give me an overview of your documented projects and the problems they address.' },
];
export const QUESTION_TABS = [
  { id: 'overview', label: 'Overview', description: 'Background and interests' },
  { id: 'experience', label: 'Experience', description: 'Roles and personal contributions' },
  { id: 'work', label: 'Work Projects', description: 'Project decisions, implementation and scope' },
  { id: 'skills', label: 'Skills', description: 'Tools and practical examples' },
  { id: 'portfolio', label: 'Portfolio', description: 'Personal projects and learning' },
] as const;
export type QuestionTabId = typeof QUESTION_TABS[number]['id'];
const projectQuestions = (projects: typeof RESUME_DATA.projects): ChatQuestion[] => projects.map(project => ({
  id: project.id, label: project.title,
  prompt: `Tell me about ${project.title}. What problem did it address, what did you personally implement, and what limitations are documented?`,
}));
export const TOPIC_QUESTIONS: Record<Exclude<QuestionTabId, 'portfolio'>, ChatQuestion[]> = {
  overview: [...STARTER_QUESTIONS, { id: 'learning', label: 'Education and learning', prompt: 'How has your education influenced your work?' }],
  experience: RESUME_DATA.experience.map(role => ({ id: role.id, label: `${role.role} at ${role.company}`, prompt: `What did your role as ${role.role} at ${role.company} involve? Describe your contribution and collaboration.` })),
  work: projectQuestions(RESUME_DATA.latestProjects || []),
  skills: RESUME_DATA.skills.map(category => ({ id: category.name, label: category.name, prompt: `Which of your documented projects demonstrate ${category.skills.join(', ')}? Distinguish direct experience from exploration.` })),
};
export const PORTFOLIO_GROUPS = [{ id: 'personal', label: 'Personal projects' }, { id: 'learning', label: 'Learning' }] as const;
export type PortfolioGroupId = typeof PORTFOLIO_GROUPS[number]['id'];
export const PORTFOLIO_QUESTIONS: Record<PortfolioGroupId, ChatQuestion[]> = {
  personal: projectQuestions(RESUME_DATA.projects),
  learning: RESUME_DATA.education.map(item => ({ id: item.id, label: item.degree, prompt: `What did you learn through ${item.degree} at ${item.school}, and where have you applied it?` })),
};

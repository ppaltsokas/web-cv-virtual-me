import React from 'react';
import { ExternalLink, FileText } from 'lucide-react';
import type { Project } from '../types';
import { API_URL } from '../constants';

export default function ProjectCard({ project }: { project: Project }) {
  return (
    <article className="p-6 rounded-2xl bg-slate-900/50 border border-slate-800 hover:border-emerald-500/50 transition-colors">
      <h3 className="text-lg font-bold text-slate-200 mb-4">{project.title}</h3>
      <p className="text-slate-400 text-sm mb-4">{project.description}</p>
      <div className="flex flex-wrap gap-2">
        {project.technologies.map(tech => <span key={tech} className="px-2 py-1 text-xs rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">{tech}</span>)}
      </div>
      {(project.link || project.pdfPath) && <div className="flex flex-wrap gap-4 mt-5 text-sm">
        {project.link && <a href={project.link} target="_blank" rel="noopener noreferrer" aria-label={`Visit ${project.title}`} className="inline-flex items-center gap-2 text-emerald-300 hover:underline"><ExternalLink size={16} />Project link</a>}
        {project.pdfPath && <a href={`${API_URL}/kb/pdf/${encodeURIComponent(project.pdfPath)}`} aria-label={`Read ${project.title} PDF`} className="inline-flex items-center gap-2 text-emerald-300 hover:underline"><FileText size={16} />Read PDF</a>}
      </div>}
    </article>
  );
}

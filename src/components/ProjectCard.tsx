import { ArrowUpRight, Github, MonitorPlay } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Project } from '../types';
import { ProjectVisual } from './ProjectVisual';
import { useLanguage } from '../context/LanguageContext';

export function ProjectCard({ project }: { project: Project }) {
  const { language } = useLanguage();
  const en = language === 'en';
  const actionCount = 1 + (project.github ? 1 : 0) + (project.demo ? 1 : 0);
  return (
    <article
      data-motion-card
      className="surface group flex h-full flex-col rounded-2xl p-3 transition duration-300 hover:-translate-y-1 hover:border-blue-300 dark:hover:border-blue-700"
    >
      <ProjectVisual
        title={project.title}
        image={project.cover}
        imageContain={project.coverContain}
        compact
      />
      <div className="flex flex-1 flex-col px-3 pb-3 pt-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="tag">{project.type}</span>
          <span className="text-xs text-slate-500 dark:text-slate-400">{project.status}</span>
        </div>
        <h3 className="text-xl font-bold tracking-tight">{project.title}</h3>
        <p className="mt-3 flex-1 text-sm leading-7 text-slate-600 dark:text-slate-300">{project.summary}</p>
        <p className="mt-3 text-xs text-slate-500">
          {en ? 'My role: ' : '我的职责：'}
          {project.role}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {project.tech.map((item) => (
            <span className="tag" key={item}>
              {item}
            </span>
          ))}
        </div>
        <div
          className={`mt-5 grid gap-2 ${
            actionCount === 1 ? 'grid-cols-1' : actionCount === 2 ? 'grid-cols-2' : 'grid-cols-3'
          }`}
        >
          <Link
            className="button-primary px-2"
            to={`/projects/${project.id}`}
            aria-label={en ? `View details for ${project.title}` : `查看${project.title}详情`}
          >
            <ArrowUpRight size={16} />
            {en ? 'Details' : '详情'}
          </Link>
          {project.github && (
            <a className="button-secondary px-2" href={project.github} target="_blank" rel="noreferrer">
              <Github size={16} />
              GitHub
            </a>
          )}
          {project.demo && (
            <a className="button-secondary px-2" href={project.demo} target="_blank" rel="noreferrer">
              <MonitorPlay size={16} />
              {en ? 'Demo' : '演示'}
            </a>
          )}
        </div>
      </div>
    </article>
  );
}

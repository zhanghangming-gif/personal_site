import { FolderSearch } from 'lucide-react';
import { useMemo, useState } from 'react';
import { ProjectCard } from '../components/ProjectCard';
import { ProjectFilters } from '../components/ProjectFilters';
import { Reveal } from '../components/Reveal';
import { useContent } from '../context/ContentContext';
import { useLanguage } from '../context/LanguageContext';

export default function ProjectsPage() {
  const { projects } = useContent();
  const { language } = useLanguage();
  const en = language === 'en';
  const [query, setQuery] = useState(''); const [type, setType] = useState(''); const [tech, setTech] = useState('');
  const filtered = useMemo(() => projects.filter((p) => { const haystack = `${p.title}${p.summary}${p.role}${p.tech.join('')}`.toLowerCase(); return haystack.includes(query.toLowerCase()) && (!type || p.type === type) && (!tech || p.tech.includes(tech)); }), [projects, query, type, tech]);
  return <div className="container-site pb-24 pt-32"><Reveal><p className="eyebrow">PROJECT ARCHIVE</p><h1 className="title-xl">{en ? 'All Projects' : '全部项目'}</h1><p className="mb-10 mt-4 max-w-2xl text-slate-600 dark:text-slate-300">{en ? 'A collection of completed and continuously iterated engineering projects. Use search and filters to find a specific topic.' : '这里记录已经完成、正在迭代和持续学习中的工程实践。使用搜索或筛选快速定位项目。'}</p></Reveal><ProjectFilters projects={projects} query={query} type={type} tech={tech} onQuery={setQuery} onType={setType} onTech={setTech} />{filtered.length ? <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{filtered.map((project) => <ProjectCard key={project.id} project={project} />)}</div> : <div className="surface grid min-h-80 place-items-center rounded-2xl p-8 text-center"><div><FolderSearch className="mx-auto mb-4 text-slate-400" size={44} /><h2 className="font-bold">{en ? 'No matching projects' : '没有找到匹配的项目'}</h2><p className="mt-2 text-sm text-slate-500">{en ? 'Try fewer keywords or different filters.' : '试试减少搜索词或切换筛选条件。'}</p></div></div>}</div>;
}

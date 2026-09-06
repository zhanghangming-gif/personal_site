import { Search } from 'lucide-react';
import type { Project } from '../types';
import { useLanguage } from '../context/LanguageContext';

export function ProjectFilters({ projects, query, type, tech, onQuery, onType, onTech }: { projects: Project[]; query: string; type: string; tech: string; onQuery: (v: string) => void; onType: (v: string) => void; onTech: (v: string) => void }) {
  const { language } = useLanguage();
  const en = language === 'en';
  const types = [...new Set(projects.map((p) => p.type))];
  const techs = [...new Set(projects.flatMap((p) => p.tech))];
  return <div className="surface mb-8 grid gap-3 rounded-2xl p-4 md:grid-cols-[1fr_190px_190px]"><label className="relative"><span className="sr-only">{en ? 'Search projects' : '搜索项目'}</span><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} /><input className="min-h-11 w-full rounded-xl border bg-transparent pl-10 pr-3 text-sm" placeholder={en ? 'Search projects, technology, or roles…' : '搜索项目、技术或职责…'} value={query} onChange={(e) => onQuery(e.target.value)} /></label><label><span className="sr-only">{en ? 'Filter by project type' : '按项目类型筛选'}</span><select className="min-h-11 w-full rounded-xl border bg-[rgb(var(--surface))] px-3 text-sm" value={type} onChange={(e) => onType(e.target.value)}><option value="">{en ? 'All Types' : '全部类型'}</option>{types.map((v) => <option key={v}>{v}</option>)}</select></label><label><span className="sr-only">{en ? 'Filter by technology' : '按技术筛选'}</span><select className="min-h-11 w-full rounded-xl border bg-[rgb(var(--surface))] px-3 text-sm" value={tech} onChange={(e) => onTech(e.target.value)}><option value="">{en ? 'All Technologies' : '全部技术'}</option>{techs.map((v) => <option key={v}>{v}</option>)}</select></label></div>;
}

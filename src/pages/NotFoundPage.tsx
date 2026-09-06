import { ArrowLeft, Compass } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useLanguage } from '../context/LanguageContext';

export default function NotFoundPage() { const { language } = useLanguage(); const en = language === 'en'; return <div className="container-site grid min-h-[85vh] place-items-center pt-16 text-center"><div><Compass className="mx-auto mb-6 text-accent" size={70} strokeWidth={1.1} /><p className="eyebrow">ERROR / 404</p><h1 className="text-5xl font-black tracking-tight">{en ? 'This page has not been explored yet' : '这里还没有被探索'}</h1><p className="mx-auto mt-5 max-w-lg text-slate-600 dark:text-slate-300">{en ? 'The page does not exist, or its address has changed.' : '你访问的页面不存在，可能已经移动或链接有误。'}</p><Link className="button-primary mt-8" to="/"><ArrowLeft size={17} />{en ? 'Back home' : '返回首页'}</Link></div></div>; }

import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { SiteLayout } from './layouts/SiteLayout';
import { ThemeProvider } from './hooks/useTheme';
import { ToastProvider } from './components/Toast';
import { ContentProvider } from './context/ContentContext';
import { AnalyticsTracker } from './components/AnalyticsTracker';
import { LanguageProvider, useLanguage } from './context/LanguageContext';
import { SoundProvider } from './hooks/useSound';

const HomePage = lazy(() => import('./pages/HomePage'));
const ProjectsPage = lazy(() => import('./pages/ProjectsPage'));
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage'));
const MessagesPage = lazy(() => import('./pages/MessagesPage'));
const ScoreTransposePage = lazy(() => import('./pages/ScoreTransposePage'));
const NotFoundPage = lazy(() => import('./pages/NotFoundPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));

function Loading() { const { language } = useLanguage(); return <div className="container-site flex min-h-[70vh] items-center justify-center"><div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-accent" aria-label={language === 'zh' ? '页面加载中' : 'Loading page'} /></div>; }

export default function App() {
  return <SoundProvider><ThemeProvider><ToastProvider><LanguageProvider><ContentProvider><AnalyticsTracker /><Suspense fallback={<Loading />}><Routes><Route element={<SiteLayout />}><Route path="/" element={<HomePage />} /><Route path="/projects" element={<ProjectsPage />} /><Route path="/projects/:projectId" element={<ProjectDetailPage />} /><Route path="/score-transpose" element={<ScoreTransposePage />} /><Route path="/messages" element={<MessagesPage />} /><Route path="/404" element={<NotFoundPage />} /><Route path="*" element={<Navigate to="/404" replace />} /></Route><Route path="/admin" element={<AdminPage />} /></Routes></Suspense></ContentProvider></LanguageProvider></ToastProvider></ThemeProvider></SoundProvider>;
}

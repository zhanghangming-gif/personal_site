import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  bashuPhotos as defaultBashuPhotos,
  campusPhotos as defaultCampusPhotos,
  experiences as defaultExperiences,
  honors as defaultHonors,
  mingyuePhotos as defaultMingyuePhotos,
  projects as defaultProjects,
  roboconPhotos as defaultRoboconPhotos,
  siteData as defaultSiteData,
} from '../data/siteData';
import type { CampusPhoto, Experience, Honor, Project } from '../types';
import { apiRequest, isDemoMode } from '../services/api';
import { useLanguage } from './LanguageContext';
import {
  englishSiteData,
  translateExperiences,
  translateGallery,
  translateHonors,
  translateProjects,
} from '../i18n/englishContent';

export interface EditableContent {
  siteData: typeof defaultSiteData;
  projects: Project[];
  experiences: Experience[];
  honors: Honor[];
  galleries: {
    bashuPhotos: CampusPhoto[];
    mingyuePhotos: CampusPhoto[];
    roboconPhotos: CampusPhoto[];
    campusPhotos: CampusPhoto[];
  };
}

export const defaultContent: EditableContent = {
  siteData: defaultSiteData,
  projects: defaultProjects,
  experiences: defaultExperiences,
  honors: defaultHonors,
  galleries: {
    bashuPhotos: defaultBashuPhotos,
    mingyuePhotos: defaultMingyuePhotos,
    roboconPhotos: defaultRoboconPhotos,
    campusPhotos: defaultCampusPhotos,
  },
};

const ContentContext = createContext<EditableContent>(defaultContent);

function restoreExperienceIds(content: EditableContent): EditableContent {
  return {
    ...content,
    experiences: content.experiences.map((experience, index) => ({
      ...experience,
      id: experience.id ?? defaultExperiences[index]?.id,
    })),
  };
}

export function ContentProvider({ children }: { children: React.ReactNode }) {
  const { language } = useLanguage();
  const [remote, setRemote] = useState<EditableContent | null>(null);
  useEffect(() => {
    if (isDemoMode) return;
    apiRequest<{ success: boolean; data: EditableContent | null }>('/api/content')
      .then((result) => result.data && setRemote(restoreExperienceIds(result.data)))
      .catch(() => undefined);
  }, []);
  const value = useMemo(() => {
    const source = remote ?? defaultContent;
    if (language === 'zh' || window.location.pathname.startsWith('/admin')) return source;
    return {
      ...source,
      siteData: { ...source.siteData, ...englishSiteData, about: { ...source.siteData.about, ...englishSiteData.about } },
      projects: translateProjects(source.projects),
      experiences: translateExperiences(source.experiences),
      honors: translateHonors(source.honors),
      galleries: {
        bashuPhotos: translateGallery(source.galleries.bashuPhotos, 'Bashu Secondary School'),
        mingyuePhotos: translateGallery(source.galleries.mingyuePhotos, 'Mingyue Innovation Program'),
        roboconPhotos: translateGallery(source.galleries.roboconPhotos, 'GSing ROBOCON Team'),
        campusPhotos: translateGallery(source.galleries.campusPhotos, 'Student Art Troupe'),
      },
    };
  }, [language, remote]);
  return <ContentContext.Provider value={value}>{children}</ContentContext.Provider>;
}

export const useContent = () => useContext(ContentContext);

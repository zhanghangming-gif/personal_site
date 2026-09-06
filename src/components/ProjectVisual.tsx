import { Bot, CircuitBoard, ScanSearch } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export function ProjectVisual({
  title,
  compact = false,
  image,
  imageContain = false,
}: {
  title: string;
  compact?: boolean;
  image?: string;
  imageContain?: boolean;
}) {
  const { language } = useLanguage();
  const en = language === 'en';
  const Icon = title.includes('雷达') ? ScanSearch : title.includes('嵌入式') ? CircuitBoard : Bot;
  return (
    <div
      data-motion-image
      className={`project-visual relative flex items-center justify-center overflow-hidden ${compact ? 'h-44' : 'min-h-72'} rounded-2xl border`}
      role="img"
      aria-label={
        en
          ? `${title} project ${image ? 'photo' : 'illustration'}`
          : `${title} 项目${image ? '照片' : '示意图'}`
      }
    >
      {image ? (
        <>
          <img
            src={image}
            alt=""
            className={`absolute inset-0 h-full w-full transition duration-500 group-hover:scale-[1.02] ${imageContain ? 'bg-white object-contain p-3 dark:bg-slate-950' : 'object-cover'}`}
          />
          <div className="absolute inset-0 bg-gradient-to-t from-slate-950/75 via-transparent to-transparent" />
        </>
      ) : (
        <>
          <div className="absolute inset-5 rounded-xl border border-dashed border-blue-400/25" />
          <Icon className="text-accent/70 dark:text-blue-300/70" size={compact ? 56 : 88} strokeWidth={1.2} />
        </>
      )}
      <span
        className={`absolute bottom-4 left-5 text-xs font-semibold tracking-wider ${image ? 'text-white' : 'text-slate-500 dark:text-slate-400'}`}
      >
        PROJECT / {title.slice(0, 12)}
      </span>
    </div>
  );
}

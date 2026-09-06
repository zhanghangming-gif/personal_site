import { AnimatePresence, motion } from 'framer-motion';
import { CalendarDays, ChevronLeft, ChevronRight, Images, MapPin, Maximize2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useLanguage } from '../context/LanguageContext';
import { useSound } from '../hooks/useSound';

type Photo = { src: string; zh: string; en: string };
type PhotoGroup = {
  id: string;
  zh: string;
  en: string;
  placeZh: string;
  placeEn: string;
  time: string;
  photos: Photo[];
};

const base = '/media/life-gallery';
const photo = (file: string, zh: string, en: string): Photo => ({ src: `${base}/${file}`, zh, en });

const groups: PhotoGroup[] = [
  {
    id: 'japan',
    zh: '日本之行',
    en: 'Japan',
    placeZh: '东京 / 筑波 / 湘南',
    placeEn: 'Tokyo / Tsukuba / Shonan',
    time: '2025',
    photos: [
      photo('japan-01.jpg', '筑波大学留念', 'A visit to the University of Tsukuba'),
      photo('japan-02.jpg', '东京大学安田讲堂', 'Yasuda Auditorium, the University of Tokyo'),
      photo('japan-03.jpg', '浅草寺五重塔', 'Five-story pagoda at Senso-ji'),
      photo('japan-04.jpg', '湘南海岸与富士山晚霞', 'Sunset over Mount Fuji from the Shonan coast'),
      photo('japan-05.jpg', '东京塔夜景', 'Tokyo Tower at night'),
      photo('japan-06.jpg', '涩谷街头', 'Streets of Shibuya'),
      photo('japan-07.jpg', '早稻田大学留念', 'A visit to Waseda University'),
    ],
  },
  {
    id: 'shenzhen',
    zh: '深圳之行',
    en: 'Shenzhen',
    placeZh: '广东深圳',
    placeEn: 'Shenzhen, Guangdong',
    time: '2025',
    photos: [
      photo('shenzhen-01.jpg', '大梅沙海滨公园', 'Dameisha Coastal Park'),
      photo('shenzhen-02.jpg', '深圳城市建筑', 'Shenzhen city architecture'),
      photo('shenzhen-03.jpg', '深圳城市天际线', 'Shenzhen skyline'),
      photo('shenzhen-04.jpg', '深圳北站夜色', 'Shenzhenbei Railway Station at night'),
      photo('shenzhen-05.jpg', '大梅沙夜海', 'Night swim at Dameisha'),
      photo('shenzhen-06.jpg', '深圳科创学院合影', 'Group photo at Shenzhen InnoX'),
      photo('shenzhen-07.jpg', '港中大深圳校门', 'CUHK-Shenzhen campus gate'),
      photo('shenzhen-08.jpg', '雨后街巷', 'Walking through rainy streets'),
    ],
  },
  {
    id: 'jiuzhaigou',
    zh: '九寨沟之行',
    en: 'Jiuzhaigou',
    placeZh: '四川九寨沟',
    placeEn: 'Jiuzhaigou, Sichuan',
    time: '2025',
    photos: [
      photo('jiuzhaigou-01.jpg', '冬日九寨沟', 'Jiuzhaigou in winter'),
      photo('jiuzhaigou-02.jpg', '与朋友同行', 'Traveling with friends'),
      photo('jiuzhaigou-03.jpg', '清澈的海子', 'A crystal-clear alpine lake'),
      photo('jiuzhaigou-04.jpg', '旅途夜晚', 'An evening on the journey'),
      photo('jiuzhaigou-05.jpg', '山间海子', 'Mountain lake in Jiuzhaigou'),
      photo('jiuzhaigou-06.jpg', '枝影与蓝水', 'Branches over blue water'),
      photo('jiuzhaigou-07.jpg', '冰封长海', 'Frozen alpine lake'),
      photo('jiuzhaigou-08.jpg', '云雾山谷', 'Misty mountain valley'),
      photo('jiuzhaigou-09.jpg', '芦苇与蓝水', 'Reeds beside blue water'),
      photo('jiuzhaigou-10.jpg', '雪落海子', 'Snowfall over turquoise water'),
      photo('jiuzhaigou-11.jpg', '清澈水岸', 'Crystal-clear lakeshore'),
    ],
  },
  {
    id: 'zhangjiajie-tianmen',
    zh: '张家界和天门山之行',
    en: 'Zhangjiajie & Tianmen Mountain',
    placeZh: '湖南张家界 / 天门山',
    placeEn: 'Zhangjiajie / Tianmen Mountain',
    time: '2025',
    photos: [
      photo('zhangjiajie-tianmen-01.jpg', '武陵源塔楼', 'Wulingyuan tower under the clouds'),
      photo('zhangjiajie-tianmen-02.jpg', '山谷索道', 'Cable cars crossing the mountain valley'),
      photo('zhangjiajie-tianmen-03.jpg', '张家界峰林', 'Sandstone pillars in Zhangjiajie'),
      photo('zhangjiajie-tianmen-04.jpg', '天门山云雾远眺', 'Misty view from Tianmen Mountain'),
      photo('zhangjiajie-tianmen-05.jpg', '云雾中的石峰', 'Stone peaks wrapped in mist'),
      photo('zhangjiajie-tianmen-06.jpg', '雨雾山景', 'Rain and clouds over the cliffs'),
      photo('zhangjiajie-tianmen-07.jpg', '玻璃栈道脚下', 'Looking down through the glass walkway'),
      photo('zhangjiajie-tianmen-08.jpg', '天门洞阶梯', 'Stairway toward Tianmen Cave'),
    ],
  },
  {
    id: 'life',
    zh: '生活碎片',
    en: 'Life Fragments',
    placeZh: '重庆 / 校园 / 日常现场',
    placeEn: 'Chongqing / Campus / Everyday Scenes',
    time: '2024 - 2026',
    photos: [
      photo('life-01.jpg', '重庆大学校园', 'Chongqing University campus'),
      photo('life-02.jpg', '室内乐音乐会', 'A chamber music evening'),
      photo('life-03.jpg', '交响乐现场', 'At a symphonic concert'),
      photo('life-04.jpg', '排练日常', 'A rehearsal day'),
      photo('life-05.jpg', '乐团排练', 'Orchestra rehearsal'),
      photo('life-06.jpg', '校园音乐会', 'Campus concert'),
      photo('life-07.jpg', '雨夜校园', 'Campus on a rainy night'),
      photo('life-08.jpg', '重庆夜景', 'Chongqing at night'),
      photo('life-09.jpg', '城市水岸', 'City waterfront'),
      photo('life-10.jpg', '海边夜色', 'Night by the sea'),
      photo('life-11.jpg', '校园演出现场', 'Campus performance'),
      photo('life-12.jpg', '树影里的校园路', 'Tree-lined campus road'),
      photo('life-13.jpg', '机器人调试间隙', 'Robot debugging in progress'),
      photo('life-14.jpg', '傍晚的校园路', 'Campus road at sunset'),
      photo('life-15.jpg', '春日花丛', 'Spring flowers on campus'),
      photo('life-16.jpg', '洪崖洞夜景', 'Hongyadong at night'),
    ],
  },
];

export function LifeGallery() {
  const { language } = useLanguage();
  const { play } = useSound();
  const en = language === 'en';
  const [groupIndex, setGroupIndex] = useState(0);
  const [index, setIndex] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const pointerStart = useRef<number | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const group = groups[groupIndex];
  const current = group.photos[index];

  const move = (step: number) => {
    setIndex((value) => (value + step + group.photos.length) % group.photos.length);
  };
  const openFullscreen = (photoIndex = index) => {
    setIndex(photoIndex);
    play('panelOpen');
    setFullscreen(true);
  };
  const closeFullscreen = () => {
    play('panelClose');
    setFullscreen(false);
  };

  useEffect(() => {
    if (!fullscreen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButton.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeFullscreen();
      if (event.key === 'ArrowLeft') move(-1);
      if (event.key === 'ArrowRight') move(1);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [fullscreen, group.photos.length, play]);

  const onPointerDown = (event: React.PointerEvent) => {
    pointerStart.current = event.clientX;
  };

  const onPointerUp = (event: React.PointerEvent) => {
    if (pointerStart.current === null) return;
    const distance = event.clientX - pointerStart.current;
    pointerStart.current = null;
    if (Math.abs(distance) > 48) move(distance < 0 ? 1 : -1);
  };

  const immersiveViewer = (
    <motion.div
      className="fixed inset-0 z-[100] overflow-hidden bg-slate-950 text-white"
      role="dialog"
      aria-modal="true"
      aria-label={en ? 'Immersive photo journal viewer' : '沉浸式影集浏览'}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      onPointerCancel={() => {
        pointerStart.current = null;
      }}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_70%_20%,rgba(59,130,246,0.22),transparent_30%),linear-gradient(180deg,rgba(2,6,23,0.38),rgba(2,6,23,0.96))]" />
      <div className="relative flex h-full flex-col px-3 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))] sm:px-5 sm:pb-5 sm:pt-[max(1rem,env(safe-area-inset-top))]">
        <div className="flex min-h-14 shrink-0 items-start justify-between gap-4 pb-3 sm:min-h-16 sm:pb-4">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.28em] text-blue-300">
              {en ? group.en : group.zh}
            </p>
            <h4 className="mt-1 line-clamp-2 text-xl font-black leading-tight sm:text-2xl">{en ? current.en : current.zh}</h4>
          </div>
          <button
            ref={closeButton}
            type="button"
            onClick={closeFullscreen}
            data-sound-off="true"
            className="grid size-12 shrink-0 place-items-center rounded-full border border-white/20 bg-white/10 text-white backdrop-blur transition hover:bg-blue-600"
            aria-label={en ? 'Close fullscreen' : '关闭全屏'}
          >
            <X className="size-6" />
          </button>
        </div>

        <div className="relative grid h-[calc(100dvh-12.5rem)] min-h-[280px] shrink-0 place-items-center overflow-hidden rounded-[1.1rem] border border-white/10 bg-white/[0.03] sm:h-[calc(100dvh-13.75rem)] sm:min-h-[360px] sm:rounded-[1.5rem] lg:h-[calc(100dvh-14rem)]">
          <AnimatePresence mode="wait">
            <motion.div
              key={current.src}
              className="absolute inset-0 grid place-items-center"
              initial={{ clipPath: 'inset(0 100% 0 0)', opacity: 0.7 }}
              animate={{ clipPath: 'inset(0 0% 0 0)', opacity: 1 }}
              exit={{ clipPath: 'inset(0 0 0 100%)', opacity: 0.5 }}
              transition={{ duration: 0.72, ease: [0.76, 0, 0.24, 1] }}
            >
              <motion.img
                src={current.src}
                alt={en ? current.en : current.zh}
                className="h-full w-full select-none object-contain"
                draggable={false}
                initial={{ scale: 1.045, x: 26 }}
                animate={{ scale: 1, x: 0 }}
                exit={{ scale: 1.02, x: -24 }}
                transition={{ duration: 0.82, ease: [0.22, 1, 0.36, 1] }}
              />
            </motion.div>
          </AnimatePresence>
          <button
            type="button"
            onClick={() => move(-1)}
            className="absolute left-2 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-slate-950/50 text-white backdrop-blur transition hover:bg-blue-600 sm:left-5 sm:size-12"
            aria-label={en ? 'Previous photo' : '上一张照片'}
          >
            <ChevronLeft className="size-6" />
          </button>
          <button
            type="button"
            onClick={() => move(1)}
            className="absolute right-2 top-1/2 grid size-10 -translate-y-1/2 place-items-center rounded-full border border-white/20 bg-slate-950/50 text-white backdrop-blur transition hover:bg-blue-600 sm:right-5 sm:size-12"
            aria-label={en ? 'Next photo' : '下一张照片'}
          >
            <ChevronRight className="size-6" />
          </button>
          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/85 to-transparent p-3 sm:p-5">
            <div className="flex flex-wrap items-end justify-between gap-2 sm:gap-4">
              <div className="flex flex-wrap gap-2 text-[11px] font-semibold text-slate-200 sm:text-xs">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 backdrop-blur">
                  <MapPin className="size-3.5" />
                  {en ? group.placeEn : group.placeZh}
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 backdrop-blur">
                  <CalendarDays className="size-3.5" />
                  {group.time}
                </span>
              </div>
              <span className="font-mono text-xs font-bold text-slate-300 sm:text-sm">
                {String(index + 1).padStart(2, '0')} / {String(group.photos.length).padStart(2, '0')}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-3 flex shrink-0 gap-2 overflow-x-auto pb-[max(0.25rem,env(safe-area-inset-bottom))] sm:mt-4">
          {group.photos.map((item, itemIndex) => (
            <button
              key={item.src}
              type="button"
              onClick={() => setIndex(itemIndex)}
              className={`relative h-14 w-20 shrink-0 overflow-hidden rounded-lg border transition sm:h-20 sm:w-32 sm:rounded-xl ${index === itemIndex ? 'border-blue-300 opacity-100 ring-2 ring-blue-300/30' : 'border-white/10 opacity-45 hover:opacity-100'}`}
              aria-label={`${en ? 'Open photo' : '查看照片'} ${itemIndex + 1}`}
            >
              <img src={item.src} alt="" loading="lazy" className="h-full w-full object-cover" />
            </button>
          ))}
        </div>
      </div>
    </motion.div>
  );

  return (
    <div className="mt-16" data-motion-section>
      <div className="mb-7 flex flex-col justify-between gap-5 md:flex-row md:items-end" data-motion-reveal>
        <div>
          <p className="eyebrow">PHOTO JOURNAL</p>
          <h3
            data-motion-heading
            className="mt-3 text-3xl font-black tracking-tight text-slate-950 dark:text-white sm:text-4xl"
          >
            {en ? 'Moments Along the Way' : '沿途与日常'}
          </h3>
          <p className="mt-3 max-w-2xl leading-7 text-slate-600 dark:text-slate-300">
            {en
              ? 'A more cinematic journal of journeys, music, and everyday life—browse the mosaic, then enter the album.'
              : '把旅途、音乐与日常整理成一组更沉浸的影集。先浏览照片墙，再进入完整相册。'}
          </p>
        </div>
        <div className="hidden size-14 place-items-center rounded-2xl border border-slate-200 bg-white text-blue-600 shadow-sm dark:border-slate-700 dark:bg-slate-900 md:grid">
          <Images className="size-6" />
        </div>
      </div>

      <div
        className="mb-5 flex gap-2 overflow-x-auto pb-2"
        role="tablist"
        aria-label={en ? 'Photo themes' : '照片主题'}
        data-motion-reveal
      >
        {groups.map((item, itemIndex) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={groupIndex === itemIndex}
            onClick={() => {
              setGroupIndex(itemIndex);
              setIndex(0);
            }}
            className={`shrink-0 rounded-full border px-4 py-2.5 text-sm font-bold transition ${groupIndex === itemIndex ? 'border-blue-600 bg-blue-600 text-white shadow-lg shadow-blue-600/20' : 'border-slate-200 bg-white text-slate-600 hover:border-blue-400 hover:text-blue-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'}`}
          >
            {en ? item.en : item.zh} <span className="ml-1 opacity-65">{item.photos.length}</span>
          </button>
        ))}
      </div>

      <div className="relative overflow-hidden rounded-[1.5rem] border border-slate-200 bg-slate-950 p-5 text-white shadow-2xl shadow-slate-950/10 dark:border-slate-800 sm:p-7" data-motion-reveal>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_88%_10%,rgba(96,165,250,0.22),transparent_28%),linear-gradient(135deg,rgba(15,23,42,0.96),rgba(2,6,23,0.98))]" />
        <div className="relative grid gap-7 lg:grid-cols-[0.85fr_1.15fr] lg:items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.26em] text-blue-300">
              {en ? 'Selected Album' : '当前影集'}
            </p>
            <h4 className="mt-3 text-3xl font-black tracking-tight sm:text-4xl">{en ? group.en : group.zh}</h4>
            <div className="mt-5 flex flex-wrap gap-3 text-sm text-slate-300">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-2">
                <MapPin className="size-4" />
                {en ? group.placeEn : group.placeZh}
              </span>
              <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-2">
                <CalendarDays className="size-4" />
                {group.time}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => openFullscreen(0)}
            data-sound-off="true"
            className="group relative min-h-[220px] overflow-hidden rounded-[1.25rem] border border-white/15 bg-white/5 text-left sm:min-h-[300px]"
            aria-label={en ? `Open ${group.en} album` : `打开${group.zh}影集`}
          >
            <img src={group.photos[0].src} alt="" className="absolute inset-0 h-full w-full object-cover opacity-82 transition duration-700 group-hover:scale-[1.04]" />
            <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/15 to-transparent" />
            <span className="absolute bottom-5 left-5 inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-bold backdrop-blur transition group-hover:bg-blue-600">
              <Maximize2 className="size-4" />
              {en ? 'Enter album' : '进入影集'}
            </span>
            <span className="absolute right-5 top-5 font-mono text-sm font-bold text-white/75">
              {group.photos.length} PHOTOS
            </span>
          </button>
        </div>
      </div>

      <div className="mt-5 columns-1 gap-4 sm:columns-2 lg:columns-3" data-motion-reveal>
        {group.photos.map((item, itemIndex) => {
          const tall = itemIndex % 5 === 1 || itemIndex % 7 === 4;
          const compact = itemIndex % 6 === 2;
          return (
            <button
              key={item.src}
              type="button"
              onClick={() => openFullscreen(itemIndex)}
              className="group mb-4 block w-full break-inside-avoid overflow-hidden rounded-[1.1rem] border border-slate-200 bg-slate-950 text-left shadow-sm transition duration-500 hover:-translate-y-1 hover:shadow-xl hover:shadow-slate-950/10 dark:border-slate-800"
              aria-label={`${en ? 'Open photo' : '打开照片'} ${itemIndex + 1}`}
            >
              <span className={`relative block overflow-hidden ${tall ? 'aspect-[4/5]' : compact ? 'aspect-[5/3]' : 'aspect-[4/3]'}`}>
                <img src={item.src} alt={en ? item.en : item.zh} loading="lazy" className="h-full w-full object-cover transition duration-700 group-hover:scale-[1.06]" />
                <span className="absolute inset-0 bg-gradient-to-t from-slate-950/78 via-slate-950/0 to-transparent opacity-80 transition group-hover:opacity-100" />
                <span className="absolute inset-x-0 bottom-0 translate-y-1 p-4 text-white transition duration-300 group-hover:translate-y-0">
                  <span className="block text-[10px] font-bold uppercase tracking-[0.2em] text-blue-200">
                    {group.time} · {String(itemIndex + 1).padStart(2, '0')}
                  </span>
                  <span className="mt-1 block text-sm font-bold leading-5">{en ? item.en : item.zh}</span>
                </span>
              </span>
            </button>
          );
        })}
      </div>

      <AnimatePresence>
        {fullscreen && immersiveViewer}
      </AnimatePresence>
    </div>
  );
}

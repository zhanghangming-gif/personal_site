import { ArrowRight, Bot, BrainCircuit, Clipboard, Github, Mail, Star, Target, Wrench } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { HonorModal } from '../components/HonorModal';
import { CampusGallery } from '../components/CampusGallery';
import { LifeGallery } from '../components/LifeGallery';
import { OpeningAnimation } from '../components/OpeningAnimation';
import { ProjectCard } from '../components/ProjectCard';
import { Reveal } from '../components/Reveal';
import MessagesPage from './MessagesPage';
import { useToast } from '../components/Toast';
import { useContent } from '../context/ContentContext';
import type { Honor, StarState } from '../types';
import { useLanguage } from '../context/LanguageContext';
import { getSiteStars, toggleSiteStar } from '../services/starService';
import { usePortfolioMotion } from '../hooks/usePortfolioMotion';

type HonorFilterId = 'all' | 'competition' | 'innovation' | 'arts' | 'university' | 'national';

const honorFilterText = (honor: Honor) => `${honor.title} ${honor.level} ${honor.category}`;

function matchesHonorFilter(honor: Honor, filter: HonorFilterId) {
  if (filter === 'all') return true;
  const text = honorFilterText(honor);
  if (filter === 'competition') return /竞赛|比赛|大赛|挑战赛|ROBOCON|RMBC|MCM|Competition|Robotics|Modeling|Challenge|Contest/i.test(text);
  if (filter === 'innovation') return /科创|创新|创业|科研|训练营|SRTP|AI|Innovation|Research|Course|Training|Entrepreneurship/i.test(text);
  if (filter === 'arts') return /艺术|文艺|音乐|Arts|Music/i.test(text);
  if (filter === 'university') return /校级|院级|重庆大学|University|Institute/i.test(text);
  return /国家|全国|美国大学生|National|MCM/i.test(text);
}

export default function HomePage() {
  const { siteData, projects, experiences, honors, galleries } = useContent();
  const { bashuPhotos, mingyuePhotos, roboconPhotos, campusPhotos } = galleries;
  const qqMailUrl = `https://mail.qq.com/cgi-bin/qm_share?t=qm_mailme&email=${encodeURIComponent(siteData.email)}`;
  const [selectedHonor, setSelectedHonor] = useState<Honor | null>(null);
  const [honorFilter, setHonorFilter] = useState<HonorFilterId>('all');
  const [stars, setStars] = useState<StarState>({ starred: false, starCount: 0 });
  const [starBusy, setStarBusy] = useState(false);
  const toast = useToast();
  const { language } = useLanguage();
  const en = language === 'en';
  const location = useLocation();
  const pageRef = useRef<HTMLDivElement>(null);
  const honorFilterOptions: { id: HonorFilterId; label: string }[] = [
    { id: 'all', label: en ? 'All' : '全部' },
    { id: 'competition', label: en ? 'Competition' : '竞赛' },
    { id: 'innovation', label: en ? 'Innovation' : '科创' },
    { id: 'arts', label: en ? 'Arts' : '艺术' },
    { id: 'university', label: en ? 'University' : '校级' },
    { id: 'national', label: en ? 'National' : '国家级' },
  ];
  const filteredHonors = useMemo(
    () => honors.filter((honor) => matchesHonorFilter(honor, honorFilter)),
    [honors, honorFilter],
  );
  const honorYears = Array.from(new Set(filteredHonors.map((honor) => honor.year.slice(0, 4))));
  const motionRefreshKey = `${language}-${projects.length}-${experiences.length}-${honors.length}-${honorFilter}-${filteredHonors.length}`;
  const shouldSkipOpening = Boolean(location.hash && location.hash !== '#home');

  usePortfolioMotion(pageRef, motionRefreshKey);

  useEffect(() => {
    void getSiteStars()
      .then(setStars)
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    if (!location.hash) return;
    const target = document.querySelector(location.hash);
    if (!target) return;
    window.setTimeout(() => target.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  }, [location.hash]);

  const handleStar = async () => {
    if (starBusy) return;
    const previous = stars;
    const optimistic = {
      starred: !previous.starred,
      starCount: Math.max(0, previous.starCount + (previous.starred ? -1 : 1)),
    };
    setStars(optimistic);
    setStarBusy(true);
    try {
      const next = await toggleSiteStar();
      setStars(next);
      toast(
        next.starred
          ? en
            ? 'Thanks for the star!'
            : '感谢你的 Star！'
          : en
            ? 'Star removed'
            : '已取消 Star',
      );
    } catch (caught) {
      setStars(previous);
      toast(caught instanceof Error ? caught.message : en ? 'Star failed' : 'Star 失败', 'error');
    } finally {
      setStarBusy(false);
    }
  };

  const copyEmail = async () => {
    await navigator.clipboard.writeText(siteData.email);
    toast(en ? 'Email copied' : '邮箱已复制');
  };
  return (
    <div ref={pageRef} className="motion-page">
      <OpeningAnimation skip={shouldSkipOpening} />
      <section id="home" className="hero-home relative min-h-screen overflow-hidden pt-16">
        <div data-hero-bg className="absolute inset-0 bg-[url('/home/hero-robot.webp')] bg-cover bg-center" />
        <div className="hero-home-overlay absolute inset-0" />
        <div className="container-site relative z-10 grid min-h-[calc(100vh-4rem)] items-center py-20">
          <div className="hero-copy-panel max-w-4xl">
            <p data-hero-kicker className="eyebrow">
              HELLO, I BUILD ROBOTS & SYSTEMS
            </p>
            <h1 className="max-w-4xl text-5xl font-black leading-[1.06] tracking-[-.055em] sm:text-6xl lg:text-7xl">
              <span className="motion-line">
                <span data-hero-line className="motion-line-inner">
                  {en ? 'Hi, I’m ' : '你好，我是'}
                  <span className="gradient-text">{siteData.name}</span>
                </span>
              </span>
            </h1>
            <p data-hero-copy className="mt-6 text-xl font-semibold text-slate-700 dark:text-slate-200">
              {siteData.identity}
            </p>
            <p
              data-hero-copy
              className="mt-4 max-w-2xl text-base leading-8 text-slate-600 dark:text-slate-300 sm:text-lg"
            >
              {siteData.intro}
            </p>
            <div data-hero-action className="mt-8 flex flex-wrap gap-3">
              <Link className="button-primary" to="/projects">
                {en ? 'View Projects' : '查看项目'} <ArrowRight size={17} />
              </Link>
              <a className="button-secondary" href={qqMailUrl} target="_blank" rel="noreferrer">
                <Mail size={17} />
                {en ? 'Contact Me' : '联系我'}
              </a>
            </div>
            <div data-hero-meta className="mt-7 flex items-center gap-3">
              <button
                type="button"
                onClick={() => void handleStar()}
                disabled={starBusy}
                aria-label={
                  stars.starred
                    ? en
                      ? 'Remove star'
                      : '取消 Star'
                    : en
                      ? 'Give this site a star'
                      : '给这个网站 Star'
                }
                aria-pressed={stars.starred}
                className={`glass-control inline-flex min-h-11 items-center gap-2 rounded-xl px-4 text-sm font-semibold transition hover:-translate-y-0.5 active:translate-y-0 disabled:cursor-wait disabled:opacity-80 ${
                  stars.starred
                    ? 'border-amber-300 bg-amber-400/15 text-amber-500 shadow-lg shadow-amber-500/10 dark:border-amber-400/40 dark:text-amber-300'
                    : 'text-slate-600 hover:border-amber-300 hover:text-amber-500 dark:text-slate-300'
                }`}
              >
                <Star size={18} fill={stars.starred ? 'currentColor' : 'none'} />
                <span>{stars.starCount}</span>
              </button>
              <button
                onClick={() =>
                  siteData.github
                    ? open(siteData.github, '_blank')
                    : toast(en ? 'GitHub is not public yet' : 'GitHub 暂未公开')
                }
                className="glass-control grid h-11 w-11 place-items-center rounded-xl transition hover:-translate-y-0.5 hover:text-accent"
                aria-label={en ? 'Visit GitHub' : '访问 GitHub'}
              >
                <Github size={19} />
              </button>
              <span className="text-sm text-slate-500">{siteData.location}</span>
            </div>
          </div>
        </div>
      </section>

      <section id="about" className="section-pad scroll-mt-16" data-motion-section>
        <div className="container-site">
          <Reveal>
            <p className="eyebrow">01 / ABOUT</p>
            <div className="grid gap-12 lg:grid-cols-[.75fr_1.25fr]">
              <div>
                <h2 className="title-xl">
                  {en ? 'Start with real problems' : '从真实问题出发'}
                  <br />
                  {en ? 'build robots that matter' : '构建有用的机器人'}
                </h2>
                <p className="mt-6 leading-8 text-slate-600 dark:text-slate-300">
                  {siteData.about.direction}
                </p>
              </div>
              <div className="grid gap-4 sm:grid-cols-3">
                {[
                  [
                    Bot,
                    en ? 'Robotic Systems' : '机器人系统',
                    en
                      ? 'Connect perception, decision-making, and action into complete systems that can be tested in the real world.'
                      : '把感知、决策与执行连接起来，构建能够在真实场景中验证的完整系统。',
                  ],
                  [
                    BrainCircuit,
                    en ? 'First Principles' : '第一性原理',
                    en
                      ? 'Break problems down from goals and constraints, then seek the simplest reliable path that can be verified.'
                      : '从目标与约束出发拆解问题，寻找简单、可靠且可验证的实现路径。',
                  ],
                  [
                    Target,
                    en ? 'Product & Users' : '产品与用户',
                    en
                      ? 'Understand the context and user pain points first, then decide what to build and how value should be measured.'
                      : '先理解真实场景与用户痛点，再决定做什么，以及如何衡量产品价值。',
                  ],
                ].map(([Icon, title, text]) => {
                  const ItemIcon = Icon as typeof Wrench;
                  return (
                    <article data-motion-card className="surface rounded-2xl p-6" key={String(title)}>
                      <ItemIcon className="mb-8 text-accent" size={25} />
                      <h3 className="font-bold">{String(title)}</h3>
                      <p className="mt-2 text-sm leading-7 text-slate-600 dark:text-slate-300">
                        {String(text)}
                      </p>
                    </article>
                  );
                })}
              </div>
            </div>
          </Reveal>
          <Reveal className="mt-12 grid gap-4 md:grid-cols-2">
            <div data-motion-card className="surface rounded-2xl p-6">
              <p className="text-sm font-bold text-accent">{en ? 'What I Focus On' : '我关注的问题'}</p>
              <p className="mt-3 leading-8 text-slate-600 dark:text-slate-300">{siteData.about.focus}</p>
            </div>
            <div data-motion-card className="surface rounded-2xl p-6">
              <p className="text-sm font-bold text-accent">
                {en ? 'What I Hope to Solve' : '我希望解决的问题'}
              </p>
              <p className="mt-3 leading-8 text-slate-600 dark:text-slate-300">{siteData.about.purpose}</p>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="projects" className="section-pad scroll-mt-16" data-motion-section>
        <div className="container-site">
          <Reveal className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
            <div>
              <p className="eyebrow">02 / PROJECTS</p>
              <h2 className="title-xl">{en ? 'Featured Projects' : '精选项目'}</h2>
              <p className="mt-4 max-w-xl text-slate-600 dark:text-slate-300">
                {en
                  ? 'From visual perception to embedded control, learning complete systems through real integration.'
                  : '从视觉感知到嵌入式控制，在一次次联调中理解完整系统。'}
              </p>
            </div>
            <Link className="button-secondary" to="/projects">
              {en ? 'View All' : '查看全部'} <ArrowRight size={17} />
            </Link>
          </Reveal>
          <div className="mt-10 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {projects
              .filter((p) => p.featured)
              .map((project) => (
                <Reveal key={project.id}>
                  <ProjectCard project={project} />
                </Reveal>
              ))}
          </div>
        </div>
      </section>

      <section
        id="experience"
        className="section-pad scroll-mt-16 bg-slate-100/60 dark:bg-slate-900/35"
        data-motion-section
      >
        <div className="container-site">
          <Reveal>
            <p className="eyebrow">03 / EXPERIENCE</p>
            <h2 className="title-xl">{en ? 'Education & Experience' : '学习与经历'}</h2>
          </Reveal>
          <div className="timeline-line relative mt-10 space-y-8 pl-10">
            {experiences.map((item) => (
              <Reveal key={item.organization}>
                <div>
                  <article data-motion-card className="relative surface rounded-2xl p-6">
                    <span className="absolute -left-[2.12rem] top-7 h-3.5 w-3.5 rounded-full border-[3px] border-[rgb(var(--page))] bg-accent ring-1 ring-accent" />
                    <p className="text-xs font-bold tracking-wider text-accent">{item.period}</p>
                    <div className="mt-2 flex flex-wrap items-baseline gap-x-3">
                      <h3 className="text-xl font-bold">{item.organization}</h3>
                      <span className="text-sm text-slate-500">{item.role}</span>
                    </div>
                    <p className="mt-4 text-sm leading-7 text-slate-600 dark:text-slate-300">{item.work}</p>
                    <p className="mt-2 text-sm">
                      <span className="font-semibold">{en ? 'What I learned: ' : '获得的成长：'}</span>
                      {item.growth}
                    </p>
                  </article>
                  {item.id === 'bashu' && (
                    <div className="mt-6">
                      <CampusGallery
                        photos={bashuPhotos}
                        eyebrow="BASHU / 2021—2024"
                        title={en ? 'Three Years That Shaped My Foundation' : '一段塑造底色的青春'}
                        description={
                          en
                            ? 'Classroom learning, class activities, friends, teachers, and family shaped how I approach goals and value the people who move forward with me.'
                            : '从课堂学习到班级活动，从并肩前行的同窗到始终支持我的家人，巴蜀中学的三年让我懂得如何认真对待目标，也学会珍惜同行的人。这段经历构成了我继续探索世界的起点。'
                        }
                        ariaLabel={en ? 'Bashu Secondary School experience photos' : '巴蜀中学高中经历照片'}
                      />
                    </div>
                  )}
                  {item.id === 'mingyue' && (
                    <div className="mt-6">
                      <CampusGallery
                        photos={mingyuePhotos}
                        eyebrow="MINGYUE / ENGINEERING"
                        title={en ? 'Learning Engineering Through Real Problems' : '在真实问题中学习工程'}
                        description={
                          en
                            ? 'The Mingyue Innovation Program is an interdisciplinary, inquiry-based, project-driven engineering program. Here I study Robotics Engineering and learn the complete path from research and prototyping to testing, iteration, and real-world application.'
                            : '重庆大学国家卓越工程师学院是全国首批国家卓越工程师学院建设试点单位之一。明月科创实验班创设于 2020 年，是学校新工科教育改革的“实验田”，以学科交叉、探究式教学和项目驱动为特色，引导学生从真实需求出发，经历研究、原型、测试与迭代。我在这里学习机器人工程，并通过课程、竞赛、科创训练、产业参访与国际交流理解技术走向真实应用的完整过程。'
                        }
                        ariaLabel={
                          en ? 'Mingyue Innovation Program photos' : '重庆大学明月科创实验班经历照片'
                        }
                      />
                    </div>
                  )}
                  {item.id === 'gsing' && (
                    <div className="mt-6">
                      <CampusGallery
                        photos={roboconPhotos}
                        eyebrow="ROBOCON / RCER"
                        title={en ? 'Let the Competition Field Test Every Idea' : '把想法交给赛场检验'}
                        description={
                          en
                            ? 'Vision is not only about helping a robot see; perception must work reliably with real hardware, complex scenes, and strict time limits. Repeated integration and field tests turn algorithms into engineering capability.'
                            : '视觉不仅是让机器人“看见”，更要让感知结果在复杂环境、有限时间和真实硬件上稳定工作。作为视觉组成员，我在一次次调试、联调与复盘中，将算法思路转化为能够服务整机决策的工程能力。'
                        }
                        ariaLabel={en ? 'GSing ROBOCON Team photos' : 'GSing战队经历照片'}
                      />
                    </div>
                  )}
                  {item.id === 'art' && (
                    <div className="mt-6">
                      <CampusGallery
                        photos={campusPhotos}
                        eyebrow="ART & ENSEMBLE"
                        title={en ? 'Music Taught Me More Than Performance' : '音乐教会我的，不只是演奏'}
                        description={
                          en
                            ? 'From section balance to full-ensemble coordination, every rehearsal and performance requires focus, listening, and trust—qualities that also shape my engineering teamwork.'
                            : '从声部配合到整团协作，从排练细节到舞台执行，每一次合奏都需要专注、倾听与信任。这些体验也延伸到我的工程实践和团队工作中。'
                        }
                        ariaLabel={en ? 'Student Art Troupe photos' : '重庆大学学生艺术团照片'}
                      />
                    </div>
                  )}
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="honors" className="section-pad scroll-mt-16" data-motion-section>
        <div className="container-site">
          <Reveal className="flex flex-col justify-between gap-6 border-b border-slate-200 pb-9 dark:border-slate-800 md:flex-row md:items-end">
            <div>
              <p className="eyebrow">04 / HONORS</p>
              <h2 className="title-xl">{en ? 'Honors & Achievements' : '荣誉与成果'}</h2>
              <p className="mt-4 max-w-2xl leading-8 text-slate-600 dark:text-slate-300">
                {en
                  ? 'A chronological record of competition, research, innovation, arts, and personal growth. Select any item to view its certificate.'
                  : '从竞赛赛场、科创项目到艺术实践与综合成长，这里按时间记录每一次认真投入后留下的成果。点击任意条目可查看真实证书。'}
              </p>
            </div>
            <div className="flex items-baseline gap-2 text-slate-500">
              <span className="text-5xl font-black tracking-tight text-accent">{filteredHonors.length}</span>
              <span className="text-sm">{en ? 'shown' : '项显示'}</span>
            </div>
          </Reveal>
          <Reveal>
            <div
              className="mt-7 flex gap-2 overflow-x-auto rounded-2xl border border-[rgb(var(--line))] bg-[rgb(var(--surface))]/75 p-2 shadow-sm backdrop-blur md:inline-flex md:max-w-full"
              aria-label={en ? 'Filter honors' : '筛选荣誉'}
            >
              {honorFilterOptions.map((option) => {
                const count = honors.filter((honor) => matchesHonorFilter(honor, option.id)).length;
                const active = honorFilter === option.id;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setHonorFilter(option.id)}
                    aria-pressed={active}
                    className={`shrink-0 rounded-xl px-4 py-2 text-sm font-bold transition ${
                      active
                        ? 'bg-accent text-white shadow-lg shadow-blue-600/20'
                        : 'text-slate-500 hover:bg-blue-50 hover:text-accent dark:text-slate-300 dark:hover:bg-slate-800'
                    }`}
                  >
                    {option.label}
                    <span className={`ml-2 font-mono text-xs ${active ? 'text-blue-100' : 'text-slate-400'}`}>
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </Reveal>
          <div className="mt-12 space-y-16">
            {honorYears.map((year) => {
              const yearHonors = filteredHonors.filter((honor) => honor.year.startsWith(year));
              return (
                <section
                  key={year}
                  aria-labelledby={`honor-year-${year}`}
                  className="grid gap-6 md:grid-cols-[130px_1fr] md:gap-10"
                >
                  <Reveal>
                    <div className="md:sticky md:top-24">
                      <p id={`honor-year-${year}`} className="text-4xl font-black tracking-[-.05em]">
                        {year}
                      </p>
                      <p className="mt-2 text-sm text-slate-500">
                        {yearHonors.length} {en ? 'achievements' : '项成果'}
                      </p>
                      <div className="mt-5 hidden h-px w-16 bg-accent md:block" />
                    </div>
                  </Reveal>
                  <div className="grid gap-5 lg:grid-cols-2">
                    {yearHonors.map((honor, index) => (
                      <Reveal key={`${honor.year}-${honor.title}-${honor.level}`}>
                        <button
                          onClick={() => setSelectedHonor(honor)}
                          className="surface group grid h-full w-full overflow-hidden rounded-2xl text-left transition duration-300 hover:-translate-y-1 hover:border-blue-300 hover:shadow-xl hover:shadow-blue-950/5 sm:grid-cols-[180px_1fr]"
                        >
                          <div className="relative min-h-44 overflow-hidden bg-slate-100 dark:bg-slate-900">
                            <img
                              src={honor.image}
                              alt={
                                en
                                  ? `${honor.title} ${honor.level} certificate`
                                  : `${honor.title}${honor.level}证书`
                              }
                              loading="lazy"
                              className="absolute inset-0 h-full w-full object-cover transition duration-500 group-hover:scale-[1.04]"
                            />
                            <div className="absolute inset-0 bg-gradient-to-t from-slate-950/30 to-transparent" />
                            <span className="absolute bottom-3 left-3 font-mono text-xs font-bold text-white">
                              {String(index + 1).padStart(2, '0')}
                            </span>
                          </div>
                          <div className="flex min-w-0 flex-col p-5 sm:p-6">
                            <div className="flex items-center justify-between gap-4">
                              <span className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-accent dark:bg-blue-400/10">
                                {honor.category}
                              </span>
                              <time className="font-mono text-xs text-slate-500">{honor.year}</time>
                            </div>
                            <h3 className="mt-5 text-lg font-bold leading-7">{honor.title}</h3>
                            <p className="mt-1 font-semibold text-accent">{honor.level}</p>
                            <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                              {honor.description}
                            </p>
                            <span className="mt-auto pt-5 text-xs font-semibold text-slate-400 transition group-hover:text-accent">
                              {en ? 'View certificate →' : '查看证书 →'}
                            </span>
                          </div>
                        </button>
                      </Reveal>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
          <LifeGallery />
        </div>
      </section>

      <section id="contact" className="section-pad scroll-mt-16" data-motion-section>
        <div className="container-site">
          <Reveal className="surface overflow-hidden rounded-3xl bg-gradient-to-br from-blue-700 to-violet-700 p-8 text-white sm:p-12 lg:p-16">
            <div>
              <div>
                <p className="mb-3 text-xs font-bold uppercase tracking-[.22em] text-blue-100">
                  05 / CONTACT
                </p>
                <h2 className="text-4xl font-bold tracking-tight sm:text-5xl">
                  {en ? 'Let’s exchange ideas,' : '一起交流想法，'}
                  <br />
                  {en ? 'or build something interesting.' : '或者做点有意思的事。'}
                </h2>
                <p className="mt-5 max-w-xl leading-8 text-blue-100">
                  {en
                    ? 'If you are interested in robotics, embedded systems, intelligent hardware, or product exploration, feel free to get in touch.'
                    : '如果你也关注机器人、嵌入式、智能硬件或产品探索，欢迎联系我。'}
                </p>
                <div className="mt-8 flex flex-wrap gap-3">
                  <a
                    href={qqMailUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="button-secondary !border-white/20 !bg-white !text-blue-800"
                  >
                    <Mail size={17} />
                    {en ? 'Send Email' : '发送邮件'}
                  </a>
                  <button
                    onClick={copyEmail}
                    className="button-secondary !border-white/30 !bg-white/10 !text-white"
                  >
                    <Clipboard size={17} />
                    {en ? 'Copy Email' : '复制邮箱'}
                  </button>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>
      <MessagesPage embedded />
      <HonorModal honor={selectedHonor} onClose={() => setSelectedHonor(null)} />
    </div>
  );
}

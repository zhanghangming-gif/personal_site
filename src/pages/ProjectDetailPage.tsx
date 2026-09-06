import { ArrowLeft, ChevronRight, Github, MonitorPlay } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { CampusGallery } from '../components/CampusGallery';
import { ProjectVisual } from '../components/ProjectVisual';
import { useToast } from '../components/Toast';
import { useContent } from '../context/ContentContext';
import { useLanguage } from '../context/LanguageContext';

export default function ProjectDetailPage() {
  const { projects } = useContent();
  const { projectId } = useParams();
  const project = projects.find((item) => item.id === projectId);
  const toast = useToast();
  const { language } = useLanguage();
  const en = language === 'en';
  if (!project)
    return (
      <div className="container-site grid min-h-[80vh] place-items-center pt-20 text-center">
        <div>
          <h1 className="text-3xl font-bold">{en ? 'Project not found' : '项目不存在'}</h1>
          <Link className="button-primary mt-6" to="/projects">
            <ArrowLeft size={17} />
            {en ? 'Back to projects' : '返回项目列表'}
          </Link>
        </div>
      </div>
    );
  return (
    <article className="pb-24 pt-28">
      <div className="container-site">
        <Link
          className="mb-8 inline-flex items-center gap-2 text-sm font-semibold text-accent"
          to="/projects"
        >
          <ArrowLeft size={17} />
          {en ? 'Back to projects' : '返回项目列表'}
        </Link>
        <div className="grid items-center gap-10 lg:grid-cols-[1.05fr_.95fr]">
          <div>
            <div className="flex flex-wrap gap-2">
              <span className="tag">{project.type}</span>
              <span className="tag">{project.status}</span>
            </div>
            <h1 className="mt-5 text-4xl font-black leading-tight tracking-[-.04em] sm:text-5xl">
              {project.title}
            </h1>
            <p className="mt-6 text-lg leading-8 text-slate-600 dark:text-slate-300">{project.summary}</p>
            <p className="mt-5 text-sm">
              <span className="font-bold">{en ? 'My role: ' : '我的职责：'}</span>
              {project.role}
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <button
                className="button-secondary"
                onClick={() => toast(project.github ? (en ? 'Opening GitHub' : '正在打开 GitHub') : (en ? 'Source code is not public yet' : '项目代码暂未公开'))}
              >
                <Github size={17} />
                {project.github ? 'GitHub' : en ? 'Private repository' : '代码暂未公开'}
              </button>
              <button
                className="button-secondary"
                onClick={() => toast(project.demo ? (en ? 'Opening demo' : '正在打开演示') : (en ? 'Online demo is not available yet' : '在线演示暂未公开'))}
              >
                <MonitorPlay size={17} />
                {project.demo ? (en ? 'Online demo' : '在线演示') : (en ? 'Demo unavailable' : '演示暂未公开')}
              </button>
            </div>
          </div>
          <ProjectVisual title={project.title} image={project.cover} imageContain={project.coverContain} />
        </div>
        <div className="mt-16 grid gap-5 md:grid-cols-2">
          <Detail title={en ? 'Background' : '项目背景'} text={project.background} />
          <Detail title={en ? 'Goal' : '项目目标'} text={project.goal} />
          <Detail title={en ? 'Technical approach' : '技术方案'} text={project.solution} />
          <Detail title={en ? 'Challenges' : '遇到的问题'} text={project.challenge} />
          <Detail title={en ? 'Solution' : '解决方案'} text={project.solution} />
          <Detail title={en ? 'Outcome' : '项目成果'} text={project.result} />
        </div>
        <section className="mt-16">
          <p className="eyebrow">SYSTEM ARCHITECTURE</p>
          <h2 className="text-3xl font-bold">{en ? 'System architecture' : '系统架构'}</h2>
          <div className="surface mt-7 flex flex-col items-stretch justify-center gap-3 rounded-2xl p-6 md:flex-row md:items-center">
            {project.architecture.map((item, index) => (
              <div className="contents" key={item}>
                <div className="rounded-xl border bg-blue-50/60 px-4 py-5 text-center text-sm font-semibold dark:bg-blue-400/5">
                  {item}
                </div>
                {index < project.architecture.length - 1 && (
                  <ChevronRight className="mx-auto rotate-90 text-slate-400 md:rotate-0" size={19} />
                )}
              </div>
            ))}
          </div>
        </section>
        <section className="mt-16">
          <p className="eyebrow">WORKFLOW</p>
          <h2 className="text-3xl font-bold">{en ? 'Workflow' : '工作流程'}</h2>
          <ol className="mt-7 grid gap-4 md:grid-cols-5">
            {project.workflow.map((item, index) => (
              <li className="surface rounded-2xl p-5" key={item}>
                <span className="text-xs font-black text-accent">0{index + 1}</span>
                <p className="mt-5 font-semibold">{item}</p>
              </li>
            ))}
          </ol>
        </section>
        {project.photos?.length ? (
          <section className="mt-16">
            <CampusGallery
              photos={project.photos}
              eyebrow="PROJECT GALLERY"
              title={project.galleryTitle ?? (en ? 'Project process and validation' : '项目过程与验证')}
              description={project.galleryDescription ?? (en ? 'Key moments from design and implementation to on-site validation.' : '记录项目从方案设计、系统实现到现场验证的关键过程。')}
              ariaLabel={en ? `${project.title} project gallery` : `${project.title}项目图片`}
              swipeLabel={en ? 'Swipe to browse project images' : '左右滑动查看项目图片'}
            />
          </section>
        ) : null}
        {project.videos?.length ? (
          <section className="mt-16">
            <p className="eyebrow">DEMO VIDEOS</p>
            <h2 className="text-3xl font-bold">{en ? 'System demos and real-world validation' : '系统演示与实机验证'}</h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600 dark:text-slate-300">
              {project.galleryDescription ??
                (en ? 'Videos document key milestones from implementation to real-world validation.' : '视频记录项目从系统实现到实机验证的关键过程，可直接在线播放并全屏查看。')}
            </p>
            <div className="mt-7 grid gap-5 lg:grid-cols-2">
              {project.videos.map((video) => (
                <article className="surface overflow-hidden rounded-2xl" key={video.src}>
                  <video
                    className="aspect-video w-full bg-black object-contain"
                    controls
                    playsInline
                    preload="metadata"
                    poster={video.poster}
                  >
                    <source src={video.src} type="video/mp4" />
                    {en ? 'Your browser does not support HTML5 video.' : '您的浏览器暂不支持 HTML5 视频播放。'}
                  </video>
                  <div className="p-5">
                    <h3 className="font-bold">{video.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                      {video.caption}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}
        <section className="mt-14">
          <h2 className="text-xl font-bold">{en ? 'Technologies' : '使用技术'}</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {project.tech.map((item) => (
              <span className="tag" key={item}>
                {item}
              </span>
            ))}
          </div>
        </section>
      </div>
    </article>
  );
}

function Detail({ title, text }: { title: string; text: string }) {
  return (
    <section className="surface rounded-2xl p-6">
      <h2 className="text-lg font-bold">{title}</h2>
      <p className="mt-3 text-sm leading-7 text-slate-600 dark:text-slate-300">{text}</p>
    </section>
  );
}

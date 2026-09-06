import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useLayoutEffect, type RefObject } from 'react';

gsap.registerPlugin(ScrollTrigger);

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function isInsideNestedSection(section: HTMLElement, item: HTMLElement) {
  const owner = item.closest<HTMLElement>('[data-motion-section]');
  return Boolean(owner && owner !== section);
}

export function usePortfolioMotion(rootRef: RefObject<HTMLElement>, refreshKey = '') {
  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const motionTargets = root.querySelectorAll(
      '[data-motion-reveal], [data-motion-heading], [data-motion-image]',
    );
    if (prefersReducedMotion()) {
      gsap.set(motionTargets, { clearProps: 'all' });
      return;
    }

    const ctx = gsap.context(() => {
      const sections = gsap.utils.toArray<HTMLElement>('[data-motion-section]', root);

      sections.forEach((section) => {
        const headings = gsap.utils
          .toArray<HTMLElement>(section.querySelectorAll('[data-motion-heading], .title-xl'))
          .filter((item) => !isInsideNestedSection(section, item));
        const candidates = gsap.utils
          .toArray<HTMLElement>(section.querySelectorAll('[data-motion-card], [data-motion-reveal]'))
          .filter((item) => !isInsideNestedSection(section, item));
        const reveals = candidates.filter((item) => {
          if (headings.some((heading) => item === heading || item.contains(heading))) return false;
          return !candidates.some(
            (other) => other !== item && item.contains(other) && item.hasAttribute('data-motion-reveal'),
          );
        });

        gsap.set(headings, { autoAlpha: 0, y: 18 });
        gsap.set(reveals, { autoAlpha: 0, y: 24 });

        const tl = gsap.timeline({
          defaults: { ease: 'power2.out' },
          scrollTrigger: {
            trigger: section,
            start: 'top 84%',
            once: true,
          },
        });

        if (headings.length) {
          tl.to(headings, { autoAlpha: 1, y: 0, duration: 0.48, stagger: 0.035 });
        }
        if (reveals.length) {
          tl.to(
            reveals,
            { autoAlpha: 1, y: 0, duration: 0.52, stagger: 0.045 },
            headings.length ? '-=0.28' : 0,
          );
        }
      });

      gsap.utils.toArray<HTMLElement>('[data-motion-image]', root).forEach((frame) => {
        const image = frame.querySelector('img');
        gsap.set(frame, { autoAlpha: 0 });
        if (image) gsap.set(image, { scale: 1.025, transformOrigin: '50% 50%' });

        const imageReveal = gsap.timeline({
          defaults: { ease: 'power2.out' },
          scrollTrigger: {
            trigger: frame,
            start: 'top 88%',
            once: true,
          },
        });
        imageReveal.to(frame, { autoAlpha: 1, duration: 0.42 });
        if (image) imageReveal.to(image, { scale: 1, duration: 0.55 }, '<');
      });
    }, root);

    return () => ctx.revert();
  }, [rootRef, refreshKey]);
}

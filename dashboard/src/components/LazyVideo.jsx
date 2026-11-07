import React, { useEffect, useRef, useState } from 'react';
import { Film } from 'lucide-react';

/**
 * Mounts the <video> only once its card is near the viewport. A grid of kept
 * clips or animations otherwise fires a metadata fetch and a decode per clip
 * the moment the page renders, which is what made the jobs page lag.
 */
export default function LazyVideo({ src, boxClass = 'w-full h-full', videoClass = 'w-full h-full object-contain' }) {
  const box = useRef(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const node = box.current;
    if (!node || seen) return undefined;
    if (!('IntersectionObserver' in window)) {
      setSeen(true);
      return undefined;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setSeen(true);
          obs.disconnect();
        }
      },
      { rootMargin: '240px' },
    );
    obs.observe(node);
    return () => obs.disconnect();
  }, [seen]);

  return (
    <div ref={box} className={boxClass}>
      {seen ? (
        <video key={src} src={src} controls playsInline preload="metadata" className={videoClass} />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-muted/60">
          <Film size={28} />
        </div>
      )}
    </div>
  );
}

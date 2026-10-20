import React, { useEffect, useState } from 'react';
import { Check, Copy, Download, Loader2 } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

function fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function fmtWhen(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

// The download name a phone or desktop saves: the clip's title when OpenShorts wrote one.
function fileName(stick, suffix = '') {
  const base = (stick.social?.title || stick.name).replace(/[^\w\- ]+/g, '').trim().slice(0, 80) || 'animated';
  return `${base}${suffix ? ` (${suffix})` : ''}.mp4`;
}

function CopyText({ label, text }) {
  const [done, setDone] = useState(false);
  if (!text) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      // Plain http on a LAN has no clipboard API; fall back to a hidden textarea.
      const area = document.createElement('textarea');
      area.value = text; document.body.appendChild(area); area.select();
      try { document.execCommand('copy'); } catch (__) { /* ignore */ }
      area.remove();
    }
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <button
      type="button"
      onClick={copy}
      title={text}
      className="w-full text-left rounded-lg border border-white/10 hover:border-brass/60 px-3 py-2 transition-colors"
    >
      <span className="flex items-center justify-between gap-2">
        <span className="font-mono text-micro uppercase text-muted">{label}</span>
        {done ? <Check size={13} className="text-ok" /> : <Copy size={13} className="text-muted" />}
      </span>
      <span className="block text-xs text-ink mt-1 line-clamp-2 break-words">{text}</span>
    </button>
  );
}

function NowBar({ now }) {
  if (!now) {
    return <p className="readout mb-6">idle · new kept clips are picked up within 5 minutes</p>;
  }
  const pct = now.total ? Math.round((100 * (now.done || 0)) / now.total) : 0;
  return (
    <div className="card p-4 mb-6">
      <div className="flex items-center gap-2 text-sm text-ink">
        <Loader2 size={14} className="animate-spin text-brass" />
        <span className="lowercase">{now.phase || 'working'} · {now.label}</span>
        <span className="readout ml-auto">{now.total ? `${now.done}/${now.total} · ${pct}%` : ''}</span>
      </div>
      <p className="readout mt-1 truncate" title={now.episode}>{now.episode}</p>
      {now.total ? (
        <div className="h-1 rounded-full bg-white/10 mt-3 overflow-hidden">
          <div className="h-full bg-brass transition-all" style={{ width: `${pct}%` }} />
        </div>
      ) : null}
    </div>
  );
}

// One clip: the storyboarded version (when it exists) and the posed version that follows the footage.
function StickCard({ stick }) {
  const [view, setView] = useState(stick.story_url ? 'story' : 'posed');
  const story = view === 'story' && stick.story_url;
  const url = getApiUrl(story ? stick.story_url : stick.url);
  const bytes = story ? stick.story_bytes : stick.bytes;
  return (
    <div className="card overflow-hidden flex flex-col">
      <div className="relative aspect-[9/16] bg-black">
        <video key={url} src={url} controls playsInline preload="metadata" className="w-full h-full object-contain" />
        {!story && stick.status === 'fallback' && (
          <span
            className="pointer-events-none absolute top-2 left-2 bg-black/70 font-mono text-micro uppercase px-2 py-1 rounded-full text-brass"
            title="The local model was busy, so poses came from the tracker alone"
          >
            needs a look
          </span>
        )}
      </div>
      <div className="p-4 flex flex-col gap-3 flex-1">
        {stick.story_url && (
          <div className="flex rounded-lg border border-white/10 overflow-hidden text-xs font-mono uppercase">
            {[['story', 'story', 'The model rewrote the clip as an acted-out story'], ['posed', 'posed', 'Follows the real footage']].map(([id, label, tip]) => (
              <button
                key={id}
                type="button"
                title={tip}
                onClick={() => setView(id)}
                className={`flex-1 py-1.5 transition-colors ${view === id ? 'bg-brass/20 text-ink' : 'text-muted hover:text-ink'}`}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        <div>
          <p className="text-sm text-ink font-medium">{stick.social?.title || stick.label}</p>
          <p className="readout mt-0.5 truncate" title={stick.episode}>{stick.label} · {stick.episode}</p>
          <p className="readout mt-0.5">
            {fmtSize(bytes)}{stick.finished_at ? ` · ${fmtWhen(stick.finished_at)}` : ''}
          </p>
        </div>
        <a href={url} download={fileName(stick, story ? 'story' : '')} className="btn-primary inline-flex items-center justify-center gap-2">
          <Download size={15} /> download mp4
        </a>
        <div className="flex flex-col gap-2">
          <CopyText label="title" text={stick.social?.title} />
          <CopyText label="tiktok" text={stick.social?.tiktok} />
          <CopyText label="instagram" text={stick.social?.instagram} />
        </div>
      </div>
    </div>
  );
}

export default function AnimatedTab() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = () => apiJson('/api/sticks')
      .then((body) => { if (!cancelled) { setData(body); setError(''); } })
      .catch(() => { if (!cancelled) setError('Could not load animations.'); });
    load();
    const timer = setInterval(load, 15000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  const sticks = data?.sticks || [];
  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-8 py-8">
      <h1 className="font-display lowercase text-2xl text-ink mb-1">animated</h1>
      <p className="text-muted text-sm mb-6 lowercase">
        Stick-figure versions of your kept clips, newest first, with the clip&apos;s audio and captions. Story: the model
        rewrites the clip as an acted-out cartoon. Posed: the figures follow the real footage. Download, copy the text, post.
      </p>
      {error && <p className="text-danger text-sm mb-4">{error}</p>}
      {data && !data.enabled && (
        <p className="text-muted text-sm lowercase">The animator is not connected (STICKS_ROOT is unset).</p>
      )}
      {data?.enabled && <NowBar now={data.now} />}
      {data?.enabled && sticks.length === 0 && (
        <p className="text-muted text-sm lowercase">No animations yet. The first one appears here when it finishes.</p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {sticks.map((stick) => <StickCard key={stick.url} stick={stick} />)}
      </div>
    </div>
  );
}

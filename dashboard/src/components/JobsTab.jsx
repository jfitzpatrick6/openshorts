import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Film, FolderOpen, Loader2 } from 'lucide-react';
import { apiJson } from '../lib/api';
import { getApiUrl } from '../config';

const WORKING = new Set(['processing', 'queued']);

function fmtWhen(epoch) {
  if (!epoch) return '';
  return new Date(epoch * 1000).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

function fmtSize(bytes) {
  if (!bytes) return '';
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function statusBadge(status) {
  if (status === 'processing' || status === 'queued') return 'badge-brass';
  if (status === 'failed') return 'badge-danger';
  if (status === 'completed') return 'badge-ok';
  return 'badge-warn';
}

function scoreTone(score) {
  if (score >= 80) return 'text-ok';
  if (score >= 65) return 'text-brass';
  return 'text-ink2';
}

function oneScore(raw) {
  if (raw === null || raw === undefined || raw === '') return null;
  const score = Number(raw);
  return Number.isFinite(score) ? Math.round(score) : null;
}

function fileName(url) {
  if (!url) return '';
  const path = String(url).split('?')[0];
  const base = path.split('/').pop() || '';
  try {
    return decodeURIComponent(base);
  } catch {
    return base;
  }
}

// Kept files are the rendered mp4s, so the score belongs to that filename.
// The 16:9 twin shares the vertical clip's score.
function scoresByFilename(clips) {
  const map = {};
  if (!Array.isArray(clips)) return map;
  for (const clip of clips) {
    const score = oneScore(clip?.predicted_score);
    if (!Number.isFinite(score)) continue;
    for (const key of ['video_url', 'landscape_url']) {
      const name = fileName(clip?.[key]);
      if (name) map[name] = score;
    }
  }
  return map;
}

export default function JobsTab({ onOpenJob }) {
  const [jobs, setJobs] = useState(null);
  const [kept, setKept] = useState(null);
  const [error, setError] = useState('');
  const [opening, setOpening] = useState('');
  // filename -> score, filled once per finished job. A poll must not refetch.
  const scoreCache = useRef({});
  const [scoreTick, setScoreTick] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      Promise.all([apiJson('/api/jobs'), apiJson('/api/retained')])
        .then(([jobBody, keptBody]) => {
          if (cancelled) return;
          setJobs(jobBody.jobs || []);
          setKept(keptBody);
          setError('');
        })
        .catch(() => {
          if (!cancelled) setError('Could not load jobs.');
        });
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      cancelled = true;
      mounted.current = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!jobs) return;
    for (const job of jobs) {
      if (!job.clip_count || WORKING.has(job.status)) continue;
      if (scoreCache.current[job.job_id]) continue;
      scoreCache.current[job.job_id] = 'loading';
      apiJson(`/api/status/${job.job_id}`)
        .then((body) => {
          scoreCache.current[job.job_id] = scoresByFilename(body?.result?.clips);
        })
        .catch(() => {
          scoreCache.current[job.job_id] = [];
        })
        .finally(() => {
          if (mounted.current) setScoreTick((tick) => tick + 1);
        });
    }
  }, [jobs]);

  const open = async (jobId) => {
    if (!onOpenJob || opening) return;
    setOpening(jobId);
    try {
      await onOpenJob(jobId);
    } catch {
      setError('Could not open that job.');
      setOpening('');
    }
  };

  const rows = jobs || [];
  const working = rows.filter((job) => WORKING.has(job.status));
  const finished = rows.filter((job) => !WORKING.has(job.status));
  const episodes = kept?.episodes || [];

  // scoreTick changes when a fill-in lands in scoreCache. The cache itself
  // is a ref, so the memo would otherwise keep an empty map.
  const scoreByFile = useMemo(() => {
    const map = new Map();
    for (const job of rows) {
      const cached = scoreCache.current[job.job_id];
      if (!cached || cached === 'loading') continue;
      for (const [name, score] of Object.entries(cached)) map.set(name, score);
    }
    return map;
  }, [rows, scoreTick]);

  if (jobs === null && kept === null && !error) {
    return <div className="flex justify-center py-20"><Loader2 className="animate-spin text-brass" /></div>;
  }

  return (
    <div className="h-full overflow-y-auto p-4 sm:p-8 max-w-5xl mx-auto animate-fade">
      <p className="eyebrow mb-1.5">02 · JOBS</p>
      <h1 className="font-display lowercase text-2xl text-ink mb-2">working and kept</h1>
      <p className="text-muted text-sm mb-8 lowercase">
        Jobs started from this page or by the clip loop. Finished files on the server
        stay with the job for about 7 days. Copies in the kept library stay for {kept?.days || 30} days.
      </p>
      {error && <p className="text-danger text-sm mb-4">{error}</p>}

      <section className="mb-10">
        <h2 className="font-display lowercase text-lg text-ink mb-3">working now</h2>
        {working.length === 0 && (
          <p className="text-muted text-sm lowercase">Nothing is clipping right now.</p>
        )}
        <div className="space-y-3">
          {working.map((job) => (
            <JobRow key={job.job_id} job={job} opening={opening} onOpen={open} />
          ))}
        </div>
      </section>

      <section className="mb-10">
        <h2 className="font-display lowercase text-lg text-ink mb-3">finished on this server</h2>
        {finished.length === 0 && (
          <p className="text-muted text-sm lowercase">No finished job is still on disk.</p>
        )}
        <div className="space-y-3">
          {finished.map((job) => (
            <JobRow key={job.job_id} job={job} opening={opening} onOpen={open} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="font-display lowercase text-lg text-ink mb-3">kept clips</h2>
        {kept && !kept.enabled && (
          <p className="text-muted text-sm lowercase">
            The kept library is not connected on this server.
          </p>
        )}
        {kept?.enabled && episodes.length === 0 && (
          <div className="text-center py-12 text-muted">
            <Film size={36} className="mx-auto mb-3" />
            <p className="lowercase">No kept clips yet.</p>
          </div>
        )}
        <div className="space-y-10">
          {episodes.map((episode) => (
            <div key={episode.name}>
              <div className="mb-4 pb-2 border-b border-rule">
                <p className="text-sm text-ink font-medium">{episode.name}</p>
                <p className="readout mt-0.5">
                  {fmtWhen(episode.updated_at)} · {episode.clips.length} clip{episode.clips.length === 1 ? '' : 's'}
                </p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
                {episode.clips.map((clip) => {
                  const score = scoreByFile.get(clip.name);
                  return (
                    <div key={clip.url} className="card overflow-hidden">
                      <div className={`relative ${clip.shape === '16:9' ? 'aspect-video' : 'aspect-[9/16]'} bg-black`}>
                        <video
                          src={getApiUrl(clip.url)}
                          controls
                          preload="metadata"
                          className="w-full h-full object-contain"
                        />
                        {Number.isFinite(score) && (
                          <span
                            className="pointer-events-none absolute top-2 left-2 bg-black/70 font-mono text-micro uppercase px-2 py-1 rounded-full"
                            title="Virality score, from 0 to 100"
                          >
                            <span className="text-white/70">viral </span>
                            <b className={scoreTone(score)}>{score}</b>
                          </span>
                        )}
                      </div>
                      <div className="p-3">
                        <p className="text-sm text-ink font-medium lowercase flex flex-wrap items-baseline gap-x-2">
                          <span>{clip.label}</span>
                          {Number.isFinite(score) && (
                            <span className={`font-mono normal-case ${scoreTone(score)}`} title="Virality score, from 0 to 100">
                              viral {score}
                            </span>
                          )}
                        </p>
                        <p className="readout mt-0.5">
                          {fmtSize(clip.bytes)}
                          {typeof clip.days_left === 'number' ? ` · ${clip.days_left}d left` : ''}
                        </p>
                        <a href={getApiUrl(clip.url)} download className="text-micro font-mono uppercase text-brass hover:text-ink mt-2 inline-block">
                          download
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function JobRow({ job, opening, onOpen }) {
  return (
    <div className="card p-4 flex flex-wrap items-center justify-between gap-3">
      <div className="min-w-0">
        <p className="text-sm text-ink font-medium truncate" title={job.title}>{job.title}</p>
        <p className="readout mt-1 flex flex-wrap items-center gap-2">
          <span className={`${statusBadge(job.status)} px-1.5 py-0.5 rounded-full`}>{job.status}</span>
          <span>{job.clip_count} clip{job.clip_count === 1 ? '' : 's'}</span>
          {job.updated_at ? <span>{fmtWhen(job.updated_at)}</span> : null}
        </p>
        {job.log && <p className="text-muted text-xs mt-1 line-clamp-2">{job.log}</p>}
      </div>
      <button
        type="button"
        onClick={() => onOpen(job.job_id)}
        disabled={!!opening}
        className="btn-ghost px-3 py-2 text-xs shrink-0"
      >
        {opening === job.job_id
          ? <><Loader2 size={14} className="animate-spin" /> opening…</>
          : <><FolderOpen size={14} /> open</>}
      </button>
    </div>
  );
}

// frontend/src/components/InsightsPanel.tsx
import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

type Status = 'idle' | 'loading' | 'done' | 'error';

const CACHE_KEY = 'insights_cache';
const CACHE_DURATION_MS = 60 * 60 * 1000; // 1 hour

type CachedData = {
  text: string;
  timestamp: number;
};

export default function InsightsPanel() {
  const [text, setText] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const ran = useRef(false);
  const navigate = useNavigate();

  const fetchInsights = useCallback(async (force = false) => {
    // 1. Check for valid cache unless forcing
    if (!force) {
      try {
        const cached = sessionStorage.getItem(CACHE_KEY);
        if (cached) {
          const { text: cachedText, timestamp }: CachedData = JSON.parse(cached);
          if (Date.now() - timestamp < CACHE_DURATION_MS) {
            setText(cachedText);
            setStatus('done');
            return;
          }
        }
      } catch {
        // Ignore cache parsing errors
      }
    }

    setStatus('loading');
    setText('');
    setErrorMsg('');

    try {
      const response = await fetch('/api/analytics/insights', {
        credentials: 'include',
      });

      if (!response.ok) {
        setStatus('error');
        setErrorMsg('Failed to load insights.');
        return;
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        setStatus('error');
        setErrorMsg('Stream not available.');
        return;
      }

      let streamedText = '';
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6);
          try {
            const parsed = JSON.parse(data);
            if (parsed.type === 'delta') {
              streamedText += parsed.content;
              setText(streamedText); // Update with the complete streamed text
            } else if (parsed.type === 'done') {
              setStatus('done');
            } else if (parsed.type === 'error') {
              setStatus('error');
              setErrorMsg(parsed.content);
              return; // Stop processing on error
            }
          } catch {
            // skip malformed JSON
          }
        }
      }

      // Only cache if the stream completed without error
      if (status !== 'error') {
        try {
          const cacheData: CachedData = { text: streamedText, timestamp: Date.now() };
          sessionStorage.setItem(CACHE_KEY, JSON.stringify(cacheData));
        } catch {
          // Ignore cache writing errors
        }
      }
    } catch {
      setStatus('error');
      setErrorMsg('Failed to connect. Please try again.');
    }
  }, []);

  useEffect(() => {
    // The ref is no longer needed with session caching, but we'll keep a similar
    // pattern to ensure this only runs once on initial mount, letting the
    // caching logic decide whether to fetch.
    if (ran.current) return;
    ran.current = true;
    fetchInsights(false); // Initial fetch can use cache
  }, [fetchInsights]);

  // Parse text into insights and dig-deeper questions
  const parseContent = (raw: string) => {
    const insights: string[] = [];
    const questions: string[] = [];

    const lines = raw.split('\n');
    let inDigDeeper = false;

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;

      if (/^dig\s+deeper/i.test(trimmed)) {
        inDigDeeper = true;
        continue;
      }

      if (inDigDeeper) {
        // Strip leading "- " or "* "
        const q = trimmed.replace(/^[-*]\s*/, '');
        if (q) questions.push(q);
      } else {
        // Numbered insight: "1. ..."
        const match = trimmed.match(/^\d+\.\s+(.+)/);
        if (match) {
          insights.push(match[1]);
        }
      }
    }

    return { insights, questions };
  };

  const { insights, questions } = parseContent(text);

  const handleQuestion = (q: string) => {
    navigate('/chat', { state: { prefill: q } });
  };

  // Shimmer loading skeleton
  if (status === 'loading' && !text) {
    return (
      <div className="rounded-xl border border-gray-200/80 bg-white p-5 shadow-card h-full">
        <div className="flex items-center gap-2 mb-4">
          <svg className="h-4 w-4 text-brand animate-pulse" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 2a1 1 0 011 1v1.323l3.954 1.582 1.599-.8a1 1 0 01.894 1.79l-1.233.616 1.738 5.42a1 1 0 01-.285 1.05A3.989 3.989 0 0115 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.715-5.349L11 6.477V16h2a1 1 0 110 2H7a1 1 0 110-2h2V6.477L6.237 7.582l1.715 5.349a1 1 0 01-.285 1.05A3.989 3.989 0 015 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.738-5.42-1.233-.617a1 1 0 01.894-1.789l1.599.799L9 4.323V3a1 1 0 011-1z" />
          </svg>
          <h2 className="text-[13px] font-semibold text-gray-900">Weekly Insights</h2>
          <span className="ml-auto text-[11px] text-brand font-medium animate-pulse">Analysing...</span>
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="flex gap-3 animate-pulse">
              <div className="h-5 w-5 rounded-full bg-gray-200 flex-shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-3.5 bg-gray-200 rounded w-full" />
                <div className="h-3.5 bg-gray-200 rounded w-3/4" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (status === 'error') {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 h-full">
        <div className="flex items-center gap-2 mb-2">
          <svg className="h-4 w-4 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
          <h2 className="text-[13px] font-semibold text-red-800">Insights</h2>
        </div>
        <p className="text-[13px] text-red-700">{errorMsg}</p>
        <button
          onClick={() => fetchInsights(true)} // Force refresh
          className="mt-3 text-sm font-medium text-red-700 underline hover:text-red-900"
        >
          Try again
        </button>
      </div>
    );
  }

  // Streamed / done state
  return (
    <div className="rounded-xl border border-gray-200/80 bg-white p-5 shadow-card h-full">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <svg className="h-4 w-4 text-brand" fill="currentColor" viewBox="0 0 20 20">
          <path d="M10 2a1 1 0 011 1v1.323l3.954 1.582 1.599-.8a1 1 0 01.894 1.79l-1.233.616 1.738 5.42a1 1 0 01-.285 1.05A3.989 3.989 0 0115 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.715-5.349L11 6.477V16h2a1 1 0 110 2H7a1 1 0 110-2h2V6.477L6.237 7.582l1.715 5.349a1 1 0 01-.285 1.05A3.989 3.989 0 015 15a3.989 3.989 0 01-2.667-1.019 1 1 0 01-.285-1.05l1.738-5.42-1.233-.617a1 1 0 01.894-1.789l1.599.799L9 4.323V3a1 1 0 011-1z" />
        </svg>
        <h2 className="text-[13px] font-semibold text-gray-900">Weekly Insights</h2>
        {status === 'loading' && (
          <span className="ml-auto text-[11px] text-brand font-medium animate-pulse">Generating...</span>
        )}
      </div>

      {/* Insights list */}
      {insights.length > 0 ? (
        <div className="space-y-3 mb-4">
          {insights.map((insight, i) => (
            <div key={i} className="flex gap-2.5">
              <span className="flex-shrink-0 flex items-center justify-center h-5 w-5 rounded-full bg-brand/10 text-brand text-[10px] font-bold">
                {i + 1}
              </span>
              <p className="text-[13px] text-gray-700 leading-relaxed">{insight}</p>
            </div>
          ))}
        </div>
      ) : text ? (
        <p className="text-[13px] text-gray-700 whitespace-pre-wrap mb-4">{text}</p>
      ) : null}

      {/* Dig deeper */}
      {questions.length > 0 && (
        <div className="border-t border-gray-100 pt-3">
          <p className="text-[10px] font-medium text-gray-500 uppercase tracking-wide mb-2">Dig deeper</p>
          <div className="flex flex-col gap-1.5">
            {questions.map((q, i) => (
              <button
                key={i}
                onClick={() => handleQuestion(q)}
                className="text-left text-[12px] px-2.5 py-1.5 rounded-lg border border-gray-200 text-brand hover:bg-brand/5 hover:border-brand/30 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Refresh button */}
      {status === 'done' && (
        <div className="mt-3 flex justify-end">
          <button
            onClick={() => fetchInsights(true)}
            className="text-[11px] text-gray-400 hover:text-gray-600 flex items-center gap-1 transition-colors"
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
            </svg>
            Refresh
          </button>
        </div>
      )}
    </div>
  );
}

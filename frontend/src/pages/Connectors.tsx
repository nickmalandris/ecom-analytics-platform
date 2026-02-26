// frontend/src/pages/Connectors.tsx
import { useEffect, useState, useRef, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';

interface ConnectionStatus {
  shopify: { connected: boolean; store_url?: string };
  meta: { connected: boolean; account_id?: string };
  tenant_id: number | null;
}

interface SyncStatus {
  syncing: boolean;
  completed: boolean;
  failed: boolean;
  resources: { resource: string; status: string; records_synced: number }[];
}

type ConnectState = 'idle' | 'connecting' | 'syncing' | 'done' | 'error';

export default function Connectors() {
  const [user, setUser] = useState<any>(null);
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [connectState, setConnectState] = useState<ConnectState>('idle');
  const [syncProgress, setSyncProgress] = useState<SyncStatus | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const navigate = useNavigate();

  // Fetch user + connection status once
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [userRes, statusRes] = await Promise.all([
          axios.get('/users/me'),
          axios.get('/api/connections/status'),
        ]);
        setUser(userRes.data);
        setStatus(statusRes.data);
      } catch (err) {
        if (axios.isAxiosError(err) && err.response?.status === 401) {
          navigate('/login');
        }
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [navigate]);

  // Poll sync status while syncing
  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get('/api/connections/sync-status');
        const data: SyncStatus = res.data;
        setSyncProgress(data);

        if (data.completed && !data.syncing) {
          // Sync finished — update connection status
          setConnectState('done');
          clearInterval(pollRef.current!);
          pollRef.current = null;
          // Refresh connection status
          const statusRes = await axios.get('/api/connections/status');
          setStatus(statusRes.data);
        } else if (data.failed) {
          setConnectState('error');
          setErrorMsg('Data sync failed. Please try again.');
          clearInterval(pollRef.current!);
          pollRef.current = null;
        }
      } catch {
        // Ignore polling errors
      }
    }, 2000);
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleConnectShopify = async (e: React.FormEvent) => {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const shopUrl = (form.elements.namedItem('shopUrl') as HTMLInputElement).value;
    if (!shopUrl) return;

    setConnectState('connecting');
    setErrorMsg('');

    try {
      const response = await axios.post('/api/connections/shopify/connect', {
        shopify_store_url: shopUrl,
      });

      if (response.data.status === 'syncing') {
        // Token exists, sync started in background
        setConnectState('syncing');
        startPolling();
      } else if (response.data.status === 'needs_oauth') {
        // Need to redirect to Shopify OAuth
        window.location.href = response.data.redirect_url;
      }
    } catch (err: any) {
      setConnectState('error');
      setErrorMsg(err.response?.data?.detail || 'Failed to connect. Please try again.');
    }
  };

  const handleConnectMeta = () => {
    if (status?.tenant_id) {
      window.location.href = `/api/auth/meta/initiate/${status.tenant_id}`;
    }
  };

  if (loading) {
    return <Layout email={user?.email}><div className="text-gray-500">Loading...</div></Layout>;
  }

  const shopifyConnected = status?.shopify.connected || connectState === 'done';

  return (
    <Layout email={user?.email}>
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Data Connectors</h1>
        <p className="text-sm text-gray-500 mt-1">Manage your data sources</p>
      </header>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Shopify Card */}
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900">Shopify</h3>
            <StatusBadge
              connected={shopifyConnected}
              connectState={connectState}
            />
          </div>

          {shopifyConnected ? (
            <div className="text-sm text-gray-600">
              <p>Connected to: <span className="font-medium">{status?.shopify.store_url}</span></p>
              {connectState === 'done' && (
                <p className="text-green-600 mt-2 text-xs font-medium">
                  Data synced successfully
                </p>
              )}
            </div>
          ) : connectState === 'connecting' || connectState === 'syncing' ? (
            <SyncingView connectState={connectState} syncProgress={syncProgress} />
          ) : (
            <div>
              {errorMsg && (
                <p className="text-sm text-red-600 mb-3">{errorMsg}</p>
              )}
              <form onSubmit={handleConnectShopify} className="mt-4">
                <label htmlFor="shopUrl" className="block text-sm font-medium text-gray-700 mb-1">
                  Store URL
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    name="shopUrl"
                    id="shopUrl"
                    placeholder="your-store.myshopify.com"
                    className="block w-full rounded-md border-0 py-1.5 text-gray-900 ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-indigo-600 sm:text-sm sm:leading-6 px-3"
                    required
                  />
                  <button
                    type="submit"
                    className="rounded-md bg-[#008060] px-3 py-2 text-sm font-semibold text-white hover:bg-[#004c3f] whitespace-nowrap"
                  >
                    Connect
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>

        {/* Meta Ads Card */}
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900">Meta Ads</h3>
            <span className={`px-2 py-1 text-xs font-medium rounded-full ${
              status?.meta.connected ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
            }`}>
              {status?.meta.connected ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          {status?.meta.connected ? (
            <div className="text-sm text-gray-600">
              <p>Account ID: <span className="font-medium">{status.meta.account_id}</span></p>
            </div>
          ) : (
            <div className="mt-4">
              <p className="text-sm text-gray-500 mb-4">
                Connect your Meta ad account to sync campaign performance data.
              </p>
              <button
                onClick={handleConnectMeta}
                disabled={!shopifyConnected}
                className={`w-full rounded-md px-3 py-2 text-sm font-semibold text-white ${
                  !shopifyConnected
                    ? 'bg-gray-300 cursor-not-allowed'
                    : 'bg-[#1877f2] hover:bg-[#166fe5]'
                }`}
              >
                Connect with Facebook
              </button>
              {!shopifyConnected && (
                <p className="text-xs text-gray-400 mt-2">Connect Shopify first.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}


function StatusBadge({ connected, connectState }: { connected: boolean; connectState: ConnectState }) {
  if (connected) {
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-100 text-green-800">
        Connected
      </span>
    );
  }
  if (connectState === 'connecting' || connectState === 'syncing') {
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-blue-100 text-blue-800 flex items-center gap-1">
        <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
        {connectState === 'connecting' ? 'Connecting...' : 'Syncing...'}
      </span>
    );
  }
  if (connectState === 'error') {
    return (
      <span className="px-2 py-1 text-xs font-medium rounded-full bg-red-100 text-red-800">
        Error
      </span>
    );
  }
  return (
    <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-100 text-gray-800">
      Not Connected
    </span>
  );
}


function SyncingView({ connectState, syncProgress }: { connectState: ConnectState; syncProgress: SyncStatus | null }) {
  const resources = syncProgress?.resources || [];
  const running = resources.filter(r => r.status === 'running');
  const completed = resources.filter(r => r.status === 'completed');

  return (
    <div className="mt-2">
      <div className="flex items-center gap-2 mb-3">
        <svg className="animate-spin h-4 w-4 text-blue-600" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-sm font-medium text-blue-700">
          {connectState === 'connecting' ? 'Connecting to Shopify...' : 'Syncing data...'}
        </span>
      </div>
      {resources.length > 0 && (
        <div className="space-y-1.5">
          {resources.map(r => (
            <div key={r.resource} className="flex items-center gap-2 text-xs">
              {r.status === 'completed' ? (
                <span className="text-green-600">&#10003;</span>
              ) : r.status === 'running' ? (
                <span className="text-blue-500 animate-pulse">&#9679;</span>
              ) : (
                <span className="text-gray-300">&#9679;</span>
              )}
              <span className={r.status === 'completed' ? 'text-gray-600' : r.status === 'running' ? 'text-blue-700 font-medium' : 'text-gray-400'}>
                {r.resource}
              </span>
              {r.status === 'completed' && r.records_synced > 0 && (
                <span className="text-gray-400">{r.records_synced.toLocaleString()} records</span>
              )}
            </div>
          ))}
        </div>
      )}
      {completed.length > 0 && running.length === 0 && !syncProgress?.syncing && (
        <p className="text-xs text-gray-500 mt-2">Refreshing analytics views...</p>
      )}
    </div>
  );
}

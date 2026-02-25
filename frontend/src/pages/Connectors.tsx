// frontend/src/pages/Connectors.tsx
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';

interface ConnectionStatus {
  shopify: { connected: boolean; store_url?: string };
  meta: { connected: boolean; account_id?: string };
  tenant_id: number;
}

export default function Connectors() {
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // Poll for status updates every 5 seconds
  useEffect(() => {
    let intervalId: any;

    const fetchStatus = async () => {
      try {
        const response = await axios.get('/api/connections/status');
        setStatus(response.data);
        setLoading(false);
      } catch (err) {
        console.error('Failed to fetch connection status', err);
        // If 401, redirect to login
        if (axios.isAxiosError(err) && err.response?.status === 401) {
          navigate('/login');
        }
      }
    };

    fetchStatus();
    intervalId = setInterval(fetchStatus, 5000);

    return () => clearInterval(intervalId);
  }, [navigate]);

  const handleConnectShopify = async (e: React.FormEvent) => {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const shopUrl = (form.elements.namedItem('shopUrl') as HTMLInputElement).value;

    if (!shopUrl) return;

    try {
        // We'll reuse the auth initiation endpoint but need to know the tenant ID
        // The backend should probably provide a "me" endpoint for connections 
        // that handles the tenant ID lookup from the user session.
        // For now, we'll assume we get the tenant_id from the status response.
        if (status?.tenant_id) {
             window.location.href = `/api/auth/shopify/initiate/${status.tenant_id}?shop=${shopUrl}`;
        }
    } catch (err) {
        console.error(err);
    }
  };

  const handleConnectMeta = () => {
      if (status?.tenant_id) {
          window.location.href = `/api/auth/meta/initiate/${status.tenant_id}`;
      }
  }

  if (loading) {
    return <Layout><div>Loading...</div></Layout>;
  }

  return (
    <Layout>
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Data Connectors</h1>
        <p className="text-gray-500 mt-2">Manage your data sources</p>
      </header>

      <div className="grid gap-6 md:grid-cols-2">
        {/* Shopify Card */}
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900">Shopify</h3>
            <span className={`px-2 py-1 text-xs font-medium rounded-full ${status?.shopify.connected ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
              {status?.shopify.connected ? 'Connected' : 'Not Connected'}
            </span>
          </div>
          
          {status?.shopify.connected ? (
            <div className="text-sm text-gray-600">
              <p>Connected to: <strong>{status.shopify.store_url}</strong></p>
              <button className="mt-4 text-red-600 hover:text-red-800 text-sm font-medium">
                Disconnect
              </button>
            </div>
          ) : (
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
                  className="rounded-md bg-[#008060] px-3 py-2 text-sm font-semibold text-white hover:bg-[#004c3f]"
                >
                  Connect
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Meta Ads Card */}
        <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900">Meta Ads</h3>
            <span className={`px-2 py-1 text-xs font-medium rounded-full ${status?.meta.connected ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}`}>
              {status?.meta.connected ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          {status?.meta.connected ? (
            <div className="text-sm text-gray-600">
              <p>Account ID: <strong>{status.meta.account_id}</strong></p>
              <button className="mt-4 text-red-600 hover:text-red-800 text-sm font-medium">
                Disconnect
              </button>
            </div>
          ) : (
            <div className="mt-4">
              <p className="text-sm text-gray-500 mb-4">
                Connect your Meta ad account to sync campaign performance data.
              </p>
              <button
                onClick={handleConnectMeta}
                disabled={!status?.shopify.connected} // Enforce order: Shopify first (to ensure tenant exists? Actually user exists now, so order matters less, but good for flow)
                className={`w-full rounded-md px-3 py-2 text-sm font-semibold text-white ${
                    !status?.shopify.connected 
                    ? 'bg-gray-300 cursor-not-allowed' 
                    : 'bg-[#1877f2] hover:bg-[#166fe5]'
                }`}
              >
                Connect with Facebook
              </button>
              {!status?.shopify.connected && (
                  <p className="text-xs text-gray-400 mt-2">Connect Shopify first.</p>
              )}
            </div>
          )}
        </div>
      </div>
    </Layout>
  );
}

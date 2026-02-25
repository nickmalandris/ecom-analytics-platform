// frontend/src/pages/Dashboard.tsx
import { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/Layout';

export default function Dashboard() {
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await axios.get('/users/me');
        setUser(response.data);
      } catch (err) {
        // Not authenticated, redirect to login
        navigate('/login');
      } finally {
        setLoading(false);
      }
    };

    fetchUser();
  }, [navigate]);

  if (loading) {
    return <div className="flex justify-center items-center h-screen">Loading...</div>;
  }

  return (
    <Layout>
      <header className="mb-8">
        <h1 className="text-3xl font-bold leading-tight tracking-tight text-gray-900">
          Dashboard
        </h1>
        <p className="text-gray-500 mt-2">Welcome back, {user?.email}</p>
      </header>
      
      <div className="rounded-lg border-4 border-dashed border-gray-200 h-96 flex items-center justify-center text-gray-400">
        Charts and Metrics coming soon...
      </div>
    </Layout>
  );
}

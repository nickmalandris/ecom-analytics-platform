// frontend/src/components/Sidebar.tsx
import { Link, useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await axios.post('/auth/jwt/logout');
      navigate('/login');
    } catch (err) {
      console.error('Logout failed', err);
    }
  };

  const menuItems = [
    { path: '/', label: 'Dashboard', icon: '📊' },
    { path: '/connectors', label: 'Connectors', icon: '🔌' },
  ];

  return (
    <div className="flex h-screen flex-col justify-between border-r bg-white w-64">
      <div className="px-4 py-6">
        <span className="grid h-10 w-32 place-content-center rounded-lg bg-gray-100 text-xs text-gray-600">
          Analytics
        </span>

        <ul className="mt-6 space-y-1">
          {menuItems.map((item) => (
            <li key={item.path}>
              <Link
                to={item.path}
                className={`block rounded-lg px-4 py-2 text-sm font-medium ${
                  location.pathname === item.path
                    ? 'bg-gray-100 text-gray-700'
                    : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700'
                }`}
              >
                <span className="mr-2">{item.icon}</span>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <div className="sticky inset-x-0 bottom-0 border-t border-gray-100">
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 bg-white p-4 hover:bg-gray-50 w-full text-left"
        >
          <div className="text-xs">
            <p className="font-medium text-gray-500">Sign out</p>
          </div>
        </button>
      </div>
    </div>
  );
}

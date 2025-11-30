import { ReactNode, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import LoginPanel from './LoginPanel';
import './ProtectedRoute.css';

interface ProtectedRouteProps {
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * A wrapper component that requires authentication.
 * If the user is not logged in, shows a login prompt.
 */
export function ProtectedRoute({ children, fallback }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const [showLogin, setShowLogin] = useState(false);

  if (isLoading) {
    return (
      <div className="protected-route-loading">
        <div className="loading-spinner"></div>
        <p>Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <>
        <div className="protected-route-prompt">
          <div className="protected-route-content">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
            </svg>
            <h2>Login Required</h2>
            <p>Please log in to access this feature and save your work.</p>
            <button className="protected-route-login-btn" onClick={() => setShowLogin(true)}>
              Login / Sign Up
            </button>
            {fallback && (
              <div className="protected-route-fallback">
                {fallback}
              </div>
            )}
          </div>
        </div>
        <LoginPanel isOpen={showLogin} onClose={() => setShowLogin(false)} />
      </>
    );
  }

  return <>{children}</>;
}

/**
 * A component that shows content only to authenticated users,
 * otherwise shows nothing or an optional fallback.
 */
export function AuthOnly({ children, fallback = null }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return null;
  }

  if (!isAuthenticated) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}

/**
 * A component that shows content only to unauthenticated users.
 */
export function GuestOnly({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading || isAuthenticated) {
    return null;
  }

  return <>{children}</>;
}

export default ProtectedRoute;

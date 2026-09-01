import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import './Navbar.css';
import ChatOverlay from './ChatOverlay';
import LoginPanel from './LoginPanel';
import { useAuth } from '../context/AuthContext';

interface NavbarProps {
  developerMode?: boolean;
  onDeveloperModeChange?: (enabled: boolean) => void;
  currentStep?: number;
}

const Navbar = ({ developerMode = false, onDeveloperModeChange, currentStep }: NavbarProps) => {
  const { user, isAuthenticated, logout } = useAuth();
  const navigate = useNavigate();
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isLoginOpen, setIsLoginOpen] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  const handleDeveloperModeToggle = () => {
    if (onDeveloperModeChange) {
      onDeveloperModeChange(!developerMode);
    }
  };

  const handleLogout = () => {
    logout();
    setShowUserMenu(false);
  };

  // Show developer mode toggle when in models section (step 3) or scorecard section (step 4)
  const showDeveloperMode = currentStep === 3 || currentStep === 4;

  const handleBrandClick = () => {
    navigate('/');
  };

  const handleLoginSuccess = () => {
    // Navigate to home page and refresh
    navigate('/');
    // Force a page refresh to reload all data
    window.location.reload();
  };

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand" onClick={handleBrandClick}>
          <div className="navbar-brand-title">Automated Credit Scoring</div>
          <div className="navbar-brand-subtitle">AI Driven Predictive Analytics for Smarter Lending</div>
        </div>
        <div className="navbar-links">
          {showDeveloperMode && (
            <div className="developer-mode-container">
              <label className="toggle-label">
                <span className="toggle-text">Developer Mode</span>
                <input
                  type="checkbox"
                  checked={developerMode}
                  onChange={handleDeveloperModeToggle}
                  className="toggle-input"
                />
                <span className="toggle-slider"></span>
              </label>
            </div>
          )}
          <button className="navbar-icon-btn" onClick={() => setIsChatOpen(true)} title="Chat with AI">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
          </button>
          {isAuthenticated && user ? (
            <div className="navbar-user-container">
              <button 
                className="navbar-user-btn" 
                onClick={() => setShowUserMenu(!showUserMenu)}
                title={user.email}
              >
                <span className="navbar-user-avatar">
                  {user.name.charAt(0).toUpperCase()}
                </span>
                <span className="navbar-user-name">{user.name}</span>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M6 9l6 6 6-6"/>
                </svg>
              </button>
              {showUserMenu && (
                <div className="navbar-user-menu">
                  <div className="navbar-user-menu-header">
                    <span className="navbar-user-menu-name">{user.name}</span>
                    <span className="navbar-user-menu-email">{user.email}</span>
                  </div>
                  <div className="navbar-user-menu-divider"></div>
                  <button className="navbar-user-menu-item" onClick={handleLogout}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                      <polyline points="16 17 21 12 16 7"></polyline>
                      <line x1="21" y1="12" x2="9" y2="12"></line>
                    </svg>
                    Logout
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button className="navbar-login-btn" onClick={() => setIsLoginOpen(true)} title="Login">
              Login
            </button>
          )}
        </div>
      </nav>
      <ChatOverlay isOpen={isChatOpen} onClose={() => setIsChatOpen(false)} />
      <LoginPanel isOpen={isLoginOpen} onClose={() => setIsLoginOpen(false)} onSuccess={handleLoginSuccess} />
    </>
  );
};

export default Navbar;
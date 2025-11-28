import { useState } from 'react';
import './Navbar.css';
import ChatOverlay from './ChatOverlay';
import LoginPanel from './LoginPanel';

interface NavbarProps {
  developerMode?: boolean;
  onDeveloperModeChange?: (enabled: boolean) => void;
  currentStep?: number;
}

const Navbar = ({ developerMode = false, onDeveloperModeChange, currentStep }: NavbarProps) => {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isLoginOpen, setIsLoginOpen] = useState(false);

  const handleDeveloperModeToggle = () => {
    if (onDeveloperModeChange) {
      onDeveloperModeChange(!developerMode);
    }
  };

  // Show developer mode toggle when in models section (step 3) or scorecard section (step 4)
  const showDeveloperMode = currentStep === 3 || currentStep === 4;

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand">Automated Credit Score</div>
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
          <button className="navbar-login-btn" onClick={() => setIsLoginOpen(true)} title="Login">
            Login
          </button>
        </div>
      </nav>
      <ChatOverlay isOpen={isChatOpen} onClose={() => setIsChatOpen(false)} />
      <LoginPanel isOpen={isLoginOpen} onClose={() => setIsLoginOpen(false)} />
    </>
  );
};

export default Navbar;

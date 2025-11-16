import { useState } from 'react';
import './Navbar.css';
import ChatOverlay from './ChatOverlay';
import LoginPanel from './LoginPanel';

const Navbar = () => {
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isLoginOpen, setIsLoginOpen] = useState(false);

  return (
    <>
      <nav className="navbar">
        <div className="navbar-brand">Automated Credit Score</div>
        <div className="navbar-links">
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

import { useState, useRef, useEffect } from 'react';
import { authPost } from '../utils/api';
import './ChatOverlay.css';

interface Message {
  id: number;
  text: string;
  sender: 'user' | 'ai';
  timestamp: Date;
}

const ChatOverlay = ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      text: "Hello! I'm your AI assistant. How can I help you with credit scoring today?",
      sender: 'ai',
      timestamp: new Date()
    }
  ]);

  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Helper function to convert newlines and markdown-like headings into HTML
  const formatAIMessage = (text: string) => {
    // Replace headings (e.g., **Heading**) with bold div
    let formatted = text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n- /g, '<br>• ')
      .replace(/\n/g, '<br>');

    return formatted;
  };

  const handleSend = async () => {
    if (!inputText.trim()) return;

    const userMessage: Message = {
      id: messages.length + 1,
      text: inputText,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    const userText = inputText;
    setInputText('');

    try {
      const data = await authPost('/api/chat', { message: userText });

      const aiMessage: Message = {
        id: messages.length + 2,
        text: data.reply || "AI did not respond.",
        sender: 'ai',
        timestamp: new Date()
      };

      setMessages(prev => [...prev, aiMessage]);

    } catch (error) {
      const errorMessage: Message = {
        id: messages.length + 2,
        text: "⚠️ Error connecting to AI backend.",
        sender: 'ai',
        timestamp: new Date()
      };

      setMessages(prev => [...prev, errorMessage]);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="chat-overlay" onClick={onClose}>
      <div className="chat-container" onClick={(e) => e.stopPropagation()}>

        {/* HEADER */}
        <div className="chat-header">
          <div className="chat-header-info">
            <div className="chat-ai-avatar">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                <path d="M2 17l10 5 10-5"></path>
                <path d="M2 12l10 5 10-5"></path>
              </svg>
            </div>
            <div>
              <div className="chat-header-title">AI Assistant</div>
              <div className="chat-header-subtitle"></div>
            </div>
          </div>
          <button className="chat-close-btn" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        {/* MESSAGES */}
        <div className="chat-messages">
          {messages.map((message) => (
            <div key={message.id} className={`chat-message ${message.sender}`}>
              <div
                className="chat-message-content"
                dangerouslySetInnerHTML={message.sender === 'ai' ? { __html: formatAIMessage(message.text) } : undefined}
              >
                {message.sender === 'user' ? message.text : null}
              </div>
              <div className="chat-message-time">
                {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* INPUT BOX */}
        <div className="chat-input-container">
          <input
            type="text"
            className="chat-input"
            placeholder="Type your message..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={handleKeyPress}
            autoFocus
          />
          <button className="chat-send-btn" onClick={handleSend} disabled={!inputText.trim()}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatOverlay;
import './Navbar.css';

const Navbar = () => {
  return (
    <nav className="navbar">
      <div className="navbar-brand">Automated Credit Score</div>
      <div className="navbar-links">
        <a href="#">Dashboard</a>
        <a href="#">Models</a>
        <a href="#">Docs</a>
        <a href="#">Help</a>
      </div>
    </nav>
  );
};

export default Navbar;
